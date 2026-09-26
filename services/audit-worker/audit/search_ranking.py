"""Hybrid search ranking for security rules."""
import logging
from typing import List, Dict, Optional

from .code_analyzer import CodeAnalysisResult

logger = logging.getLogger(__name__)


class HybridRankingEngine:
    """Engine for hybrid ranking combining semantic and keyword-based scoring."""

    # Configuration for different search types
    GENERAL_RULES_CONFIG = {
        'semantic_weight': 0.7,
        'keyword_weight': 0.3,
        'keyword_match_boost': 0.1,
        'category_boost': 0.15,
        'language_boost': 0.05,
        'function_boost': 0.05,
        'max_keyword_score': 0.5
    }

    INTERNAL_RULES_CONFIG = {
        'semantic_weight': 0.65,
        'keyword_weight': 0.35,
        'keyword_match_boost': 0.08,
        'category_boost': 0.12,
        'language_boost': 0.05,
        'function_boost': 0.03,
        'library_boost': 0.03,
        'pattern_boost': 0.05,
        'max_keyword_score': 0.4
    }

    def __init__(self, config_type: str = 'general'):
        """Initialize ranking engine with specific configuration."""
        self.config = self._get_config(config_type)

    def _get_config(self, config_type: str) -> Dict:
        """Get configuration based on search type."""
        if config_type == 'internal':
            return self.INTERNAL_RULES_CONFIG.copy()
        return self.GENERAL_RULES_CONFIG.copy()

    def rank_results(self, semantic_results: List[Dict],
                    code_analysis: CodeAnalysisResult,
                    lang: Optional[str] = None) -> List[Dict]:
        """
        Apply hybrid ranking to semantic search results.

        Score = semantic_weight * semantic_score + keyword_weight * keyword_score
        """
        ranked_rules = []

        for rule in semantic_results:
            rule_text = rule['text'].lower()
            rule_lang = rule.get('lang', '').lower() if rule.get('lang') else ''

            # Semantic score
            semantic_score = rule['similarity']

            # Keyword score calculation
            keyword_score = self._calculate_keyword_score(
                rule_text, code_analysis, rule_lang, lang
            )

            # Cap keyword score
            keyword_score = min(keyword_score, self.config['max_keyword_score'])

            # Hybrid score
            hybrid_score = (
                self.config['semantic_weight'] * semantic_score +
                self.config['keyword_weight'] * keyword_score
            )

            # Store ranking data
            rule['hybrid_score'] = hybrid_score
            rule['keyword_score'] = keyword_score

            ranked_rules.append(rule)

        # Sort by hybrid score
        ranked_rules.sort(key=lambda x: x['hybrid_score'], reverse=True)

        return ranked_rules

    def _calculate_keyword_score(self, rule_text: str,
                                code_analysis: CodeAnalysisResult,
                                rule_lang: str, user_lang: Optional[str]) -> float:
        """Calculate keyword-based score for a rule."""
        keyword_score = 0.0

        # Boost for matching keywords
        for kw in code_analysis.suspicious_keywords:
            if kw in rule_text:
                keyword_score += self.config['keyword_match_boost']

        # Boost for matching security categories
        if hasattr(code_analysis, 'security_categories'):
            for category in code_analysis.security_categories:
                category_str = (category.value if hasattr(category, 'value')
                               else category)
                if category_str in rule_text or category_str.replace('_', ' ') in rule_text:
                    keyword_score += self.config['category_boost']

        # Language matching bonus
        if user_lang and rule_lang and user_lang.lower() == rule_lang:
            keyword_score += self.config['language_boost']

        # Boost for suspicious functions (for general rules)
        if 'function_boost' in self.config:
            for func in code_analysis.suspicious_functions:
                if func in rule_text:
                    keyword_score += self.config['function_boost']

        # Internal rules specific boosts
        if 'library_boost' in self.config:
            for lib in code_analysis.library_calls:
                if isinstance(lib, str) and lib.lower() in rule_text:
                    keyword_score += self.config['library_boost']

        if 'pattern_boost' in self.config:
            for pattern in code_analysis.code_patterns:
                if pattern in rule_text:
                    keyword_score += self.config['pattern_boost']

        return keyword_score