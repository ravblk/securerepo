from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class SeedNotFoundError(HTTPException):
    """Exception raised when seed operation is not found."""

    def __init__(self, detail: str = "Seed not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ScrapingError(HTTPException):
    """Exception raised when web scraping fails."""

    def __init__(self, detail: str = "Web scraping failed"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


class EmbeddingServiceError(HTTPException):
    """Exception raised when embedding service fails."""

    def __init__(self, detail: str = "Embedding service failed"):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


class QdrantError(HTTPException):
    """Exception raised when Qdrant operations fail."""

    def __init__(self, detail: str = "Qdrant operation failed"):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


class ContentQualityError(HTTPException):
    """Exception raised when scraped content fails quality validation."""

    def __init__(self, detail: str = "Content quality validation failed"):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def register_exception_handlers(app):
    """Register custom exception handlers for the FastAPI app."""

    @app.exception_handler(SeedNotFoundError)
    async def seed_not_found_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.detail}
        )

    @app.exception_handler(ScrapingError)
    async def scraping_error_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": exc.detail}
        )

    @app.exception_handler(EmbeddingServiceError)
    async def embedding_error_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": exc.detail}
        )

    @app.exception_handler(QdrantError)
    async def qdrant_error_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": exc.detail}
        )

    @app.exception_handler(ContentQualityError)
    async def content_quality_error_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.detail}
        )
