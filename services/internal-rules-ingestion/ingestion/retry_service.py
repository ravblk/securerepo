import logging
import time
from typing import Callable, Optional

from qdrant_client.http.exceptions import (
    UnexpectedResponse,
    ResponseHandlingException,
)
import requests


from .config import settings
from .exceptions import (
    QdrantError,
    ContentFetchError,
    EmbeddingServiceError
)

logger = logging.getLogger(__name__)


class RetryService:
    """Service for handling retry logic with exponential backoff."""

    def __init__(self):
        self._retriable_exceptions = (
            ConnectionError,
            TimeoutError,
            UnexpectedResponse,
            ResponseHandlingException,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        )

    def execute_with_retry(
        self,
        func: Callable,
        name: str,
        max_retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
        backoff_max: Optional[float] = None
    ) -> any:
        """
        Execute a function with exponential backoff retries.

        Args:
            func: Function to execute
            name: Operation name for logging
            max_retries: Maximum number of retry attempts
            backoff_base: Base delay factor
            backoff_max: Maximum delay

        Returns:
            Result of the function execution
        """
        max_retries = max_retries or settings.qdrant_max_retries
        backoff_base = backoff_base or settings.qdrant_backoff_base
        backoff_max = backoff_max or settings.qdrant_backoff_max

        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return func()
            except self._retriable_exceptions as e:
                last_exc = e
                if attempt >= max_retries:
                    logger.error(f"[{name}] failed after {attempt} attempts: {e}")
                    raise

                delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                logger.warning(
                    f"[{name}] attempt {attempt}/{max_retries} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)

        raise last_exc  # pragma: no cover

    async def execute_async_with_retry(
        self,
        func: Callable,
        name: str,
        max_retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
        backoff_max: Optional[float] = None
    ) -> any:
        """
        Execute an async function with exponential backoff retries.

        Args:
            func: Async function to execute
            name: Operation name for logging
            max_retries: Maximum number of retry attempts
            backoff_base: Base delay factor
            backoff_max: Maximum delay

        Returns:
            Result of the function execution
        """
        max_retries = max_retries or settings.qdrant_max_retries
        backoff_base = backoff_base or settings.qdrant_backoff_base
        backoff_max = backoff_max or settings.qdrant_backoff_max

        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return await func()
            except Exception as e:
                last_exc = e
                if attempt >= max_retries:
                    logger.error(f"[{name}] failed after {attempt} attempts: {e}")
                    raise

                delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                logger.warning(
                    f"[{name}] attempt {attempt}/{max_retries} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)

        raise last_exc  # pragma: no cover

    def is_retriable(self, exception: Exception) -> bool:
        """Check if an exception is retriable."""
        return isinstance(exception, self._retriable_exceptions)
