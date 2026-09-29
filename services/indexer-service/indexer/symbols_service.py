"""Service for managing code symbols in database for Symbol-Context feature."""
import logging
import psycopg2
from typing import List, Optional, Dict
from .config import settings
logger = logging.getLogger(__name__)


def get_db_connection():
    """Function to create PostgreSQL connection."""
    try:
        return psycopg2.connect(settings.postgres_url)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise


class SymbolsService:
    """Service for managing code symbols in database."""

    def __init__(self):
        self._connection = None

    def _get_connection(self):
        """Get database connection with error handling."""
        try:
            if self._connection is None:
                self._connection = get_db_connection()
            return self._connection
        except Exception as e:
            logger.error(f"Failed to get database connection: {e}")
            raise

    def save_symbols(self, symbols: List[dict], audit_id: str) -> int:
        """Batch save symbols to database.

        Args:
            symbols: List of symbol definitions
            audit_id: Audit ID

        Returns:
            Number of saved symbols
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        saved_count = 0

        try:
            for symbol in symbols:
                try:
                    # Use positional parameters for better compatibility
                    cursor.execute("""
                        INSERT INTO symbols (audit_id, symbol, symbol_type, file_path, start_line, end_line, code, length, package, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (audit_id, symbol, file_path, start_line)
                        DO UPDATE SET end_line = EXCLUDED.end_line, code = EXCLUDED.code, length = EXCLUDED.length, package = EXCLUDED.package
                    """, (
                        audit_id,
                        symbol.get('symbol'),
                        symbol.get('symbol_type'),
                        symbol.get('file_path'),
                        symbol.get('start_line'),
                        symbol.get('end_line'),
                        symbol.get('code'),
                        symbol.get('length'),
                        symbol.get('package')
                    ))
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"Failed to save symbol {symbol.get('symbol', 'unknown')}: {e}")
                    continue

            conn.commit()
            logger.info(f"Saved {saved_count} symbols for audit {audit_id}")
            return saved_count

        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving symbols: {e}")
            return 0
        finally:
            cursor.close()

    def get_symbol_by_name(self, audit_id: str, symbol_name: str, limit: int = 5) -> List[dict]:
        """Get symbols by name (supports overloaded functions).

        Args:
            audit_id: Audit ID
            symbol_name: Symbol name
            limit: Maximum number to return

        Returns:
            List of symbol definitions
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, audit_id, symbol, symbol_type, file_path, start_line, end_line, code, length, package
                FROM symbols
                WHERE audit_id = %s AND symbol = %s
                ORDER BY length ASC
                LIMIT %s
            """, (audit_id, symbol_name, limit))

            columns = [desc[0] for desc in cursor.description]
            symbols = [dict(zip(columns, row)) for row in cursor.fetchall()]

            logger.debug(f"Found {len(symbols)} definitions for symbol '{symbol_name}'")
            return symbols

        except Exception as e:
            logger.error(f"Error retrieving symbol '{symbol_name}': {e}")
            return []
        finally:
            cursor.close()

    def get_symbols_by_names(self, audit_id: str, symbol_names: List[str], limit_per_name: int = 2) -> Dict[str, List[dict]]:
        result = {}
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            for symbol_name in symbol_names:
                cursor.execute("""
                    SELECT id, audit_id, symbol, symbol_type, file_path, start_line, end_line, code, length, package
                    FROM symbols
                    WHERE audit_id = %s AND symbol = %s
                    ORDER BY length ASC
                    LIMIT %s
                """, (audit_id, symbol_name, limit_per_name))

                columns = [desc[0] for desc in cursor.description]
                symbols = [dict(zip(columns, row)) for row in cursor.fetchall()]

                if symbols:
                    result[symbol_name] = symbols

            logger.debug(f"Retrieved symbols for {len(result)} out of {len(symbol_names)} names")
            return result

        except Exception as e:
            logger.error(f"Error retrieving symbols: {e}")
            return {}
        finally:
            cursor.close()

    def delete_symbols_by_audit(self, audit_id: str) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM symbols WHERE audit_id = %s", (audit_id,))
            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Deleted {deleted_count} symbols for audit {audit_id}")
            return deleted_count

        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting symbols: {e}")
            return 0
        finally:
            cursor.close()

    def close(self):
        if self._connection:
            self._connection.close()
            logger.debug("Database connection closed")


# Global symbols service instance
symbols_service: Optional[SymbolsService] = None


def get_symbols_service() -> SymbolsService:
    global symbols_service
    if symbols_service is None:
        symbols_service = SymbolsService()
    return symbols_service
