from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class AuditNotFoundError(HTTPException):
    """Exception raised when audit is not found."""

    def __init__(self, detail: str = "Audit not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class AccessDeniedError(HTTPException):
    """Exception raised when access is denied."""

    def __init__(self, detail: str = "Access denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class DatabaseError(HTTPException):
    """Exception raised for database errors."""

    def __init__(self, detail: str = "Database error"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


class IntegrationError(HTTPException):
    """Exception raised for integration errors (Kafka, Qdrant, etc.)."""

    def __init__(self, detail: str = "Integration error"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def register_exception_handlers(app):
    """Register custom exception handlers for the FastAPI app."""

    @app.exception_handler(AuditNotFoundError)
    async def audit_not_found_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.detail}
        )

    @app.exception_handler(AccessDeniedError)
    async def access_denied_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.detail}
        )

    @app.exception_handler(DatabaseError)
    async def database_error_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": exc.detail}
        )

    @app.exception_handler(IntegrationError)
    async def integration_error_handler(request, exc):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": exc.detail}
        )
