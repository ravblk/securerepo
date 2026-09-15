import logging
from typing import Optional, List

import requests

from .config import settings
from .exceptions import EmbeddingServiceError

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings."""

    def __init__(self):
        self._url = f"{settings.embedding_url}/embed"

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for given text."""
        try:
            import time
            start_time = time.time()

            response = requests.post(
                self._url,
                json={"inputs": text},
                timeout=settings.embedding_timeout,
            )

            duration = time.time() - start_time
            logger.info(f"Embedding request completed in {duration:.2f}s, text length: {len(text)}")

            response.raise_for_status()

            result = response.json()
            embeddings = result.get("embeddings", [])

            return embeddings[0] if embeddings else None

        except requests.exceptions.Timeout:
            error_msg = f"Embedding service timeout after {settings.embedding_timeout}s"
            logger.error(error_msg)
            raise EmbeddingServiceError(error_msg)

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
            embedding = self.get_embedding("test connection")
            if embedding and len(embedding) > 0:
                return True, f"Embedding service connected, embedding size: {len(embedding)}"
            return False, "Embedding service returned empty result"

        except Exception as e:
            return False, f"Embedding service connection failed: {str(e)}"

    def is_available(self) -> bool:
        """Check if embedding service is available."""
        available, _ = self.test_connection()
        return available
