"""
FastAPI application for SecureRepo security audit service.
Refactored to use modular components.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

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
from api.auth import get_current_user, validate_token_manual

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global dependencies
kafka_service: Optional[KafkaService] = None
qdrant_service: Optional[QdrantService] = None
audit_controller: Optional[AuditController] = None


def handle_status_update(status_data: dict):
    """Handle audit status update from Kafka with SSE broadcast."""
    from api.sse_manager import sse_manager

    audit_id = status_data.get("audit_id")
    status = status_data.get("status")

    if audit_id and status:
        try:
            # Update database (existing)
            update_audit_status(audit_id, status)
            logger.info(f"Updated audit {audit_id} to {status}")

            # Broadcast to SSE subscribers (NEW)
            try:
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(
                    sse_manager.broadcast(audit_id, status_data),
                    loop
                )
                logger.info(f"Broadcasted status update for audit {audit_id}")
            except Exception as e:
                logger.error(f"Failed to broadcast SSE update: {e}")

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

    # Start SSE cleanup task
    from api.sse_manager import sse_manager

    async def run_cleanup():
        while True:
            await asyncio.sleep(settings.sse_cleanup_interval)
            await sse_manager.cleanup_inactive_subscriptions()

    cleanup_task = asyncio.create_task(run_cleanup())

    logger.info(f"{settings.app_name} started successfully")
    yield

    # Cleanup
    cleanup_task.cancel()
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
def start_audit(request: AuditStartRequest, current_user: str = Depends(get_current_user)):
    """Start a new security audit."""
    try:
        # Override user_id from token to prevent spoofing
        request.user_id = current_user
        return audit_controller.start_audit(request)
    except Exception as e:
        logger.error(f"Failed to start audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit", response_model=dict)
def get_audits_list(
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    current_user: str = Depends(get_current_user)
):
    """Get list of audits for a user."""
    try:
        return audit_controller.get_audits_list(current_user, status, limit, offset)
    except Exception as e:
        logger.error(f"Failed to list audits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit/{audit_id}/status", response_model=AuditStatusResponse)
def get_audit_status(audit_id: str, current_user: str = Depends(get_current_user)):
    """Get status of a specific audit."""
    try:
        return audit_controller.get_audit_status(audit_id, current_user)
    except (AuditNotFoundError, AccessDeniedError):
        raise
    except Exception as e:
        logger.error(f"Failed to get audit status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit/{audit_id}/report", response_model=AuditReportResponse)
def audit_report(audit_id: str, current_user: str = Depends(get_current_user)):
    """Get detailed report for a completed audit."""
    try:
        return audit_controller.get_audit_report(audit_id, current_user)
    except (AuditNotFoundError, AccessDeniedError):
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate audit report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit/{audit_id}/live-status")
async def audit_live_status(
    audit_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    SSE endpoint for real-time audit status updates.

    Returns streaming Server-Sent Events for audit status changes.
    Automatically disconnects when audit completes or errors.
    Includes heartbeats every 15 seconds to keep connection alive.
    """
    from api.sse_manager import sse_manager
    from api.database import get_audit
    import json

    # Validate audit exists and user has access
    audit = get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    if audit.user_id != current_user:
        raise HTTPException(status_code=403, detail="Access denied")

    # If audit is already completed, return final status immediately
    if audit.status in ('completed', 'failed', 'all_completed'):
        async def final_status_event():
            yield f"event: status_update\ndata: {json.dumps({'audit_id': audit_id, 'status': audit.status})}\n\n"
            yield "event: complete\ndata: {}\n\n"

        return StreamingResponse(
            final_status_event(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )

    # Stream live updates
    async def event_stream():
        async for event in sse_manager.subscribe(audit_id):
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
