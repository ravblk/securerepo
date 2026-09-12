import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    kafka_broker: str = os.getenv("KAFKA_BROKER", "kafka:9092")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
    embedding_url: str = os.getenv("EMBEDDING_URL", "http://embedding:8080")

    collection_name: str = "code_repo"
    embedding_size: int = 1024
    embedding_timeout_sec: int = 120

    repo_parsed_topic: str = "repo.parsed"
    audit_tasks_topic: str = "audit.tasks"
    audit_status_topic: str = "audit.status"
    consumer_group: str = "indexer-group"

    clone_root: str = "/tmp/repos"
    max_code_length: int = 5000
    max_walk_depth: int = 10
    skip_dirs: frozenset = frozenset({".git", "__pycache__"})

    api_host: str = "0.0.0.0"
    api_port: int = 8002


settings = Settings()
