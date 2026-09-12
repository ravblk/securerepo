"""
FastAPI application for Internal Rules Ingestion with modular components.
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query

from ingestion.config import settings
from ingestion.models import (
    SyncRequest,
    SyncResponse,
    SyncStatus,
    HealthResponse,
    ServiceInfoResponse
)
from ingestion.sync_controller import SyncController
from ingestion.qdrant_service import QdrantService
from ingestion.content_service import ContentService
from ingestion.embedding_service import EmbeddingService
from ingestion.exceptions import (
    register_exception_handlers,
    SyncNotFoundError
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Global service instances
qdrant_service: Optional[QdrantService] = None
content_service: Optional[ContentService] = None
embedding_service: Optional[EmbeddingService] = None
sync_controller: Optional[SyncController] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    global qdrant_service, content_service, embedding_service, sync_controller

    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Initialize content service
    try:
        content_service = ContentService()
        logger.info("Content service initialized successfully")
    except Exception as e:
        logger.warning(f"Content service initialization failed: {e}. Will retry on demand.")

    # Initialize embedding service
    try:
        embedding_service = EmbeddingService()
        logger.info("Embedding service initialized successfully")
    except Exception as e:
        logger.warning(f"Embedding service initialization failed: {e}. Will retry on demand.")

    # Initialize Qdrant service
    try:
        qdrant_service = QdrantService()
        logger.info("Qdrant service initialized successfully")
    except Exception as e:
        logger.warning(f"Qdrant service initialization failed: {e}. Will retry on demand.")

    # Initialize sync controller
    try:
        sync_controller = SyncController(qdrant_service, content_service, embedding_service)
        logger.info("Sync controller initialized successfully")
    except Exception as e:
        logger.warning(f"Sync controller initialization failed: {e}. Will retry on demand.")

    logger.info(f"{settings.app_name} started successfully")
    logger.info(f"Max workers: {settings.max_workers}")
    logger.info(f"Collection name: {settings.collection_name}")

    yield

    # Cleanup
    logger.info("Shutting down...")


# FastAPI app setup
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# Register custom exception handlers
register_exception_handlers(app)


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint."""
    health_status = sync_controller.get_health_status()
    return HealthResponse(
        status=health_status["status"],
        qdrant=health_status["qdrant"],
        qdrant_url=settings.qdrant_url
    )


@app.get("/", response_model=ServiceInfoResponse)
def root():
    """Service information endpoint."""
    return ServiceInfoResponse(
        service=settings.app_name,
        version=settings.app_version,
        storage="Qdrant",
        max_workers=settings.max_workers
    )


@app.post("/sync/start", response_model=SyncResponse)
def start_sync(request: SyncRequest = SyncRequest()):
    """Start the internal rules sync process."""
    try:
        pages_json = request.space_key or settings.pages_json
        sync_id = sync_controller.start_sync(pages_json)

        message = f"Sync started for sync_id: {sync_id}"
        if request.space_key:
            message += f" (space_key={request.space_key})"

        logger.info(f"Started sync {sync_id}")

        return SyncResponse(
            sync_id=sync_id,
            status="started",
            message=message
        )

    except Exception as e:
        logger.error(f"Failed to start sync: {e}")
        raise


@app.get("/sync/{sync_id}/status")
def get_sync_status(sync_id: str):
    """Get status of a specific sync operation."""
    status = sync_controller.get_sync_status(sync_id)
    if status is None:
        raise SyncNotFoundError(f"Sync ID {sync_id} not found")
    return status


@app.get("/sync/history")
def get_sync_history(limit: int = Query(default=10, ge=1, le=100)):
    """Get sync operation history."""
    items = sync_controller.get_sync_history(limit)
    return {"items": items}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")
