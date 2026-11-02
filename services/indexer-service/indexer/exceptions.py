class IndexerError(Exception):
    """Base error for indexing failures that should be retried."""

    def __init__(self, audit_id: str, message: str) -> None:
        self.audit_id = audit_id
        super().__init__(message)


class IndexingError(IndexerError):
    """Retryable failure while embedding, storing, or publishing an audit."""


class KafkaPublishError(IndexerError):
    """Not every audit task was acknowledged by Kafka."""
