import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from .config import settings
from .exceptions import QdrantError

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for Qdrant vector database operations."""

    def __init__(self, url: str = settings.qdrant_url) -> None:
        self._client = QdrantClient(url=url)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Ensure collection exists in Qdrant."""
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                existing = {c.name for c in self._client.get_collections().collections}
                collection_names = existing

                if settings.collection_name not in collection_names:
                    self._client.create_collection(
                        collection_name=settings.collection_name,
                        vectors_config=VectorParams(
                            size=settings.embedding_size,
                            distance=Distance.COSINE
                        )
                    )
                    logger.info(f"Created Qdrant collection: {settings.collection_name}")
                else:
                    logger.info(f"Qdrant collection already exists: {settings.collection_name}")

                logger.info("Qdrant connection verified successfully")
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
                    error_msg = f"Failed to connect to Qdrant after {max_retries} attempts: {e}"
                    logger.error(error_msg)
                    raise QdrantError(error_msg)

    def upsert_points(self, points: list[PointStruct]) -> None:
        """Upsert points to Qdrant collection."""
        try:
            self._client.upsert(
                collection_name=settings.collection_name,
                points=points
            )
            logger.info(f"Successfully upsert {len(points)} points to Qdrant")
        except Exception as e:
            error_msg = f"Qdrant upsert failed: {e}"
            logger.error(error_msg)
            raise QdrantError(error_msg)

    def test_connection(self) -> tuple[bool, str]:
        """Test Qdrant connection."""
        try:
            collections = self._client.get_collections()
            collection_names = [c.name for c in collections.collections]
            return True, f"Qdrant connected, {len(collection_names)} collections available"
        except Exception as e:
            return False, f"Qdrant connection failed: {str(e)}"

    def is_available(self) -> bool:
        """Check if Qdrant is available."""
        available, _ = self.test_connection()
        return available

    def get_client(self):
        """Get the Qdrant client instance."""
        return self._client
