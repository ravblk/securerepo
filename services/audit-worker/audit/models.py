from typing import Optional, List, Any, TypedDict
from pydantic import BaseModel


# Pydantic models for API and validation
class AuditTask(BaseModel):
    """Model representing an audit task from Kafka."""
    chunk_id: str
    code: str
    file_path: str
    audit_id: str
    lang: Optional[str] = "python"
    chunk_index: Optional[int] = 0
    total_chunks: Optional[int] = 1


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str


class ServiceInfoResponse(BaseModel):
    """Service information response."""
    service: str
    kafka_topic: str
    storage: str


# LangGraph State
class AuditState(TypedDict):
    """State for the LangGraph workflow with Symbol-Context support."""
    task: AuditTask
    code: str
    file_path: str
    lang: str
    audit_id: str  # Required for Symbol-Context
    code_embedding: List[float]
    internal_rules: List[dict]
    enriched_context: str  # Symbol-Context enriched function bodies
    violations: List[dict]
    severity: Optional[str]
    auditing_sent: bool


# Rule models
class SecurityRule(BaseModel):
    """Model for a security rule from Qdrant."""
    rule_id: str
    text: str
    url: str = ""


class Violation(BaseModel):
    """Model for a code security violation."""
    rule_id: str
    rule_url: str = ""
    severity: str
    explanation: str
    vulnerable_line: str


class ViolationsResponse(BaseModel):
    """Model for violations response from LLM."""
    violations: List[Violation]


class FileLanguage(BaseModel):
    """Model for detected programming language."""
    name: str
    extension: str
