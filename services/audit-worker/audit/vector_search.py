"""Vector search utilities for Qdrant operations."""
import math
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class VectorSearchHelper:
    """Helper class for vector search operations."""

    @staticmethod
    def compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Вычисляет косинусное сходство между двумя векторами."""
        try:
            if len(vec1) != len(vec2):
                logger.warning(f"Vector length mismatch: {len(vec1)} vs {len(vec2)}")
                return 0.0

            dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))
            magnitude1 = math.sqrt(sum(v1 ** 2 for v1 in vec1))
            magnitude2 = math.sqrt(sum(v2 ** 2 for v2 in vec2))

            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0

            return dot_product / (magnitude1 * magnitude2)

        except Exception as e:
            logger.error(f"Error computing cosine similarity: {e}")
            return 0.0

    @staticmethod
    def extract_text_content(payload: Dict) -> str:
        """Extract text content from payload with fallbacks."""
        for field in ["text", "content", "description"]:
            text = payload.get(field, "")
            if text:
                return text
        return ""

    @staticmethod
    def filter_security_points(points: List, skip_fields: Optional[List[str]] = None,
                              required_fields: Optional[List[str]] = None) -> List[Dict]:
        """Filter points to include internal security rules only."""
        if skip_fields is None:
            skip_fields = ["vulnerability_type", "sample_id", "code"]
        if required_fields is None:
            required_fields = ["title", "text"]

        filtered_points = []
        for point in points:
            payload = point.payload

            # Skip points with vulnerability code (examples, not rules)
            if any(key in payload for key in skip_fields):
                continue

            # Keep only points with required fields for internal policies
            if not all(key in payload for key in required_fields):
                continue

            filtered_points.append(point)

        return filtered_points

    @staticmethod
    def process_search_point(point, embedding: List[float]) -> Optional[Dict]:
        """Process a single search point with similarity calculation."""
        try:
            vector_search = VectorSearchHelper()

            point_vector = point.vector
            similarity = vector_search.compute_cosine_similarity(embedding, point_vector)

            return {
                'point': point,
                'similarity': similarity,
                'text': vector_search.extract_text_content(point.payload),
                'rule_id': point.payload.get("title", "unknown"),
                'url': point.payload.get("url", ""),
                'source': point.payload.get("source", ""),
                'lang': point.payload.get("lang", "")
            }
        except Exception as e:
            logger.debug(f"Error processing point: {e}")
            return None

    @staticmethod
    def format_search_result(rule: Dict, max_length: int = 1000) -> Dict:
        """Format a search result for API response."""
        return {
            "rule_id": rule['rule_id'],
            "text": rule['text'][:max_length],
            "url": rule['url']
        }