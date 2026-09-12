from typing import Optional
from pydantic import BaseModel


class SeedRequest(BaseModel):
    """Request model for starting the seeding process."""
    force: bool = False
    max_depth: Optional[int] = None  # Override default max depth for this request


class SeedResponse(BaseModel):
    """Response model for seeding request."""
    seed_id: str
    status: str
    message: Optional[str] = None


class SeedStatus(BaseModel):
    """Model for seed operation status."""
    seed_id: str
    status: str
    pages_processed: int = 0
    pages_failed: int = 0
    nested_pages_found: int = 0
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    current_url: Optional[str] = None


class SeedHistoryItem(BaseModel):
    """Model for seed history entry."""
    seed_id: str
    status: str
    pages_processed: int
    pages_failed: int
    nested_pages_found: int
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str


class ServiceInfoResponse(BaseModel):
    """Service information response."""
    service: str
    version: str
    storage: str
    nested_scanning_enabled: bool
    max_depth: int
