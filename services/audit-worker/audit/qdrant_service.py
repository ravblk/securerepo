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

    def search_general_rules_hybrid(
        self,
        embedding: List[float],
        code: str,
        lang: str,
        limit: int = 3
    ) -> List[dict]:
        """
        Hybrid search combining semantic and keyword-based search for general security rules.

        Improves upon pure semantic search by:
        1. Analyzing code for security-relevant keywords and patterns
        2. Using semantic similarity for broad match
        3. Filtering/prioritizing based on identified security categories
        4. Applying keyword boosting for precise relevance
        """
        if not embedding:
            return []

        try:
            # Step 1: Analyze code for security-relevant patterns
            code_analysis = self.analyze_code_security(code, lang)
            self._log_code_analysis(code_analysis, "general rules")

            # Step 2: Semantic search for general rules
            semantic_results = self._semantic_search_general_rules(embedding, lang)

            logger.info(f"Semantic search found {len(semantic_results)} candidates")

            # Step 3: Apply keyword-based scoring and fusion ranking
            ranking_engine = HybridRankingEngine('general')
            ranked_rules = ranking_engine.rank_results(semantic_results, code_analysis, lang)

            # Step 4: Return top results
            top_rules = ranked_rules[:limit]
            self._log_search_results(top_rules, "general rules hybrid")

            return self.vector_search_helper.format_search_results_batch(
                [VectorSearchHelper.format_search_result(rule) for rule in top_rules]
            )

        except Exception as e:
            error_msg = f"Hybrid general rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    def search_internal_rules_hybrid(
        self,
        embedding: List[float],
        code: str,
        limit: int = 2
    ) -> List[dict]:
        """
        Hybrid search combining semantic and keyword-based search for internal security policies.

        Similar approach to search_general_rules_hybrid but for internal policies.
        """
        if not embedding:
            return []

        try:
            # Step 1: Analyze code for security-relevant patterns
            lang = self._default_lang  # Default to python for internal rules
            code_analysis = self.analyze_code_security(code, lang)
            self._log_code_analysis(code_analysis, "internal rules")

            # Step 2: Semantic search for internal rules
            semantic_results = self._semantic_search_internal_rules(embedding)

            logger.info(f"Semantic internal rules search found {len(semantic_results)} candidates")

            # Step 3: Apply hybrid ranking for internal rules
            ranking_engine = HybridRankingEngine('internal')
            ranked_rules = ranking_engine.rank_results(semantic_results, code_analysis)

            # Step 4: Return top results
            top_rules = ranked_rules[:limit]
            self._log_search_results(top_rules, "internal rules hybrid")

            return self.vector_search_helper.format_search_results_batch(
                [VectorSearchHelper.format_search_result(rule) for rule in top_rules]
            )

        except Exception as e:
            error_msg = f"Hybrid internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    # ========== Legacy Semantic Search Methods ==========

    def search_general_rules(
        self,
        embedding: List[float],
        lang: str,
        limit: int = 3
    ) -> List[dict]:
        """Search for general security rules using legacy semantic approach."""
        if not embedding:
            return []

        try:
            return self._search_general_rules_semantic_with_keywords(embedding, lang, limit)
        except Exception as e:
            error_msg = f"General rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    def search_internal_rules(
        self,
        embedding: List[float],
        limit: int = 2
    ) -> List[dict]:
        """Search for internal security policies using legacy semantic approach."""
        if not embedding:
            return []

        try:
            return self._search_internal_rules_semantic(embedding, limit)
        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    # ========== Internal Semantic Search Methods ==========

    def _semantic_search_general_rules(
        self,
        embedding: List[float],
        lang: str,
        semantic_limit: int = 50
    ) -> List[dict]:
        """Semantic search for general security rules."""
        try:
            points_data = self._client.scroll(
                collection_name="general_best_practices",
                limit=semantic_limit,
                with_payload=True,
                with_vectors=True
            )

            # Filter and process points
            security_rules_points = []
            for point in self.vector_search_helper.filter_security_points(points_data[0]):
                processed_point = self.vector_search_helper.process_search_point(point, embedding)
                if processed_point:
                    security_rules_points.append(processed_point)

            # Sort by similarity
            security_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            return security_rules_points

        except Exception as e:
            error_msg = f"Semantic search error: {e}"
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

    def _search_general_rules_semantic_with_keywords(
        self,
        embedding: List[float],
        lang: str,
        limit: int = 3
    ) -> List[dict]:
        """Legacy semantic search with basic keyword matching for backward compatibility."""
        try:
            points_data = self._client.scroll(
                collection_name="general_best_practices",
                limit=100,
                with_payload=True,
                with_vectors=True
            )

            # Filter security rules
            security_rules_points = []
            for point in self.vector_search_helper.filter_security_points(points_data[0]):
                processed_point = self.vector_search_helper.process_search_point(point, embedding)
                if processed_point:
                    security_rules_points.append(processed_point)

            logger.info(
                f"General rules search: {len(points_data[0])} total points, "
                f"{len(security_rules_points)} security rules"
            )

            # Sort by similarity and return top results
            security_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            top_rules = security_rules_points[:limit]

            self._log_search_results(top_rules, "general rules semantic")

            return [
                VectorSearchHelper.format_search_result(rule)
                for rule in top_rules
            ]

        except Exception as e:
            error_msg = f"General rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    def _search_internal_rules_semantic(
        self,
        embedding: List[float],
        limit: int = 2
    ) -> List[dict]:
        """Legacy semantic search for internal policies backward compatibility."""
        try:
            points_data = self._client.scroll(
                collection_name="internal_policies",
                limit=50,
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
                f"{len(internal_rules_points)} internal rules"
            )

            # Sort by similarity and return top results
            internal_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            top_rules = internal_rules_points[:limit]

            logger.info(f"Selected {len(top_rules)} best internal rules")

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

    def is_available(self) -> bool:
        """Check if Qdrant is available."""
        available, _ = self.test_connection()
        return available


# Add batch processing method to VectorSearchHelper
VectorSearchHelper.format_search_results_batch = staticmethod(lambda results: results)