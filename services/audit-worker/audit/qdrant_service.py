"""
Qdrant Service - Simplified implementation for internal rules retrieval
Service for Qdrant vector database operations with basic semantic search.
"""
import logging
from typing import List, Optional

import numpy as np
from qdrant_client import QdrantClient

from .config import settings
from .exceptions import QdrantError

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for Qdrant vector database operations with semantic search."""

    def __init__(self, url: Optional[str] = None) -> None:
        """Initialize Qdrant service."""
        self._client = QdrantClient(url=url or settings.qdrant_url)
        self._default_lang = "python"
        self._collection_name = "internal_policies"

    def get_client(self) -> QdrantClient:
        """Get the Qdrant client instance."""
        return self._client

    def _process_search_point(self, point, embedding: List[float], lang: Optional[str] = None) -> Optional[dict]:
        """Process a search point with language filtering and similarity calculation."""
        payload = point.payload

        # Skip points without required fields
        if not all(key in payload for key in ["title", "text"]):
            return None

        # Language filter if provided
        if lang is not None:
            point_lang = payload.get("lang", "").lower()
            if point_lang and point_lang != lang.lower():
                # Allow English rules for all languages
                if point_lang != "en":
                    return None

        # Extract vector if available
        if hasattr(point, 'vector') and point.vector:
            point_vector = point.vector
        else:
            return None

        # Calculate cosine similarity
        embedding_array = np.array(embedding)
        point_vector_array = np.array(point_vector)

        dot_product = np.dot(embedding_array, point_vector_array)
        norm_a = np.linalg.norm(embedding_array)
        norm_b = np.linalg.norm(point_vector_array)

        if norm_a == 0 or norm_b == 0:
            similarity = 0.0
        else:
            similarity = dot_product / (norm_a * norm_b)

        return {
            "rule_id": payload.get("rule_id", payload.get("title", "")),
            "title": payload.get("title", ""),
            "text": payload.get("text", ""),
            "url": payload.get("url", ""),
            "category": payload.get("category", ""),
            "similarity": similarity,
            "lang": payload.get("lang", "")
        }

    def format_search_result(self, result: dict) -> dict:
        """Format search result for response."""
        return {
            "rule_id": result.get("rule_id", ""),
            "text": result.get("text", ""),
            "url": result.get("url", ""),
            "similarity": result.get("similarity", 0.0)
        }

    def search_rules(
        self,
        embedding: List[float],
        code: str,
        lang: str,
        limit: int = 3  # ТОЛЬКО 3 внутренних правила как дополнение к zero-shot
    ) -> List[dict]:
        """
        Search internal security rules for ZERO-SHOT augmentation.

        Returns exactly 3 most relevant internal rules as context for LLM zero-shot analysis.
        The main analysis is performed by LLM independently using its security knowledge.

        How it works:
        1. Uses semantic similarity to find most relevant internal rules
        2. Returns top 3 rules as augmentation context for LLM
        3. LLM performs independent zero-shot vulnerability detection with CWE IDs
        """
        return self.search_basic_rules(embedding, lang, limit)

    def search_basic_rules(
        self,
        embedding: List[float],
        lang: str,
        limit: int = 3  # ТОЛЬКО 3 внутренних правил для zero-shot
    ) -> List[dict]:
        """Search for exactly 3 most relevant internal security rules for zero-shot augmentation."""
        if not embedding:
            return []

        try:
            return self._search_internal_rules_basic(embedding, lang, limit)
        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    def _search_internal_rules_basic(
        self,
        embedding: List[float],
        lang: Optional[str] = None,
        limit: int = 3
    ) -> List[dict]:
        """Basic semantic search for internal security policies."""
        try:
            points_data = self._client.scroll(
                collection_name="internal_policies",
                limit=limit * 2,  # Получаем больше правил для ранжирования
                with_payload=True,
                with_vectors=True
            )

            # Filter internal rules
            internal_rules_points = []
            for point in points_data[0]:
                # Skip points without basic fields
                payload = point.payload
                if not all(key in payload for key in ["title", "text"]):
                    continue

                # Process search point with language filtering
                processed_point = self._process_search_point(point, embedding, lang)
                if processed_point:
                    internal_rules_points.append(processed_point)

            logger.info(
                f"Internal rules search: {len(points_data[0])} total points, "
                f"{len(internal_rules_points)} valid internal rules"
            )

            # Sort by similarity and return top results
            internal_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            top_rules = internal_rules_points[:limit]

            self._log_search_results(top_rules, "internal rules semantic")

            return [
                self.format_search_result(rule)
                for rule in top_rules
            ]

        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    def _log_search_results(self, results: List[dict], context: str):
        """Log search results with scores."""
        if results:
            scores_str = ", ".join([f"{r['similarity']:.3f}" for r in results])
            logger.info(f"Selected {len(results)} best rules via {context} (scores: [{scores_str}])")
        else:
            logger.warning(f"No best rules found via {context}")

    def test_connection(self) -> tuple[bool, str]:
        """Test Qdrant connection."""
        try:
            collections = self._client.get_collections()
            collection_names = [c.name for c in collections.collections]
            return True, f"Qdrant connected, {len(collection_names)} collections available"
        except Exception as e:
            return False, f"Qdrant connection failed: {str(e)}"

    def is_available(self) -> bool:
        """Check if Qdrant is available."""
        available, _ = self.test_connection()
        return available