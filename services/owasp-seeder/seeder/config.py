import os
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Settings:
    # Service Configuration
    app_name: str = "OWASP Seeder"
    app_version: str = "2.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8004

    # Qdrant Configuration
    qdrant_url: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
    collection_name: str = "general_best_practices"
    embedding_size: int = 1024

    # Embedding Service Configuration
    embedding_url: str = os.getenv("EMBEDDING_URL", "http://embedding:8080")
    embedding_timeout: int = 120

    # Web Scraping Configuration
    pages_json: str = os.getenv("PAGES_JSON", "[]")
    max_text_length: int = 10000
    request_timeout: int = 30
    user_agent: str = "Mozilla/5.0 (compatible; OWASP-Seeder/2.0)"

    # Nested Page Scanning Configuration
    enable_nested_scanning: bool = os.getenv("ENABLE_NESTED_SCANNING", "true").lower() in ("true", "1", "yes")
    max_depth: int = int(os.getenv("MAX_DEPTH", "1"))  # Maximum depth for nested pages
    max_pages_per_domain: int = int(os.getenv("MAX_PAGES_PER_DOMAIN", "50"))  # Limit to prevent DoS
    follow_external_links: bool = os.getenv("FOLLOW_EXTERNAL_LINKS", "false").lower() in ("true", "1", "yes")

    # Allowed domains for nested scanning
    allowed_domains: List[str] = None
    internal_url_patterns: List[str] = None  # Additional patterns for internal URLs

    def __post_init__(self):
        # Set default for frozenset
        if self.allowed_domains is None:
            object.__setattr__(
                self, 'allowed_domains',
                frozenset({"owasp.org", "cwe.mitre.org", "owasp.org/www-project-cwe"})
            )
        # Set default for internal URL patterns
        if self.internal_url_patterns is None:
            object.__setattr__(
                self, 'internal_url_patterns',
                frozenset({"owasp.org", "owasp.org/www-project-", "cwe.mitre.org"})
            )


settings = Settings()
