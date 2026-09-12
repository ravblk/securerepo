import logging
from typing import Optional

import psycopg2
from psycopg2.extras import Json

from .config import settings
from .exceptions import DatabaseError

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for PostgreSQL database operations."""

    def __init__(self):
        self._conn: Optional[psycopg2.extensions.connection] = None

    def get_connection(self) -> psycopg2.extensions.connection:
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            try:
                self._conn = psycopg2.connect(settings.postgres_url)
                logger.info("Database connection established")
            except Exception as e:
                raise DatabaseError(f"Failed to connect to database: {str(e)}")
        return self._conn

    def save_result(
        self,
        audit_id: str,
        chunk_id: str,
        file_path: str,
        violations: list,
        severity: Optional[str]
    ) -> None:
        """Save audit results to database."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO audit_results (audit_id, chunk_id, file_path, findings, severity)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (audit_id, chunk_id, file_path, Json(violations), severity)
            )
            conn.commit()
            logger.info(f"Saved result for chunk {chunk_id}: {len(violations)} violations")
        except Exception as e:
            conn.rollback()
            error_msg = f"DB Error saving result for {chunk_id}: {e}"
            logger.error(error_msg)
            raise DatabaseError(error_msg)
        finally:
            cursor.close()

    def test_connection(self) -> tuple[bool, str]:
        """Test database connection."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            return True, "Database connection successful"
        except Exception as e:
            return False, f"Database connection failed: {str(e)}"

    def is_available(self) -> bool:
        """Check if database is available."""
        available, _ = self.test_connection()
        return available

    def close(self) -> None:
        """Close database connection."""
        if self._conn and not self._conn.closed:
            try:
                self._conn.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
        self._conn = None
