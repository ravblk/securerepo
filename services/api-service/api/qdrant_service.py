import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from .config import settings
from .exceptions import IntegrationError

logger = logging.getLogger(__name__)
qdrant_service_instance: Optional["QdrantService"] = None


class QdrantService:
    """Service for Qdrant vector database operations."""

    def __init__(self, url: str = settings.qdrant_url) -> None:
        global qdrant_service_instance
        self._client = QdrantClient(url=url)
        qdrant_service_instance = self
        self._ensure_collections()

    def _ensure_collections(self) -> None:
        """Ensure all required collections exist in Qdrant."""
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                existing = {c.name for c in self._client.get_collections().collections}

                for collection in settings.qdrant_collections:
                    if collection not in existing:
                        self._client.create_collection(
                            collection_name=collection,
                            vectors_config=VectorParams(
                                size=settings.embedding_size,
                                distance=Distance.COSINE
                            )
                        )
                        logger.info(f"Created Qdrant collection: {collection}")
                    else:
                        logger.info(f"Qdrant collection already exists: {collection}")

                logger.info("Qdrant initialized successfully")
                return  # Success, exit the retry loop

            except Exception as e:
                connection_error = "Connection refused" in str(e) or "111" in str(e)

                if attempt < max_retries - 1 and connection_error:
                    logger.warning(
                        f"Qdrant connection attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    import time
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to initialize Qdrant collections after {max_retries} attempts: {e}")
                    # Don't raise exception, just log. Service will continue without Qdrant initialized
                    logger.warning("Service will continue without Qdrant collections initialized.")
                    return

    def get_client(self) -> QdrantClient:
        """Get the Qdrant client instance."""
        return self._client

    @property
    def client(self) -> QdrantClient:
        """Get the Qdrant client instance (property access)."""
        return self._client


def get_qdrant_service() -> Optional[QdrantService]:
    """Get or create the singleton Qdrant service instance."""
    global qdrant_service_instance
    return qdrant_service_instance