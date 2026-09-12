import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from .config import settings
from .exceptions import LLMConnectionError

logger = logging.getLogger(__name__)


class LLMService:
    """Service for communicating with LLM foundation models."""

    def __init__(self):
        self._llm: Optional[ChatOpenAI] = None

    def get_llm(self) -> ChatOpenAI:
        """Get or create LLM instance."""
        if self._llm is None:
            if not settings.foundation_models_url or not settings.foundation_models_url.strip():
                raise LLMConnectionError("FOUNDATION_MODELS_URL is empty or not set")

            api_key = settings.foundation_models_api_key if settings.foundation_models_api_key else "none"

            try:
                self._llm = ChatOpenAI(
                    model=settings.llm_model,
                    api_key=api_key,
                    base_url=settings.foundation_models_url,
                    temperature=settings.llm_temperature,
                    timeout=settings.llm_timeout,
                    max_retries=settings.llm_max_retries,
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
                return False, f"Missing API key for {settings.foundation_models_url}"
            return False, f"LLM connection failed: {error_msg}"

    def is_available(self) -> bool:
        """Check if LLM is available without throwing exceptions."""
        available, _ = self.test_connection()
        return available
