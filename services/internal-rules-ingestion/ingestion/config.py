import os
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Settings:
    # Service Configuration
    app_name: str = "Internal Rules Ingestion"
    app_version: str = "2.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8001

    # Qdrant Configuration
    qdrant_url: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
    collection_name: str = "internal_policies"
    vector_size: int = 1024

    # Embedding Service Configuration
    embedding_url: str = os.getenv("EMBEDDING_URL", "http://embedding:8080")
    embedding_timeout: int = 120
    text_limit: int = 10000

    # Content Source Configuration
    pages_json: str = os.getenv("PAGES_JSON", "[]")
    request_timeout: int = 30

    # Confluence Configuration (for future use)
    confluence_url: str = os.getenv("CONFLUENCE_URL", "")
    confluence_user: str = os.getenv("CONFLUENCE_USER", "")
    confluence_api_token: str = os.getenv("CONFLUENCE_API_TOKEN", "")
    confluence_space_key: str = os.getenv("CONFLUENCE_SPACE_KEY", "")

    # Processing Configuration
    max_workers: int = int(os.getenv("MAX_WORKERS", "8"))

    # Retry Configuration
    qdrant_max_retries: int = int(os.getenv("QDRANT_MAX_RETRIES", "5"))
    qdrant_backoff_base: float = float(os.getenv("QDRANT_BACKOFF_BASE", "1.0"))
    qdrant_backoff_max: float = float(os.getenv("QDRANT_BACKOFF_MAX", "30.0"))

    http_max_retries: int = int(os.getenv("HTTP_MAX_RETRIES", "3"))
    http_backoff_base: float = float(os.getenv("HTTP_BACKOFF_BASE", "1.0"))
    http_backoff_max: float = float(os.getenv("HTTP_BACKOFF_MAX", "10.0"))


settings = Settings()
