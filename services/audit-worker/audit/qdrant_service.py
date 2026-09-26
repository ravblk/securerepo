"""
Qdrant Service Refactored - Modular and Clean Implementation
Service for Qdrant vector database operations with hybrid search support.
"""
import logging
from typing import List, Optional

from qdrant_client import QdrantClient

from .config import settings
from .exceptions import QdrantError
from .qdrant_config import SecurityPatternsConfig, SecurityCategory
from .code_analyzer import CodeAnalyzer, CodeAnalysisResult
from .vector_search import VectorSearchHelper
from .search_ranking import HybridRankingEngine

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for Qdrant vector database operations with hybrid search support."""

    def __init__(self, url: Optional[str] = None) -> None:
        """Initialize Qdrant service with modular components."""
        self._client = QdrantClient(url=url or settings.qdrant_url)
        self._default_lang = "python"

        # Initialize modular components
        self.code_analyzer = CodeAnalyzer(self._default_lang)
        self.config = SecurityPatternsConfig()
        self.vector_search_helper = VectorSearchHelper()

    def get_client(self) -> QdrantClient:
        """Get the Qdrant client instance."""
        return self._client

    def analyze_code_security(self, code: str, lang: str) -> CodeAnalysisResult:
        """Analyze code for security-relevant keywords and patterns."""
        return self.code_analyzer.analyze_code_security(code, lang)

    # ========== Hybrid Search Methods ==========

    def search_rules(
        self,
        embedding: List[float],
        code: str,
        lang: str,
        limit: int = 7  # ТОЛЬКО 7 внутренних правил как дополнение к zero-shot
    ) -> List[dict]:
        """
        Search internal security rules for ZERO-SHOT augmentation.

        Returns exactly 7 most relevant internal rules as context for LLM zero-shot analysis.
        The main analysis is performed by LLM independently using its security knowledge.

        How it works:
        1. Analyzes code for security-relevant keywords and patterns
        2. Uses semantic similarity to find most relevant internal rules
        3. Returns top 7 rules as augmentation context for LLM
        4. LLM performs independent zero-shot vulnerability detection with CWE IDs
        """
        if not embedding:
            return []

        try:
            # Step 1: Analyze code for security-relevant patterns
            code_analysis = self.analyze_code_security(code, lang)
            self._log_code_analysis(code_analysis, "internal security rules")

            # Step 2: Get top 7 internal security rules for zero-shot augmentation
            all_internal_rules = self._get_all_internal_rules(embedding)

            logger.info(f"Retrieved {len(all_internal_rules)} internal security rules for zero-shot augmentation")

            # Step 3: Apply keyword-based scoring and ranking
            ranking_engine = HybridRankingEngine('internal')
            ranked_rules = ranking_engine.rank_results(all_internal_rules, code_analysis)

            # Step 4: Return exactly 7 most relevant rules for zero-shot context
            top_rules = ranked_rules[:limit]  # HARD LIMIT: exactly 7 rules

            self._log_search_results(top_rules, "internal rules (zero-shot augmentation)")

            return self.vector_search_helper.format_search_results_batch(
                [VectorSearchHelper.format_search_result(rule) for rule in top_rules]
            )

        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    # ========== Legacy Semantic Search Methods ==========

    def search_basic_rules(
        self,
        embedding: List[float],
        lang: str,
        limit: int = 7  # ТОЛЬКО 7 внутренних правил для zero-shot
    ) -> List[dict]:
        """Search for exactly 7 most relevant internal security rules for zero-shot augmentation."""
        if not embedding:
            return []

        try:
            return self._search_internal_rules_basic(embedding, limit)
        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    # ========== Internal Semantic Search Methods (DEPRECATED - integrated with all rules search) ==========

    def search_internal_rules(
        self,
        embedding: List[float],
        limit: int = 2
    ) -> List[dict]:
        """Search for internal security policies - DEPRECATED: now integrated with all rules search."""
        logger.warning("search_internal_rules is deprecated - internal policies are now included in general rules search")
        return []

    def _get_all_internal_rules(
        self,
        embedding: List[float],
        internal_limit: int = 200  # Увеличенный лимит для получения всех правил
    ) -> List[dict]:
        """Get ALL internal security rules from internal_policies collection."""
        internal_rules_points = []

        try:
            # Search ONLY in internal_policies collection
            logger.info("Searching ALL internal policies...")
            internal_points_data = self._client.scroll(
                collection_name="internal_policies",
                limit=internal_limit,
                with_payload=True,
                with_vectors=True
            )

            # Process all internal policy points
            for point in internal_points_data[0]:
                # Check basic fields for internal policies
                payload = point.payload
                if not all(key in payload for key in ["title", "text"]):
                    continue

                processed_point = self.vector_search_helper.process_search_point(point, embedding)
                if processed_point:
                    internal_rules_points.append(processed_point)

            logger.info(f"Found {len(internal_rules_points)} internal security rules")

            # Sort by similarity descending
            internal_rules_points.sort(key=lambda x: x['similarity'], reverse=True)

            return internal_rules_points

        except Exception as e:
            error_msg = f"Error retrieving internal rules: {e}"
            logger.error(error_msg)
            return []

    def _semantic_search_internal_rules(
        self,
        embedding: List[float],
        internal_limit: int = 30
    ) -> List[dict]:
        """Semantic search for internal security policies."""
        try:
            points_data = self._client.scroll(
                collection_name="internal_policies",
                limit=internal_limit,
                with_payload=True,
                with_vectors=True
            )

            # Filter and process points
            internal_rules_points = []
            for point in points_data[0]:
                # Skip points without basic fields
                payload = point.payload
                if not all(key in payload for key in ["title", "text"]):
                    continue

                processed_point = self.vector_search_helper.process_search_point(point, embedding)
                if processed_point:
                    internal_rules_points.append(processed_point)

            # Sort by similarity
            internal_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            return internal_rules_points

        except Exception as e:
            error_msg = f"Semantic internal rules search error: {e}"
            logger.error(error_msg)
            return []

    def _search_internal_rules_basic(
        self,
        embedding: List[float],
        limit: int = 20
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

                processed_point = self.vector_search_helper.process_search_point(point, embedding)
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
                VectorSearchHelper.format_search_result(rule)
                for rule in top_rules
            ]

        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    # ========== Utility Methods ==========

    def _log_code_analysis(self, analysis: CodeAnalysisResult, context: str):
        """Log code analysis results."""
        logger.info(
            f"{context.capitalize()} code analysis found: "
            f"{len(analysis.suspicious_keywords)} keywords, "
            f"{len(analysis.suspicious_functions)} suspicious functions, "
            f"{len(analysis.library_calls)} library calls, "
            f"{len(analysis.security_categories)} security categories"
        )

    def _log_search_results(self, results: List[dict], context: str):
        """Log search results with scores."""
        if results:
            scores_str = ", ".join([f"{r['hybrid_score']:.3f}" for r in results])
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

    # ========== Legacy Methods for Backward Compatibility ==========

    def search_general_rules_hybrid(
        self,
        embedding: List[float],
        code: str,
        lang: str,
        limit: int = 20
    ) -> List[dict]:
        """DEPRECATED: Use search_rules instead."""
        logger.warning("search_general_rules_hybrid is deprecated - use search_rules for all internal rules")
        return self.search_rules(embedding, code, lang, limit)

    def search_general_rules(
        self,
        embedding: List[float],
        lang: str,
        limit: int = 20
    ) -> List[dict]:
        """DEPRECATED: Use search_basic_rules instead."""
        logger.warning("search_general_rules is deprecated - use search_basic_rules for internal rules")
        return self.search_basic_rules(embedding, lang, limit)

    def search_internal_rules_hybrid(
        self,
        embedding: List[float],
        code: str,
        limit: int = 20
    ) -> List[dict]:
        """DEPRECATED: Use search_rules instead."""
        logger.warning("search_internal_rules_hybrid is deprecated - use search_rules")
        lang = self._default_lang
        return self.search_rules(embedding, code, lang, limit)

    def search_internal_rules(
        self,
        embedding: List[float],
        limit: int = 20
    ) -> List[dict]:
        """DEPRECATED: Use search_basic_rules instead."""
        logger.warning("search_internal_rules is deprecated - use search_basic_rules")
        return self.search_basic_rules(embedding, self._default_lang, limit)

    def is_available(self) -> bool:
        """Check if Qdrant is available."""
        available, _ = self.test_connection()
        return available


# Add batch processing method to VectorSearchHelper
VectorSearchHelper.format_search_results_batch = staticmethod(lambda results: results)