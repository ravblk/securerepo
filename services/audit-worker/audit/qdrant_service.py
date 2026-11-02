"""
Qdrant Service - Simplified implementation for internal rules retrieval
Service for Qdrant vector database operations with basic semantic search.
"""
import logging
from typing import List, Optional

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

    def _matches_language(self, payload: dict, lang: Optional[str]) -> bool:
        """Keep rules for this language, English, or rules with no language tag."""
        if lang is None:
            return True
        point_lang = (payload.get("lang") or "").lower()
        if not point_lang:
            return True
        return point_lang in {lang.lower(), "en"}

    def _search_internal_rules_basic(
        self,
        embedding: List[float],
        lang: Optional[str] = None,
        limit: int = 3
    ) -> List[dict]:
        """Nearest-neighbour search over internal_policies.

        scroll() only reads the first page of the collection and then ranks
        that page, so the relevant rules are missed whenever they are not
        stored at the head of the collection.
        """
        try:
            fetch_limit = max(limit * 10, 30)
            hits = self._client.search(
                collection_name=self._collection_name,
                query_vector=embedding,
                limit=fetch_limit,
                with_payload=True,
            )

            internal_rules_points = []
            for hit in hits:
                payload = hit.payload or {}
                if not all(key in payload for key in ["title", "text"]):
                    continue
                if not self._matches_language(payload, lang):
                    continue
                internal_rules_points.append({
                    "rule_id": payload.get("rule_id", payload.get("title", "")),
                    "title": payload.get("title", ""),
                    "text": payload.get("text", ""),
                    "url": payload.get("url", ""),
                    "category": payload.get("category", ""),
                    "similarity": float(getattr(hit, "score", 0.0) or 0.0),
                    "lang": payload.get("lang", ""),
                })

            logger.info(
                f"Internal rules search: {len(hits)} nearest hits, "
                f"{len(internal_rules_points)} valid internal rules"
            )

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