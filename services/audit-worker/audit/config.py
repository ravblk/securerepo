import os
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Settings:
    # Kafka Configuration
    kafka_broker: str = os.getenv("KAFKA_BROKER", "kafka:9092")
    audit_tasks_topic: str = "audit.tasks"
    audit_status_topic: str = "audit.status"
    audit_group: str = "audit-worker"
    kafka_timeout_seconds: int = 30

    # Qdrant Configuration
    qdrant_url: str = os.getenv("QDRANT_URL", "http://qdrant:6333")

    # Embedding Service Configuration
    embedding_url: str = os.getenv("EMBEDDING_URL", "http://embedding:8080/embed")
    embedding_timeout_seconds: int = 30
    embedding_size: int = 1024

    # Database Configuration
    postgres_url: str = os.getenv("POSTGRES_URL", "postgresql://securerepo:securerepo_pass@postgres:5432/securerepo")

    # LLM Configuration
    foundation_models_url: str = os.getenv("FOUNDATION_MODELS_URL", "https://foundation-models.api.cloud.ru/v1")
    foundation_models_api_key: str = os.getenv("FOUNDATION_MODELS_API_KEY", "none")
    llm_model: str = os.getenv("LLM_MODEL", "Qwen/Qwen3-Coder-Next")
    llm_timeout: int = 120
    llm_temperature: float = 0.0
    llm_max_retries: int = 3

    # Service Configuration
    app_name: str = "Audit Worker"
    app_version: str = "1.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8003

    # Processing Configuration
    max_code_length: int = 5000
    max_retries: int = 3
    retry_delay_seconds: int = 5

    # Langfuse Configuration
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "http://langfuse:3090")
    langfuse_enabled: bool = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


settings = Settings()
