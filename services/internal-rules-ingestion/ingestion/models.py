from typing import Optional
from pydantic import BaseModel


class SyncRequest(BaseModel):
    """Request model for starting the sync process."""
    space_key: Optional[str] = None
    force: bool = False


class SyncResponse(BaseModel):
    """Response model for sync request."""
    sync_id: str
    status: str
    message: Optional[str] = None


class SyncStatus(BaseModel):
    """Model for sync operation status."""
    sync_id: str
    status: str
    pages_processed: int = 0
    pages_failed: int = 0
    pages_total: int = 0
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    current_url: Optional[str] = None


class Page(BaseModel):
    """Model for a content page to be synced."""
    id: int
    title: str
    url: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    qdrant: str
    qdrant_url: str


class ServiceInfoResponse(BaseModel):
    """Service information response."""
    service: str
    version: str
    storage: str
    max_workers: int
