"""
FastAPI application for SecureRepo Audit Worker.
Refactored to use modular components.
"""
import logging
import threading
import time
import json
from typing import Optional

from fastapi import FastAPI

from audit.config import settings
from audit.models import AuditTask, HealthResponse, ServiceInfoResponse
from audit.audit_controller import AuditController
from audit.audit_workflow import AuditWorkflow
from audit.llm_service import LLMService
from audit.qdrant_service import QdrantService
from audit.embedding_service import EmbeddingService
from audit.database_service import DatabaseService
from audit.kafka_service import KafkaService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("audit-worker")

# Global service instances
llm_service: Optional[LLMService] = None
embedding_service: Optional[EmbeddingService] = None
qdrant_service: Optional[QdrantService] = None
database_service: Optional[DatabaseService] = None
kafka_service: Optional[KafkaService] = None
audit_workflow: Optional[AuditWorkflow] = None
audit_controller: Optional[AuditController] = None

# In-memory state tracking
auditing_sent: dict = {}
failed_audits: set = set()


def initialize_services() -> None:
    """Initialize all required services with graceful fallback."""
    global llm_service, embedding_service, qdrant_service, database_service, kafka_service, audit_workflow, audit_controller

    logger.info("Initializing audit worker services...")

    # Initialize LLM service (can be unavailable initially)
    try:
        llm_service = LLMService()
        available, message = llm_service.test_connection()
        if not available:
            logger.warning(f"LLM service initialization warning: {message}. Service will retry on demand.")
        else:
            logger.info("LLM service initialized successfully")
    except Exception as e:
        logger.warning(f"LLM service initialization failed: {e}. Service will retry on demand.")
        llm_service = LLMService()  # Create instance anyway for later retry

    # Initialize embedding service (can be unavailable initially)
    try:
        embedding_service = EmbeddingService()
        logger.info("Embedding service initialized successfully")
    except Exception as e:
        logger.warning(f"Embedding service initialization failed: {e}. Service will retry on demand.")
        embedding_service = EmbeddingService()  # Create instance anyway for later retry

    # Initialize Qdrant service (can be unavailable initially)
    try:
        qdrant_service = QdrantService()
        available, message = qdrant_service.test_connection()
        if not available:
            logger.warning(f"Qdrant service initialization warning: {message}. Service will retry on demand.")
        else:
            logger.info("Qdrant service initialized successfully")
    except Exception as e:
        logger.warning(f"Qdrant service initialization failed: {e}. Service will retry on demand.")
        qdrant_service = QdrantService()  # Create instance anyway for later retry

    # Initialize database service (can be unavailable initially)
    try:
        database_service = DatabaseService()
        logger.info("Database service initialized successfully")
    except Exception as e:
        logger.warning(f"Database service initialization failed: {e}. Service will retry on demand.")
        database_service = DatabaseService()  # Create instance anyway for later retry

    # Initialize Kafka service (can be unavailable initially)
    try:
        kafka_service = KafkaService()
        kafka_service.init_producer()  # Initialize producer with retry logic (same as indexer)
        logger.info("Kafka service initialized successfully")
    except Exception as e:
        logger.warning(f"Kafka service initialization warning: {e}. Service may retry on demand.")
        kafka_service = KafkaService()  # Create instance anyway for later retry

    # Initialize workflow (can handle transient dependencies)
    try:
        audit_workflow = AuditWorkflow(
            llm_service=llm_service,
            qdrant_service=qdrant_service,
            embedding_service=embedding_service
        )
        logger.info("Audit workflow initialized successfully")
    except Exception as e:
        logger.warning(f"Audit workflow initialization warning: {e}. Workflow may retry on demand.")

    # Initialize controller (can handle transient dependencies)
    try:
        audit_controller = AuditController(
            workflow=audit_workflow,
            llm_service=llm_service,
            database_service=database_service,
            kafka_service=kafka_service
        )
        logger.info("Audit controller initialized successfully")
    except Exception as e:
        logger.warning(f"Audit controller initialization warning: {e}. Controller may retry on demand.")

    logger.info("All services initialized to operate mode (some dependencies may reconnect on demand)")


