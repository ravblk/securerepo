"""Code analysis module for security patterns detection."""
import re
from typing import List, Set
from dataclasses import dataclass

from .qdrant_config import SecurityCategory, CATEGORY_KEY_TO_ENUM, SecurityPatternsConfig
from .go_patterns import GoSecurityPatterns


@dataclass
class CodeAnalysisResult:
    """Result of code analysis for security-relevant keywords and patterns."""
    suspicious_keywords: List[str]
    suspicious_functions: List[str]
    library_calls: List[str]
    code_patterns: List[str]
    security_categories: Set[str]


class CodeAnalyzer:
    """Analyzes code for security-relevant patterns and keywords."""

    def __init__(self, default_lang: str = "python"):
        self.default_lang = default_lang
        self.config = SecurityPatternsConfig()

    def analyze_code_security(self, code: str, lang: str) -> CodeAnalysisResult:
        """Analyze code for security-relevant keywords and patterns."""
        lang = lang.lower().replace('-', '_') if lang else self.default_lang

        suspicious_keywords, relevant_categories = self._analyze_keywords(code, lang)

        suspicious_functions, library_calls, code_patterns = self._analyze_patterns(code, lang)

        # Use Go-specific patterns for Go language
        if lang == "go":
            self._apply_go_patterns(code, lang, suspicious_functions, suspicious_keywords, relevant_categories)

        return CodeAnalysisResult(
            suspicious_keywords=list(set(suspicious_keywords)),
            suspicious_functions=list(set(suspicious_functions)),
            library_calls=list(set(library_calls)),
            code_patterns=list(set(code_patterns)),
            security_categories=relevant_categories
        )

    def _analyze_keywords(self, code: str, lang: str) -> tuple[List[str], Set[str]]:
        """Analyze code for security-relevant keywords."""
        lang_keywords = self.config.get_keywords_for_language(lang.lower())

        suspicious_keywords = []
        relevant_categories = set()

        code_lower = code.lower()
        for category, keywords in lang_keywords.items():
            found_keywords = [kw for kw in keywords if kw in code_lower]
            if found_keywords:
                suspicious_keywords.extend(found_keywords)
                # Map category key to enum value using the mapping
                category_enum = CATEGORY_KEY_TO_ENUM.get(category)
                if category_enum:
                    relevant_categories.add(category_enum)

        return suspicious_keywords, relevant_categories

    def _analyze_patterns(self, code: str, lang: str) -> tuple[List[str], List[str], List[str]]:
        """Analyze code for suspicious patterns and extract library calls."""
        patterns = self.config.get_patterns_for_language(lang)
        suspicious_functions = []

        # Check regex patterns
        for pattern in patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            suspicious_functions.extend(matches)

        # Extract library calls and patterns
        library_calls = self._extract_library_calls(code, lang)
        code_patterns = self._extract_code_patterns(code, lang)

        return suspicious_functions, library_calls, code_patterns

    def _apply_go_patterns(self, code: str, lang: str, suspicious_functions: List[str],
                          suspicious_keywords: List[str], relevant_categories: Set[str]):
        """Apply Go-specific security patterns."""
        detected_patterns = GoSecurityPatterns.detect_patterns(code, lang)
        go_keywords = GoSecurityPatterns.get_security_keywords(code)

        suspicious_functions.extend([f"Go: {cat} - {pat[:40]}..." for cat, pat in detected_patterns])
        suspicious_keywords.extend(go_keywords)

        go_categories = GoSecurityPatterns.get_categories_from_keywords(go_keywords)
        for category in go_categories:
            category_enum = CATEGORY_KEY_TO_ENUM.get(category)
            if category_enum:
                relevant_categories.add(category_enum)

    def _extract_library_calls(self, code: str, lang: str) -> List[str]:
        """Extract library calls from code."""
        library_calls = []

        if lang == "python":
            # Python imports
            import_pattern = r"from\s+(\w+)|import\s+(\w+)"
            matches = re.findall(import_pattern, code, re.IGNORECASE)
            for match in matches:
                library_calls.extend([m for m in match if m])

            # Function calls
            call_pattern = r"(\w+)\.\w+\s*\("
            library_calls.extend(re.findall(call_pattern, code))
        elif lang == "javascript":
            # JavaScript require and imports
            library_calls.extend(re.findall(r"require\s*\(\s*['\"]([^'\"]+)['\"]", code))
            library_calls.extend(re.findall(r"import.*from\s+['\"]([^'\"]+)['\"]", code))

            # Method calls
            call_pattern = r"(\w+)\.\w+\s*\("
            library_calls.extend(re.findall(call_pattern, code))

        return [str(lib) for lib in library_calls if lib]

    def _extract_code_patterns(self, code: str, lang: str) -> List[str]:
        """Extract suspicious code patterns."""
        patterns = []

        if lang == "python":
            # String concatenation with user input
            if re.search(r'f["\'].*\{.*\}', code):
                patterns.append("f-string interpolation")

            # String format
            if re.search(r'\.format\s*\(', code):
                patterns.append("string formatting")

            # Direct SQL execution
            if re.search(r'execute\s*\([^)]*\+', code):
                patterns.append("sql concatenation")

        elif lang == "javascript":
            # Template literals
            if re.search(r'`.*\$\{.*\}`', code):
                patterns.append("template literal interpolation")

            # String concatenation in queries
            if re.search(r'["\'].*\+.*["\'].*execute', code):
                patterns.append("query concatenation")

        return patterns