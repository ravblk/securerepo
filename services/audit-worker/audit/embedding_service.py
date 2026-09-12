import logging
from typing import Optional, List

import requests

from .config import settings
from .exceptions import EmbeddingServiceError

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings."""

    def __init__(self):
        self._url = settings.embedding_url

    def get_embedding(self, text: str, max_length: Optional[int] = None) -> Optional[List[float]]:
        """Get embedding for given text."""
        try:
            # Truncate text if maximum length specified
            if max_length and len(text) > max_length:
                text = text[:max_length]

            response = requests.post(
                self._url,
                json={"inputs": text},
                timeout=settings.embedding_timeout_seconds,
            )
            response.raise_for_status()

            result = response.json()
            embeddings = result.get("embeddings", [])

            if isinstance(embeddings, list) and embeddings:
                return embeddings[0]
            else:
                return None

        except requests.exceptions.RequestException as e:
            error_msg = f"Embedding service request failed: {str(e)}"
            logger.error(error_msg)
            raise EmbeddingServiceError(error_msg)
        except Exception as e:
            error_msg = f"Embedding service error: {str(e)}"
            logger.error(error_msg)
            raise EmbeddingServiceError(error_msg)

    def test_connection(self) -> tuple[bool, str]:
        """Test embedding service connection."""
        try:
            embedding = self.get_embedding("test", max_length=10)
            if embedding and len(embedding) > 0:
                return True, f"Embedding service connected, embedding size: {len(embedding)}"
            return False, "Embedding service returned empty result"
        except Exception as e:
            return False, f"Embedding service connection failed: {str(e)}"

    def is_available(self) -> bool:
        """Check if embedding service is available."""
        available, _ = self.test_connection()
        return available
