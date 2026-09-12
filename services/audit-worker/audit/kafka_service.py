import json
import logging
import time
from typing import Callable, Optional

from kafka import KafkaProducer, KafkaConsumer

# Reduce noise from kafka-python internal logging
logging.getLogger('kafka').setLevel(logging.WARNING)

from .config import settings
from .exceptions import KafkaError

logger = logging.getLogger(__name__)


class KafkaService:
    """Service for Kafka message production and consumption."""

    def __init__(self) -> None:
        self._producer: Optional[KafkaProducer] = None

    def init_producer(self) -> None:
        """Initialize Kafka producer with retry logic and connection stability settings."""
        while True:
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=settings.kafka_broker,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    acks="all",
                    # Add connection stability settings (same as indexer)
                    reconnect_backoff_ms=100,
                    reconnect_backoff_max_ms=10000,
                    request_timeout_ms=30000,
                    max_in_flight_requests_per_connection=5,
                )
                logger.info("Kafka producer initialized: %s", settings.kafka_broker)
                break
            except Exception as e:
                logger.warning("Kafka not available, retrying in 5 seconds... Error: %s", e)
                time.sleep(5)

    def get_producer(self) -> Optional[KafkaProducer]:
        """Get Kafka producer instance if initialized."""
        return self._producer

    def send_message(self, topic: str, message: dict) -> None:
        """Send a message to specified Kafka topic."""
        if not self._producer:
            logger.warning("Producer not initialized, cannot send message to topic %s", topic)
            return
        try:
            self._producer.send(topic, value=message)
            self._producer.flush(timeout=settings.kafka_timeout_seconds)
            logger.info("Successfully sent message to Kafka topic: %s", topic)
        except Exception as e:
            logger.exception("Failed to send message to topic %s: %s", topic, e)

    def send_status(
        self,
        audit_id: str,
        status: str,
        error: Optional[str] = None,
        progress: Optional[int] = None,
        chunk_index: Optional[int] = None,
        total_chunks: Optional[int] = None
    ) -> None:
        """Send audit status update to Kafka."""
        msg: dict = {"audit_id": audit_id, "status": status}
        if error:
            msg["error"] = error
        if progress is not None:
            msg["progress"] = progress
        if chunk_index is not None:
            msg["chunk_index"] = chunk_index
        if total_chunks is not None:
            msg["total_chunks"] = total_chunks

        try:
            producer = self.get_producer()
            if producer:
                producer.send(settings.audit_status_topic, value=msg)
                producer.flush(timeout=settings.kafka_timeout_seconds)
                logger.info("Successfully sent status %s for audit %s", status, audit_id)
        except Exception as e:
            logger.exception("Failed to send status for audit %s: %s", audit_id, e)

    def consume(self, topic: str, on_message: Callable) -> None:
        """Consume messages from Kafka topic with retry logic (same as indexer)."""
        while True:
            try:
                consumer = KafkaConsumer(
                    topic,
                    bootstrap_servers=settings.kafka_broker,
                    group_id=settings.audit_group,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset="latest",
                    enable_auto_commit=True,
                )
                logger.info("Listening to topic '%s'", topic)
                break
            except Exception:
                logger.warning("Kafka not available, retrying in 5 seconds...")
                time.sleep(5)

        logger.info("Waiting for messages...")
        for message in consumer:
            on_message(message)

    def close(self) -> None:
        """Close Kafka producer connection."""
        if self._producer:
            try:
                self._producer.close()
                logger.info("Kafka producer closed")
            except Exception as e:
                logger.error(f"Error closing Kafka producer: {e}")
            self._producer = None

    def send_audit_tasks(self, audit_id: str, points: list) -> None:
        """Send audit tasks to Kafka (compatibility method, same as indexer)."""
        if not self._producer:
            logger.warning("Producer not initialized, cannot send audit tasks for audit %s", audit_id)
            return
        total = len(points)
        for i, point in enumerate(points):
            task = {
                "chunk_id": point.payload["chunk_id"],
                "code": point.payload["code"],
                "file_path": point.payload["file_path"],
                "audit_id": audit_id,
                "chunk_index": i,
                "total_chunks": total,
            }
            try:
                self._producer.send(settings.audit_tasks_topic, value=task)
            except Exception as e:
                logger.exception("Failed to send audit task %d for audit %s: %s", i, audit_id, e)
        try:
            self._producer.flush()
            logger.info("Successfully sent %d audit tasks for audit %s", total, audit_id)
        except Exception as e:
            logger.exception("Failed to flush audit tasks for audit %s: %s", audit_id, e)
