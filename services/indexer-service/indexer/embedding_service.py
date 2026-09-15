import logging
from typing import Optional

import requests

from .config import settings

logger = logging.getLogger(__name__)


def get_embedding(text: str) -> Optional[list[float]]:
    """Get embedding for given text, simplified like owasp-seeder."""
    import time
    start_time = time.time()

    try:
        response = requests.post(
            f"{settings.embedding_url}/embed",
            json={"inputs": text},
            timeout=180,  # Simplified timeout like other services
        )

        duration = time.time() - start_time
        logger.info(f"Embedding request completed in {duration:.2f}s, code length: {len(text)}")

        response.raise_for_status()
        return response.json()["embeddings"][0]

    except requests.exceptions.Timeout:
        error_msg = f"Embedding service timeout after 180s"
        logger.error(error_msg)
        return None

    except requests.exceptions.RequestException as e:
        error_msg = f"Embedding service request failed: {str(e)}"
        logger.error(error_msg)
        return None

    except Exception as e:
        error_msg = f"Embedding service error: {str(e)}"
        logger.error(error_msg)
        return None
