import json
import logging
import time
from typing import Callable, Optional

from kafka import KafkaConsumer, KafkaProducer
from .config import settings
from .exceptions import KafkaPublishError

logger = logging.getLogger(__name__)

# Reduce noise from kafka-python internal logging
logging.getLogger('kafka').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class KafkaService:
    def __init__(self) -> None:
        self._producer: Optional[KafkaProducer] = None

    def init_producer(self) -> None:
        while True:
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=settings.kafka_broker,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    acks="all",
                    # Add connection stability settings
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

    def send_status(
        self,
        audit_id: str,
        status: str,
        error: Optional[str] = None,
        total_chunks: Optional[int] = None,
    ) -> None:
        if not self._producer:
            logger.warning("Producer not initialized, cannot send status for audit %s", audit_id)
            return
        msg: dict = {"audit_id": audit_id, "status": status}
        if error:
            msg["error"] = error
        if total_chunks is not None:
            msg["total_chunks"] = total_chunks
        try:
            self._producer.send(settings.audit_status_topic, value=msg)
            self._producer.flush()
            logger.info("Successfully sent status %s for audit %s", status, audit_id)
        except Exception as e:
            logger.exception("Failed to send status for audit %s: %s", audit_id, e)

    def send_audit_tasks(self, audit_id: str, points: list, lang: str = "python") -> int:
        """Send audit tasks to Kafka for processing.

        Uses audit_id as message key to ensure all chunks for a single audit are
        delivered to the same partition, maintaining ordering and allowing
        parallel processing of different audits across multiple worker replicas.

        Raises KafkaPublishError unless every task is acknowledged. A partial
        publish leaves total_chunks larger than the messages the worker will
        see, and the audit never reaches completed.
        """
        if not self._producer:
            raise KafkaPublishError(audit_id, "Producer not initialized")
        total = len(points)
        futures = []
        for i, point in enumerate(points):
            task = {
                "chunk_id": point.payload["chunk_id"],
                "code": point.payload["code"],
                "file_path": point.payload["file_path"],
                "audit_id": audit_id,
                "lang": point.payload.get("lang", lang),
                "chunk_index": i,
                "total_chunks": total,
            }
            try:
                futures.append(self._producer.send(
                    settings.audit_tasks_topic,
                    value=task,
                    key=audit_id.encode("utf-8"),
                ))
            except Exception as e:
                raise KafkaPublishError(
                    audit_id, f"Failed to send audit task {i}: {e}"
                ) from e
        try:
            self._producer.flush()
            for i, future in enumerate(futures):
                future.get(timeout=30)
        except Exception as e:
            raise KafkaPublishError(
                audit_id, f"Audit tasks were not fully acknowledged: {e}"
            ) from e
        logger.info("Successfully sent %d audit tasks for audit %s", total, audit_id)
        return total

    def consumer_settings(self) -> dict:
        """Offset policy for repo.parsed.

        earliest + manual commit: a new group reads the backlog, and a failed
        handler does not advance the committed offset.
        """
        return {
            "auto_offset_reset": "earliest",
            "enable_auto_commit": False,
            "max_poll_records": 1,
        }

    def consume(self, topic: str, on_message: Callable) -> None:
        max_attempts = 3
        consumer = None
        while consumer is None:
            try:
                consumer = KafkaConsumer(
                    topic,
                    bootstrap_servers=settings.kafka_broker,
                    group_id=settings.consumer_group,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    **self.consumer_settings(),
                )
                logger.info("Listening to topic '%s'", topic)
            except Exception:
                logger.warning("Kafka not available, retrying in 5 seconds...")
                time.sleep(5)

        logger.info("Waiting for messages...")
        attempts: dict[tuple, int] = {}
        while True:
            batches = consumer.poll(timeout_ms=1000, max_records=1)
            for tp, messages in batches.items():
                for message in messages:
                    key = (tp.partition, message.offset)
                    try:
                        on_message(message)
                        consumer.commit()
                        attempts.pop(key, None)
                    except Exception as e:
                        attempts[key] = attempts.get(key, 0) + 1
                        logger.exception(
                            "Error processing repo message (attempt %s/%s)",
                            attempts[key],
                            max_attempts,
                        )
                        if attempts[key] >= max_attempts:
                            audit_id = getattr(e, "audit_id", None)
                            if audit_id is None and isinstance(message.value, dict):
                                audit_id = message.value.get("audit_id")
                            if audit_id:
                                self.send_status(audit_id, "failed", error=str(e))
                            consumer.commit()
                            attempts.pop(key, None)
                        else:
                            consumer.seek(tp, message.offset)
                            time.sleep(5)
