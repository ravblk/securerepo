from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# Pydantic models for API validation
class AuditStartRequest(BaseModel):
    """Request model for starting a new audit."""
    repo_url: str = Field(..., description="URL of the repository to audit")
    branch: str = Field(default="main", description="Git branch to audit")
    lang: str = Field(default="python", description="Programming language")
    user_id: str = Field(..., description="User ID from authentication system")


class AuditStatusResponse(BaseModel):
    """Response model for audit status."""
    audit_id: str
    repo_url: str
    status: str
    created_at: datetime
    updated_at: datetime


class Finding(BaseModel):
    """Individual finding model for audit reports."""
    message: str
    severity: str
    file_path: str
    line_number: str = ""
    code_snippet: str = ""
    fix_suggestion: str = ""
    description: str = ""
    rule_id: str = ""
    rule_url: str = ""
    chunk_severity: Optional[str] = None


class AuditReportResponse(BaseModel):
    """Response model for audit reports containing findings."""
    audit_id: str
    findings: List[Finding]


class AuditListItem(BaseModel):
    """Response model for individual audit in list."""
    audit_id: str
    user_id: str
    repo_url: str
    branch: str
    lang: str
    status: str
    created_at: datetime
    updated_at: datetime


class AuditListResponse(BaseModel):
    """Response model for audit list endpoint."""
    items: List[AuditListItem]
    total: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str


class InitResponse(BaseModel):
    """Initialization response."""
    status: str
