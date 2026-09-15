import logging
import uuid
from datetime import datetime
from typing import Optional

from qdrant_client.models import PointStruct

from .config import settings
from .models import Page
from .qdrant_service import QdrantService
from .content_service import ContentService
from .embedding_service import EmbeddingService
from .exceptions import ProcessingError

logger = logging.getLogger(__name__)


class SyncController:
    """Controller for internal rules synchronization operations."""

    def __init__(
        self,
        qdrant_service: QdrantService,
        content_service: ContentService,
        embedding_service: EmbeddingService
    ):
        self._qdrant_service = qdrant_service
        self._content_service = content_service
        self._embedding_service = embedding_service
        self._sync_status: dict = {}

    def start_sync(self, pages_json: Optional[str] = None) -> str:
        """Start the sync process."""
        sync_id = str(uuid.uuid4())

        # Use provided pages_json or fall back to settings
        pages_source = pages_json or settings.pages_json
        pages = self._content_service.get_pages_from_json(pages_source)

        self._sync_status[sync_id] = {
            "sync_id": sync_id,
            "status": "running",
            "pages_processed": 0,
            "pages_failed": 0,
            "pages_total": len(pages),
            "started_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Sync {sync_id} started for {len(pages)} pages")

        try:
            points = self._process_pages(pages, sync_id)

            if points:
                self._qdrant_service.upsert_points(points)

            self._sync_status[sync_id]["status"] = "completed"
            self._sync_status[sync_id]["completed_at"] = datetime.utcnow().isoformat()

            processed = self._sync_status[sync_id]["pages_processed"]
            failed = self._sync_status[sync_id]["pages_failed"]

            logger.info(
                f"Sync {sync_id} completed: "
                f"processed={processed}, failed={failed}"
            )

        except Exception as e:
            self._sync_status[sync_id]["status"] = "failed"
            self._sync_status[sync_id]["error"] = str(e)
            self._sync_status[sync_id]["completed_at"] = datetime.utcnow().isoformat()
            logger.error(f"Sync {sync_id} failed: {e}")
            raise ProcessingError(f"Sync failed: {str(e)}")

        return sync_id

    def _process_pages(self, pages: list[dict], sync_id: str) -> list[PointStruct]:
        """Process pages sequentially, like owasp-seeder."""
        points: list[PointStruct] = []

        for idx, page in enumerate(pages):
            try:
                point = self._process_page(page, idx)
                if point:
                    points.append(point)
                    self._sync_status[sync_id]["pages_processed"] += 1
                    logger.info(f"✓ Processed page {idx + 1}/{len(pages)}: {page.get('title', 'Unknown')}")
                else:
                    self._sync_status[sync_id]["pages_failed"] += 1
                    logger.warning(f"✗ Failed to process page {idx + 1}/{len(pages)}: {page.get('url', 'Unknown')}")

            except Exception as e:
                error_msg = f"Failed to process page {page.get('url')}: {e}"
                logger.error(error_msg)
                self._sync_status[sync_id]["pages_failed"] += 1

        return points

    def _process_page(self, page: dict, idx: int) -> Optional[PointStruct]:
        """Process a single page and create a Qdrant point, like owasp-seeder."""
        url = page.get("url")
        title = page.get("title", f"Page {page.get('id')}")

        logger.info(f"Processing page {idx}: {title} from {url}")

        try:
            # Get text content
            text = self._content_service.get_text_from_url(url)
            if not text:
                logger.warning(f"Failed to extract text from {url}")
                return None

            # Get embedding
            embedding = self._embedding_service.get_embedding(text)
            if not embedding:
                logger.warning(f"Failed to get embedding for {url}")
                return None

            # Create point
            point = PointStruct(
                id=page.get("id"),
                vector=embedding,
                payload={
                    "title": title,
                    "url": url,
                    "text": text[:settings.text_limit],
                    "source": "gitlab-handbook",
                    "ingested_at": datetime.utcnow().isoformat(),
                }
            )

            logger.info(f"Successfully processed: {title[:50]}")
            return point

        except Exception as e:
            logger.error(f"Error processing page {page.get('url')}: {e}")
            raise ProcessingError(f"Failed to process page: {str(e)}")

    def get_sync_status(self, sync_id: str) -> Optional[dict]:
        """Get status of a sync operation."""
        return self._sync_status.get(sync_id)

    def get_sync_history(self, limit: int = 10) -> list:
        """Get sync operation history."""
        items = list(self._sync_status.values())
        items.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return items[:limit]

    def get_health_status(self) -> dict:
        """Get comprehensive health status."""
        qdrant_healthy, qdrant_message = self._qdrant_service.check_health()
        embedding_healthy, embedding_message = self._embedding_service.test_connection()

        return {
            "status": "healthy" if qdrant_healthy and embedding_healthy else "degraded",
            "qdrant": "reachable" if qdrant_healthy else "unreachable",
            "qdrant_message": qdrant_message,
            "embedding": "available" if embedding_healthy else "unavailable",
            "embedding_message": embedding_message,
            "qdrant_url": settings.qdrant_url,
        }
