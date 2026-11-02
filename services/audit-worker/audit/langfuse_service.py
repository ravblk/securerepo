import logging
from typing import Optional, Any

from langfuse import Langfuse
from langfuse.callback import CallbackHandler

from .config import settings

logger = logging.getLogger(__name__)


def _keys_look_valid(public_key: str, secret_key: str) -> bool:
    return public_key.startswith("pk-") and secret_key.startswith("sk-")


class LangfuseService:
    """Service for Langfuse integration and LLM tracing."""

    def __init__(self):
        self._langfuse: Optional[Langfuse] = None
        self._callback_handler: Optional[CallbackHandler] = None
        self._enabled = settings.langfuse_enabled

    def _validate_keys(self) -> bool:
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return False
        if not _keys_look_valid(settings.langfuse_public_key, settings.langfuse_secret_key):
            logger.error(
                "Langfuse API keys look swapped or invalid "
                "(LANGFUSE_PUBLIC_KEY must start with pk-, LANGFUSE_SECRET_KEY with sk-)"
            )
            return False
        return True

    def _init_langfuse(self) -> None:
        """Initialize Langfuse client if not already initialized."""
        if self._langfuse is not None:
            return

        if not self._enabled:
            logger.info("Langfuse is disabled - missing API keys")
            return

        if not self._validate_keys():
            self._enabled = False
            return

        try:
            self._langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            if not self._langfuse.auth_check():
                logger.error(
                    "Langfuse auth_check failed for host %s — traces will not be ingested",
                    settings.langfuse_host,
                )
                self._enabled = False
                self._langfuse = None
                return
            logger.info("Langfuse initialized and authenticated: %s", settings.langfuse_host)
        except Exception as e:
            logger.warning("Failed to initialize Langfuse: %s", e)
            self._enabled = False
            self._langfuse = None

    def get_callback_handler(
        self,
        stateful_client: Optional[Any] = None,
    ) -> Optional[CallbackHandler]:
        """LangChain callback handler; pass workflow trace as stateful_client to nest LLM spans."""
        if not self._enabled:
            return None

        if stateful_client is not None:
            try:
                self._init_langfuse()
                return CallbackHandler(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                    stateful_client=stateful_client,
                )
            except Exception as e:
                logger.warning("Failed to create Langfuse callback handler: %s", e)
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
                logger.warning("Failed to create Langfuse callback handler: %s", e)

        return self._callback_handler

    def create_trace(self, name: str, session_id: Optional[str] = None, metadata: Optional[dict] = None):
        """Create a new trace for tracing audit operations."""
        if not self._enabled:
            return None

        try:
            self._init_langfuse()
            if self._langfuse:
                trace = self._langfuse.trace(
                    name=name,
                    session_id=session_id,
                    metadata=metadata or {},
                )
                logger.debug("Created trace: %s for session: %s", name, session_id)
                return trace
        except Exception as e:
            logger.warning("Failed to create trace: %s", e)

        return None

    def create_score(self, trace_id: str, name: str, value: float, comment: Optional[str] = None):
        """Create a score for evaluating operation results."""
        if not self._enabled:
            return

        try:
            self._init_langfuse()
            if self._langfuse:
                self._langfuse.score(
                    trace_id=trace_id,
                    name=name,
                    value=value,
                    comment=comment or "",
                )
                logger.debug("Created score: %s=%s for trace: %s", name, value, trace_id)
        except Exception as e:
            logger.warning("Failed to create score: %s", e)

    def create_event(self, trace_id: str, name: str, metadata: Optional[dict] = None):
        """Create an event within a trace for detailed logging."""
        if not self._enabled:
            return

        try:
            self._init_langfuse()
            if self._langfuse:
                self._langfuse.event(
                    trace_id=trace_id,
                    name=name,
                    metadata=metadata or {},
                )
                logger.debug("Created event: %s for trace: %s", name, trace_id)
        except Exception as e:
            logger.warning("Failed to create event %s: %s", name, e)

    def flush(self):
        """Flush any pending traces to Langfuse server."""
        if not self._enabled or self._langfuse is None:
            return

        try:
            self._langfuse.flush()
            logger.debug("Langfuse traces flushed")
        except Exception as e:
            logger.warning("Failed to flush Langfuse: %s", e)


langfuse_service = LangfuseService()
