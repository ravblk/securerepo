import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from .config import settings
from .langfuse_service import langfuse_service
from .exceptions import LLMConnectionError

logger = logging.getLogger(__name__)


class LLMService:
    """Service for communicating with LLM foundation models."""

    def __init__(self):
        self._llm: Optional[ChatOpenAI] = None

    def get_llm(self) -> ChatOpenAI:
        """Get or create LLM instance with Langfuse callback handler."""
        if self._llm is None:
            if not settings.OAPI_MODELS_URL or not settings.OAPI_MODELS_URL.strip():
                raise LLMConnectionError("OAPI_MODELS_URL is empty or not set")

            api_key = settings.OAPI_API_KEY if settings.OAPI_API_KEY else "none"

            try:
                # Get Langfuse callback handler for automatic LLM tracing
                langfuse_callback = langfuse_service.get_callback_handler()

                # Build callbacks list with Langfuse handler if available
                callbacks = []
                if langfuse_callback:
                    callbacks.append(langfuse_callback)
                    logger.info("Langfuse callback attached to LLM")

                self._llm = ChatOpenAI(
                    model=settings.llm_model,
                    api_key=api_key,
                    base_url=settings.OAPI_MODELS_URL,
                    temperature=settings.llm_temperature,
                    timeout=settings.llm_timeout,
                    max_retries=settings.llm_max_retries,
                    callbacks=callbacks if callbacks else None,
                )
                logger.info(f"LLM initialized: {settings.llm_model}")
            except Exception as e:
                raise LLMConnectionError(f"Failed to initialize LLM: {str(e)}")

        return self._llm

    def test_connection(self) -> tuple[bool, str]:
        """Test LLM connection."""
        try:
            llm = self.get_llm()
            llm.invoke([HumanMessage(content="test")])
            return True, "LLM connection successful"
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() and "missing" in error_msg.lower():
                return False, f"Missing API key for {settings.OAPI_MODELS_URL}"
            return False, f"LLM connection failed: {error_msg}"

    def is_available(self) -> bool:
        """Check if LLM is available without throwing exceptions."""
        available, _ = self.test_connection()
        return available
