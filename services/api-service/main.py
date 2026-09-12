"""
FastAPI application for SecureRepo security audit service.
Refactored to use modular components.
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.models import (
    AuditStartRequest,
    AuditStatusResponse,
    AuditReportResponse
)
from api.database import init_database, update_audit_status
from api.audit_controller import AuditController
from api.kafka_service import KafkaService
from api.qdrant_service import QdrantService
from api.exceptions import (
    AuditNotFoundError,
    AccessDeniedError,
    register_exception_handlers
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global dependencies
kafka_service: Optional[KafkaService] = None
qdrant_service: Optional[QdrantService] = None
audit_controller: Optional[AuditController] = None


def handle_status_update(status_data: dict):
    """Handle audit status update from Kafka."""
    audit_id = status_data.get("audit_id")
    status = status_data.get("status")

    if audit_id and status:
        try:
            update_audit_status(audit_id, status)
            logger.info(f"Updated audit {audit_id} to {status}")
        except Exception as e:
            logger.error(f"Failed to update audit status for {audit_id}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    global kafka_service, qdrant_service, audit_controller

    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Initialize database (with graceful fallback)
    try:
        init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}. Service will start anyway.")

    # Initialize Kafka (with graceful fallback)
    try:
        kafka_service = KafkaService()
        kafka_service.init()
        logger.info("Kafka initialized successfully")
    except Exception as e:
        logger.warning(f"Kafka initialization failed: {e}. Service will start anyway.")
        kafka_service = KafkaService()  # Create instance anyway for later retry

    # Initialize Qdrant (with graceful fallback)
    try:
        qdrant_service = QdrantService()
        logger.info("Qdrant client initialized successfully")
    except Exception as e:
        logger.warning(f"Qdrant initialization failed: {e}. Service will start anyway.")
        qdrant_service = QdrantService()  # Create instance anyway for later retry

    # Initialize audit controller (with graceful fallback)
    try:
        audit_controller = AuditController(kafka_service)
        kafka_service.start_status_consumer(handle_status_update)
        logger.info("Audit controller initialized successfully")
    except Exception as e:
        logger.warning(f"Audit controller initialization failed: {e}. Service will start anyway.")

    logger.info(f"{settings.app_name} started successfully")
    yield

    # Cleanup (if needed)
    logger.info("Shutting down...")


# FastAPI app setup
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom exception handlers
register_exception_handlers(app)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.app_name}


@app.get("/init")
def init():
    """Manual initialization of dependencies."""
    logger.info("Manual initialization triggered")
    return {"status": "initialized"}


@app.post("/audit/start", response_model=dict)
def start_audit(request: AuditStartRequest):
    """Start a new security audit."""
    try:
        return audit_controller.start_audit(request)
    except Exception as e:
        logger.error(f"Failed to start audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit", response_model=dict)
def get_audits_list(
    user_id: str = Query(..., description="User ID from frontend"),
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
):
    """Get list of audits for a user."""
    try:
        return audit_controller.get_audits_list(user_id, status, limit, offset)
    except Exception as e:
        logger.error(f"Failed to list audits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit/{audit_id}/status", response_model=AuditStatusResponse)
def get_audit_status(audit_id: str, user_id: str = Query(..., description="User ID from frontend")):
    """Get status of a specific audit."""
    try:
        return audit_controller.get_audit_status(audit_id, user_id)
    except (AuditNotFoundError, AccessDeniedError):
        raise
    except Exception as e:
        logger.error(f"Failed to get audit status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit/{audit_id}/report", response_model=AuditReportResponse)
def audit_report(audit_id: str, user_id: str = Query(..., description="User ID from frontend")):
    """Get detailed report for a completed audit."""
    try:
        return audit_controller.get_audit_report(audit_id, user_id)
    except (AuditNotFoundError, AccessDeniedError):
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate audit report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
