import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from .config import settings
from .retry_service import RetryService
from .exceptions import QdrantError

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for Qdrant vector database operations with retry logic."""

    def __init__(self, url: str = settings.qdrant_url) -> None:
        self._url = url
        self._client: Optional[QdrantClient] = None
        self._retry_service = RetryService()
        self._init_client()
        self._ensure_collection()

    def _init_client(self) -> None:
        """Initialize QdrantClient with retry logic."""
        def init_func():
            return QdrantClient(url=self._url, timeout=30)

        try:
            self._client = self._retry_service.execute_with_retry(
                init_func,
                name="QdrantClient init"
            )
            logger.info(f"Qdrant client initialized at {self._url}")
        except Exception as e:
            raise QdrantError(f"Failed to initialize Qdrant client: {str(e)}")

    def _ensure_collection(self) -> None:
        """Ensure the collection exists with retry logic."""
        def ensure_func():
            collections = self._client.get_collections().collections
            collection_names = [c.name for c in collections]

            if settings.collection_name not in collection_names:
                logger.info(f"Creating collection '{settings.collection_name}' (size={settings.vector_size})")
                self._client.create_collection(
                    collection_name=settings.collection_name,
                    vectors_config=VectorParams(
                        size=settings.vector_size,
                        distance=Distance.COSINE
                    )
                )
            else:
                logger.info(f"Collection '{settings.collection_name}' already exists")

        try:
            self._retry_service.execute_with_retry(
                ensure_func,
                name="ensure_collection"
            )
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            # Don't raise - collection might exist already

    def upsert_points(self, points: list[PointStruct]) -> None:
        """Upsert points into Qdrant with retry logic."""
        if not points:
            logger.warning("No points to upsert")
            return

        def upsert_func():
            return self._client.upsert(
                collection_name=settings.collection_name,
                points=points,
                wait=True,
            )

        try:
            self._retry_service.execute_with_retry(
                upsert_func,
                name=f"upsert {len(points)} points"
            )
            logger.info(f"Successfully upsert {len(points)} points to Qdrant")
        except Exception as e:
            error_msg = f"Failed to upsert points: {e}"
            logger.error(error_msg)
            raise QdrantError(error_msg)

    def check_health(self) -> tuple[bool, str]:
        """Check Qdrant health."""
        try:
            self._client.get_collections()
            return True, "Qdrant reachable"
        except Exception as e:
            message = f"Qdrant health check failed: {str(e)}"
            logger.warning(message)
            return False, message

    def get_client(self) -> QdrantClient:
        """Get the Qdrant client instance."""
        return self._client

    @property
    def is_available(self) -> bool:
        """Check if Qdrant is available."""
        available, _ = self.check_health()
        return available
