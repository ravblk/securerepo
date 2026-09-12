from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import declarative_base, relationship


# Database setup
Base = declarative_base()


# SQLAlchemy ORM Models
class Audit(Base):
    """Audit database model representing a security audit session."""
    __tablename__ = "audits"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    repo_url = Column(String, nullable=False)
    branch = Column(String, default='main')
    lang = Column(String, default='python')
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    audit_logs = relationship("AuditLog", back_populates="audit", cascade="all, delete-orphan")
    audit_results = relationship("AuditResult", back_populates="audit", cascade="all, delete-orphan")


class AuditLog(Base):
    """Audit log database model for tracking audit actions."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False)
    action = Column(String, nullable=False)
    details = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    audit = relationship("Audit", back_populates="audit_logs")


class AuditResult(Base):
    """Audit result database model for storing findings."""
    __tablename__ = "audit_results"

    id = Column(Integer, primary_key=True)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False)
    chunk_id = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    findings = Column(String, nullable=False)  # JSONB field, stored as String in SQLAlchemy
    severity = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    audit = relationship("Audit", back_populates="audit_results")
