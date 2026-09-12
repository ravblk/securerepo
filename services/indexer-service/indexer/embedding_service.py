import logging
from typing import Optional

import requests

from .config import settings

logger = logging.getLogger(__name__)


def get_embedding(text: str) -> Optional[list[float]]:
    try:
        response = requests.post(
            f"{settings.embedding_url}/embed",
            json={"inputs": text},
            timeout=settings.embedding_timeout_sec,
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]
    except Exception:
        logger.exception("Error getting embedding")
        return None
