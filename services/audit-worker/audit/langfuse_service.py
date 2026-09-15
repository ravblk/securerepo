import logging
from typing import Optional
from langfuse import Langfuse
from langfuse.callback import CallbackHandler
from .config import settings

logger = logging.getLogger(__name__)


class LangfuseService:
    """Service for Langfuse integration and LLM tracing."""

    def __init__(self):
        self._langfuse: Optional[Langfuse] = None
        self._callback_handler: Optional[CallbackHandler] = None

    def _init_langfuse(self) -> None:
        """Initialize Langfuse client if not already initialized."""
        if self._langfuse is not None:
            return

        if not settings.langfuse_enabled:
            logger.info("Langfuse is disabled - missing API keys")
            return

        try:
            self._langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host
            )
            logger.info(f"Langfuse initialized: {settings.langfuse_host}")
        except Exception as e:
            logger.warning(f"Failed to initialize Langfuse: {e}")
            self._langfuse = None

    def get_callback_handler(self) -> Optional[CallbackHandler]:
        """Get Langchain callback handler for automatic LLM tracing."""
        if not settings.langfuse_enabled:
            return None

        if self._callback_handler is None:
            try:
                self._init_langfuse()
                if self._langfuse:
                    self._callback_handler = CallbackHandler(
                        public_key=settings.langfuse_public_key,
                        secret_key=settings.langfuse_secret_key,
                        host=settings.langfuse_host,
                    )
                    logger.info("Langfuse callback handler created")
            except Exception as e:
                logger.warning(f"Failed to create Langfuse callback handler: {e}")

        return self._callback_handler

    def create_trace(self, name: str, session_id: Optional[str] = None, metadata: Optional[dict] = None):
        """Create a new trace for tracing audit operations."""
        if not settings.langfuse_enabled:
            return None

        try:
            self._init_langfuse()
            if self._langfuse:
                trace = self._langfuse.trace(
                    name=name,
                    session_id=session_id,
                    metadata=metadata or {}
                )
                logger.debug(f"Created trace: {name} for session: {session_id}")
                return trace
        except Exception as e:
            logger.warning(f"Failed to create trace: {e}")

        return None

    def create_score(self, trace_id: str, name: str, value: float, comment: Optional[str] = None):
        """Create a score for evaluating operation results."""
        if not settings.langfuse_enabled:
            return

        try:
            self._init_langfuse()
            if self._langfuse:
                self._langfuse.score(
                    trace_id=trace_id,
                    name=name,
                    value=value,
                    comment=comment or ""
                )
                logger.debug(f"Created score: {name}={value} for trace: {trace_id}")
        except Exception as e:
            logger.warning(f"Failed to create score: {e}")

    def create_event(self, trace_id: str, name: str, metadata: Optional[dict] = None):
        """Create an event within a trace for detailed logging."""
        if not settings.langfuse_enabled:
            return

        try:
            self._init_langfuse()
            if self._langfuse:
                self._langfuse.event(
                    trace_id=trace_id,
                    name=name,
                    metadata=metadata or {}
                )
                logger.debug(f"Created event: {name} for trace: {trace_id}")
        except Exception as e:
            logger.warning(f"Failed to create event: {e}")

    def flush(self):
        """Flush any pending traces to Langfuse server."""
        if not settings.langfuse_enabled or self._langfuse is None:
            return

        try:
            self._langfuse.flush()
            logger.debug("Langfuse traces flushed")
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse: {e}")


# Global service instance
langfuse_service = LangfuseService()