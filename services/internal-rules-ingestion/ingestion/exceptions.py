from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class SyncNotFoundError(HTTPException):
    """Exception raised when sync operation is not found."""

    def __init__(self, detail: str = "Sync not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ContentFetchError(HTTPException):
    """Exception raised when content fetching fails."""

    def __init__(self, detail: str = "Content fetch failed"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


class EmbeddingServiceError(HTTPException):
    """Exception raised when embedding service fails."""

    def __init__(self, detail: str = "Embedding service failed"):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


class QdrantError(HTTPException):
    """Exception raised when Qdrant operations fail."""

    def __init__(self, detail: str = "Qdrant operation failed"):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


class ProcessingError(HTTPException):
    """Exception raised when page processing fails."""

    def __init__(self, detail: str = "Page processing failed"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def register_exception_handlers(app):
    """Register custom exception handlers for the FastAPI app."""

    @app.exception_handler(SyncNotFoundError)
    async def sync_not_found_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.detail}
        )

    @app.exception_handler(ContentFetchError)
    async def content_fetch_error_handler(request, exc):
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

    @app.exception_handler(ProcessingError)
    async def processing_error_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": exc.detail}
        )