def process_message(message, consumer) -> None:
    """Process a single Kafka message."""
    task: Optional[AuditTask] = None
    audit_id: Optional[str] = None

    try:
        task_data = message.value
        task = AuditTask(**task_data)

        chunk_index = task.chunk_index or 0
        total_chunks = task.total_chunks or 1
        is_last_chunk = chunk_index >= total_chunks - 1
        audit_id = task.audit_id

        logger.info(f"Received task: {task.chunk_id} ({chunk_index + 1}/{total_chunks})")

        # Skip if audit already failed
        if audit_id in failed_audits:
            logger.warning(f"Skipping {task.chunk_id} - audit {audit_id} already marked as failed")
            return

        # Send initial auditing status
        if audit_controller.should_send_auditing_status(audit_id, auditing_sent):
            audit_controller.send_auditing_status(audit_id, chunk_index, total_chunks)
            auditing_sent[audit_id] = True
            failed_audits.discard(audit_id)
            logger.info(f"Sent 'auditing' status for audit {audit_id}")

        logger.info("Processing task...")
        violations, severity = audit_controller.process_task(task)

        logger.info(
            f"Processed {task.chunk_id}, violations: {len(violations)}, "
            f"severity: {severity}, is_last_chunk: {is_last_chunk}"
        )

        # Send completion status for last chunk
        if is_last_chunk:
            audit_controller.send_completed_status(audit_id, chunk_index, total_chunks)
            # Clean up tracking
            if audit_id in auditing_sent:
                del auditing_sent[audit_id]

    except Exception as e:
        error_msg = f"Error in {task.chunk_id if task else 'unknown task'}: {str(e)}"
        logger.error(error_msg)

        # Send failed status if first error for this audit
        if audit_id and audit_id not in failed_audits:
            logger.info(f"Sending failed status for audit {audit_id}: {error_msg}")
            audit_controller.send_failed_status(audit_id, error_msg)
            failed_audits.add(audit_id)
        else:
            logger.warning(f"Skipping failed status (already sent or no audit_id)")


def consume_tasks() -> None:
    """Main consumer loop for processing audit tasks."""
    cycle_count = 0
    max_cycles = 1  # Process messages only once

    logger.info(f"Starting to consume from topic: {settings.audit_tasks_topic}")

    try:
        while cycle_count < max_cycles:
            consumer = None
            while consumer is None:
                try:
                    consumer = kafka_service.create_consumer(settings.audit_tasks_topic)
                    logger.info("Consumer created for cycle %d/%d", cycle_count + 1, max_cycles)
                except Exception as e:
                    logger.error("Failed to create consumer: %s, retrying in 5 seconds...", e)
                    time.sleep(5)

            logger.info("Waiting for messages...")
            messages_processed = 0
            for message in consumer:
                try:
                    process_message(message, consumer)
                    messages_processed += 1

                    # Commit offset after successful processing
                    try:
                        consumer.commit()
                    except Exception as e:
                        logger.error("Failed to commit offset: %s", e)

                except Exception as e:
                    logger.error("Error in consume loop: %s", e)
                    # Don't commit on error - message will be retried
                    if e.__class__.__name__ == 'KeyboardInterrupt':
                        raise

            logger.info("Cycle %d completed. Processed %d messages", cycle_count + 1, messages_processed)
            consumer.close()
            cycle_count += 1

        logger.info("All processing cycles completed")

    except KeyboardInterrupt:
        logger.info("Consuming stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in kafka consumption: {e}")
        time.sleep(5)

    if hasattr(kafka_service, 'close'):
        kafka_service.close()


def run_api():
    """Run FastAPI application in a separate thread."""
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


# FastAPI application setup
app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint."""
    return HealthResponse(status="healthy", service=settings.app_name)


@app.get("/", response_model=ServiceInfoResponse)
def root():
    """Service information endpoint."""
    return ServiceInfoResponse(
        service="audit-worker",
        kafka_topic=settings.audit_tasks_topic,
        storage="PostgreSQL"
    )


if __name__ == "__main__":
    try:
        # Initialize all services
        initialize_services()

        # Start API in daemon thread
        api_thread = threading.Thread(target=run_api, daemon=True)
        api_thread.start()
        logger.info("API server started in background thread")

        # Start Kafka consumer in main thread
        logger.info("Starting Kafka consumer...")
        consume_tasks()

    except KeyboardInterrupt:
        logger.info("Audit worker stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in audit worker: {e}")
        raise
    finally:
        # Cleanup services
        if kafka_service:
            kafka_service.close()
        if database_service:
            database_service.close()
        logger.info("Audit worker shutdown complete")
