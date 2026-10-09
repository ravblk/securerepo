import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Settings:
    # Kafka Configuration
    kafka_broker: str = os.getenv("KAFKA_BROKER", "kafka:9092")
    repo_parsed_topic: str = "repo.parsed"
    audit_tasks_topic: str = "audit.tasks"
    audit_status_topic: str = "audit.status"

    # Qdrant Configuration
    qdrant_url: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
    qdrant_collections: List[str] = None
    embedding_size: int = 1024

    # Database Configuration
    postgres_url: str = os.getenv("POSTGRES_URL", "postgresql://securerepo:securerepo_pass@postgres:5432/securerepo")

    # Keycloak Configuration
    keycloak_url: str = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
    keycloak_realm: str = os.getenv("KEYCLOAK_REALM", "securerepo")
    keycloak_audience: Optional[str] = os.getenv("KEYCLOAK_CLIENT_ID", "securerepo-api") or None

    # Application Configuration
    app_name: str = "SecureRepo API"
    app_version: str = "1.0.0"

    # Timeout Configuration
    kafka_timeout_seconds: int = 30
    db_connection_timeout_seconds: int = 10

    # SSE Configuration
    sse_enabled: bool = os.getenv("SSE_ENABLED", "true").lower() == "true"
    sse_heartbeat_interval: int = int(os.getenv("SSE_HEARTBEAT_INTERVAL", "15"))
    sse_cleanup_interval: int = int(os.getenv("SSE_CLEANUP_INTERVAL", "300"))
    sse_max_subscribers: int = int(os.getenv("SSE_MAX_SUBSCRIBERS", "100"))
    sse_max_subscribers_per_audit: int = int(os.getenv("SSE_MAX_SUBSCRIBERS_PER_AUDIT", "10"))

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Error Messages
    error_audit_not_found: str = "Audit not found"
    error_access_denied: str = "Access denied"
    error_audit_not_completed: str = "Audit not completed yet"

    def __post_init__(self):
        # Set default for frozenset
        if self.qdrant_collections is None:
            object.__setattr__(self, 'qdrant_collections', frozenset({
                "internal_policies",
                "general_best_practices",
                "code_repo"
            }))


settings = Settings()
