import logging
import threading
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import settings
from .db_models import Audit
from .exceptions import DatabaseError

logger = logging.getLogger(__name__)


# Database setup
engine = create_engine(settings.postgres_url, echo=False)
SessionLocal = sessionmaker(bind=engine)
_db_lock = threading.Lock()


def get_db() -> Session:
    """Get database session for dependency injection."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_database():
    """Initialize database through migrations."""
    try:
        from migrations import run_migrations, verify_relationships
        success = run_migrations()
        if success:
            verify_relationships()
        return success
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        raise DatabaseError(f"Database migration failed: {str(e)}")


def create_audit(
    audit_id: str,
    user_id: str,
    repo_url: str,
    branch: str = "main",
    lang: str = "python"
) -> Audit:
    """Create a new audit record in the database."""
    try:
        session = SessionLocal()

        audit = Audit(
            id=audit_id,
            user_id=user_id,
            repo_url=repo_url,
            branch=branch,
            lang=lang,
            status="pending"
        )

        session.add(audit)
        session.commit()
        session.refresh(audit)

        logger.info(f"Created audit {audit_id} for user {user_id}")
        return audit

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create audit: {e}")
        raise DatabaseError(f"Failed to create audit: {str(e)}")
    finally:
        session.close()


def get_audit(audit_id: str) -> Optional[Audit]:
    """Retrieve an audit record by ID."""
    try:
        session = SessionLocal()
        audit = session.query(Audit).filter(Audit.id == audit_id).first()
        return audit
    except Exception as e:
        logger.error(f"Failed to get audit {audit_id}: {e}")
        raise DatabaseError(f"Failed to retrieve audit: {str(e)}")
    finally:
        session.close()


def update_audit_status(audit_id: str, status: str) -> None:
    """Update the status of an audit."""
    try:
        session = SessionLocal()

        audit = session.query(Audit).filter(Audit.id == audit_id).first()
        if not audit:
            session.close()
            raise DatabaseError(f"Audit {audit_id} not found")

        audit.status = status
        audit.updated_at = datetime.utcnow()
        session.commit()

        logger.info(f"Updated audit {audit_id} status to {status}")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update audit status: {e}")
        raise DatabaseError(f"Failed to update audit status: {str(e)}")
    finally:
        session.close()


def list_audits(
    user_id: str,
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
) -> Tuple[List[Audit], int]:
    """Get list of audits with filtering and pagination."""
    try:
        session = SessionLocal()

        query = session.query(Audit).filter(Audit.user_id == user_id)

        if status:
            query = query.filter(Audit.status == status)

        total = query.count()

        audits = query.order_by(Audit.created_at.desc()).limit(limit).offset(offset).all()

        return audits, total

    except Exception as e:
        logger.error(f"Failed to list audits: {e}")
        raise DatabaseError(f"Failed to retrieve audits: {str(e)}")
    finally:
        session.close()


def get_audit_results(audit_id: str) -> List[Tuple]:
    """Get all audit results for a given audit ID."""
    try:
        import psycopg2
        from psycopg2.extras import Json

        conn = psycopg2.connect(settings.postgres_url)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT chunk_id, file_path, findings, severity FROM audit_results WHERE audit_id = %s ORDER BY chunk_id",
            (audit_id,)
        )
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        logger.info(f"Found {len(rows)} audit results for audit {audit_id}")
        return rows

    except Exception as e:
        logger.error(f"Failed to get audit results: {e}")
        raise DatabaseError(f"Failed to retrieve audit results: {str(e)}")
