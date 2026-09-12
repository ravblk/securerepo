class AuditWorkerError(Exception):
    """Base exception for audit worker errors."""
    pass


class LLMConnectionError(AuditWorkerError):
    """Exception raised when LLM connection fails."""
    pass


class EmbeddingServiceError(AuditWorkerError):
    """Exception raised when embedding service fails."""
    pass


class DatabaseError(AuditWorkerError):
    """Exception raised when database operations fail."""
    pass


class QdrantError(AuditWorkerError):
    """Exception raised when Qdrant operations fail."""
    pass


class KafkaError(AuditWorkerError):
    """Exception raised when Kafka operations fail."""
    pass


class WorkflowError(AuditWorkerError):
    """Exception raised when workflow processing fails."""
    pass


class ValidationError(AuditWorkerError):
    """Exception raised when validation fails."""
    pass
