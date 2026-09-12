import json
import logging
import threading
import time
from typing import Optional, Callable

from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic

# Reduce noise from kafka-python internal logging
kafka_logger = logging.getLogger('kafka')
kafka_logger.setLevel(logging.WARNING)

from .config import settings
from .exceptions import IntegrationError

logger = logging.getLogger(__name__)


class KafkaService:
    """Service for Kafka message production and consumption."""

    def __init__(self) -> None:
        self._producer: Optional[KafkaProducer] = None
        self._consumer_thread: Optional[threading.Thread] = None
        self._consumer_callback: Optional[Callable[[dict], None]] = None

    def init(self) -> None:
        """Initialize Kafka and create necessary topics."""
        try:
            admin_client = KafkaAdminClient(
                bootstrap_servers=settings.kafka_broker,
                client_id='api-service-admin'
            )

            topics = [
                NewTopic(name=settings.repo_parsed_topic, num_partitions=1, replication_factor=1),
                NewTopic(name=settings.audit_tasks_topic, num_partitions=1, replication_factor=1),
                NewTopic(name=settings.audit_status_topic, num_partitions=1, replication_factor=1)
            ]

            existing_topics = admin_client.list_topics()
            topics_to_create = [t for t in topics if t.name not in existing_topics]

            if topics_to_create:
                admin_client.create_topics(new_topics=topics_to_create, validate_only=False)
                logger.info(f"Created Kafka topics: {[t.name for t in topics_to_create]}")
            else:
                logger.info("All Kafka topics already exist")

            admin_client.close()
            logger.info("Kafka initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Kafka: {e}")
            raise IntegrationError(f"Kafka initialization failed: {str(e)}")

    def _get_producer(self) -> KafkaProducer:
        """Get or create Kafka producer instance."""
        if self._producer is None:
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=settings.kafka_broker,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    acks="all"
                )
                logger.info("Kafka producer initialized")
            except Exception as e:
                logger.error(f"Failed to create Kafka producer: {e}")
                raise IntegrationError(f"Kafka producer creation failed: {str(e)}")

        return self._producer

    def send_message(self, topic: str, message: dict) -> None:
        """Send a message to a Kafka topic."""
        try:
            producer = self._get_producer()
            producer.send(topic, value=message)
            producer.flush(timeout=settings.kafka_timeout_seconds)
            logger.info(f"Sent message to topic {topic}")
        except Exception as e:
            logger.error(f"Failed to send message to Kafka topic {topic}: {e}")
            raise IntegrationError(f"Failed to send message to Kafka: {str(e)}")

    def start_status_consumer(self, callback: Callable[[dict], None]) -> None:
        """Start the status consumer in a background thread."""
        if self._consumer_thread is None or not self._consumer_thread.is_alive():
            self._consumer_callback = callback
            self._consumer_thread = threading.Thread(
                target=self._consume_status_updates,
                daemon=True,
                name="status-consumer"
            )
            self._consumer_thread.start()
            logger.info("Status consumer thread started")

    def _consume_status_updates(self) -> None:
        """Consume audit status updates from Kafka."""
        while True:
            try:
                consumer = KafkaConsumer(
                    settings.audit_status_topic,
                    bootstrap_servers=settings.kafka_broker,
                    group_id="api-service-status",
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset="earliest",
                    enable_auto_commit=True
                )
                logger.info(f"Connected to Kafka, listening to {settings.audit_status_topic}")

                for message in consumer:
                    try:
                        status_data = message.value
                        logger.info(f"Received status update: {status_data}")
                        if self._consumer_callback:
                            self._consumer_callback(status_data)
                    except Exception as e:
                        logger.error(f"Error processing status message: {e}")

            except Exception as e:
                logger.error(f"Kafka consumer error: {e}, reconnecting in 5 seconds...")
                time.sleep(5)
