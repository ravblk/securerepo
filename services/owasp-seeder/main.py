"""
FastAPI application for OWASP Seeder with modular components.
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from seeder.config import settings
from seeder.models import (
    SeedRequest,
    SeedResponse,
    HealthResponse,
    ServiceInfoResponse
)
from seeder.seed_controller import SeedController
from seeder.web_scraper import WebScraper
from seeder.embedding_service import EmbeddingService
from seeder.qdrant_service import QdrantService
from seeder.exceptions import (
    register_exception_handlers,
    SeedNotFoundError
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Global service instances
web_scraper: Optional[WebScraper] = None
embedding_service: Optional[EmbeddingService] = None
qdrant_service: Optional[QdrantService] = None
seed_controller: Optional[SeedController] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    global web_scraper, embedding_service, qdrant_service, seed_controller

    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Initialize web scraper
    try:
        web_scraper = WebScraper()
        logger.info("Web scraper initialized successfully")
    except Exception as e:
        logger.warning(f"Web scraper initialization failed: {e}. Will retry on demand.")

    # Initialize embedding service
    try:
        embedding_service = EmbeddingService()
        available, message = embedding_service.test_connection()
        if not available:
            logger.warning(f"Embedding service initialization warning: {message}")
        else:
            logger.info("Embedding service initialized successfully")
    except Exception as e:
        logger.warning(f"Embedding service initialization failed: {e}. Will retry on demand.")

    # Initialize Qdrant service
    try:
        qdrant_service = QdrantService()
        logger.info("Qdrant service initialized successfully")
    except Exception as e:
        logger.warning(f"Qdrant service initialization failed: {e}. Will retry on demand.")

    # Initialize seed controller
    try:
        seed_controller = SeedController(web_scraper, embedding_service, qdrant_service)
        logger.info("Seed controller initialized successfully")
    except Exception as e:
        logger.warning(f"Seed controller initialization failed: {e}. Will retry on demand.")

    logger.info(f"{settings.app_name} started successfully")
    logger.info(f"Nested scanning enabled: {settings.enable_nested_scanning}")
    logger.info(f"Max depth: {settings.max_depth}")
    logger.info(f"Max pages per domain: {settings.max_pages_per_domain}")

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
    return HealthResponse(status="healthy", service=settings.app_name)


@app.get("/", response_model=ServiceInfoResponse)
def root():
    """Service information endpoint."""
    return ServiceInfoResponse(
        service=settings.app_name,
        version=settings.app_version,
        storage="Qdrant",
        nested_scanning_enabled=settings.enable_nested_scanning,
        max_depth=settings.max_depth
    )


@app.post("/seed/start", response_model=SeedResponse)
def start_seed(request: SeedRequest = SeedRequest()):
    """Start the OWASP seeding process."""
    try:
        seed_id = seed_controller.start_seed(request)
        logger.info(f"Started seed {seed_id}")

        message = f"Seeding started with maximum depth {request.max_depth or settings.max_depth}"
        if settings.enable_nested_scanning:
            message += " (nested scanning enabled)"

        return SeedResponse(
            seed_id=seed_id,
            status="started",
            message=message
        )

    except Exception as e:
        logger.error(f"Failed to start seed: {e}")
        raise


@app.get("/seed/{seed_id}/status")
def get_seed_status(seed_id: str):
    """Get status of a specific seed operation."""
    status = seed_controller.get_seed_status(seed_id)
    if status is None:
        raise SeedNotFoundError(f"Seed ID {seed_id} not found")
    return status


@app.get("/seed/history")
def get_seed_history(limit: int = 10):
    """Get seed operation history."""
    items = seed_controller.get_seed_history(limit)
    return {"items": items}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")
