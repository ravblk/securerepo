import logging
from typing import Optional, Tuple

from .models import AuditTask
from .audit_workflow import AuditWorkflow
from .llm_service import LLMService
from .qdrant_service import QdrantService
from .embedding_service import EmbeddingService
from .database_service import DatabaseService
from .kafka_service import KafkaService
from .language_detector import LanguageDetector
from .exceptions import AuditWorkerError

logger = logging.getLogger(__name__)


class AuditController:
    """Controller for audit task processing."""

    def __init__(
        self,
        workflow: AuditWorkflow,
        llm_service: LLMService,
        database_service: DatabaseService,
        kafka_service: KafkaService,
    ):
        self._workflow = workflow
        self._llm_service = llm_service
        self._database_service = database_service
        self._kafka_service = kafka_service

    def process_task(self, task: AuditTask) -> Tuple[list, Optional[str]]:
        """Process a single audit task."""
        logger.info(f"Processing task: {task.chunk_id} for audit {task.audit_id}")

        # Detect programming language
        lang = LanguageDetector.detect(task.file_path)
        logger.info(f"Detected language: {lang}")

        # Prepare initial workflow state
        initial_state = {
            "task": task,
            "code": task.code,
            "file_path": task.file_path,
            "lang": lang,
            "code_embedding": [],
            "general_rules": [],
            "internal_rules": [],
            "violations": [],
            "severity": None,
            "auditing_sent": False
        }

        try:
            # Process through workflow
            violations, severity = self._workflow.process(task, initial_state)

            # Save results to database if violations found
            if violations:
                self._database_service.save_result(
                    audit_id=task.audit_id,
                    chunk_id=task.chunk_id,
                    file_path=task.file_path,
                    violations=violations,
                    severity=severity
                )

            logger.info(
                f"Task {task.chunk_id} completed: {len(violations)} violations, severity: {severity}"
            )
            return violations, severity

        except Exception as e:
            error_msg = f"Error processing task {task.chunk_id}: {str(e)}"
            logger.error(error_msg)
            raise AuditWorkerError(error_msg)

    def send_auditing_status(
        self,
        audit_id: str,
        chunk_index: int,
        total_chunks: int
    ) -> None:
        """Send auditing status to Kafka."""
        try:
            self._kafka_service.send_status(
                audit_id=audit_id,
                status="auditing",
                progress=50,
                chunk_index=chunk_index,
                total_chunks=total_chunks
            )
            logger.info(f"Sent 'auditing' status for audit {audit_id}")
        except Exception as e:
            logger.error(f"Failed to send auditing status: {e}")

    def send_completed_status(
        self,
        audit_id: str,
        chunk_index: int,
        total_chunks: int
    ) -> None:
        """Send completed status to Kafka."""
        try:
            self._kafka_service.send_status(
                audit_id=audit_id,
                status="completed",
                progress=100,
                chunk_index=chunk_index,
                total_chunks=total_chunks
            )
            logger.info(f"Sent 'completed' status for audit {audit_id}")
        except Exception as e:
            logger.error(f"Failed to send completed status: {e}")

    def send_failed_status(self, audit_id: str, error: str) -> None:
        """Send failed status to Kafka."""
        try:
            self._kafka_service.send_status(
                audit_id=audit_id,
                status="failed",
                error=error
            )
            logger.info(f"Sent 'failed' status for audit {audit_id}: {error}")
        except Exception as e:
            logger.error(f"Failed to send failed status: {e}")

    def check_llm_availability(self) -> bool:
        """Check if LLM is available."""
        available, message = self._llm_service.test_connection()
        if not available:
            logger.warning(f"LLM unavailable: {message}")
        return available

    def should_send_auditing_status(self, audit_id: str, tracking_dict: dict) -> bool:
        """Determine if auditing status should be sent."""
        return audit_id not in tracking_dict
