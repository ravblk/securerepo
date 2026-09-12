import logging
import re
import ast
import keyword
from typing import List, Optional, Set, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

from qdrant_client import QdrantClient

from .config import settings
from .exceptions import QdrantError
from .go_patterns import GoSecurityPatterns

logger = logging.getLogger(__name__)


class SecurityCategory(Enum):
    """Security categories for keyword classification."""
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    CODE_INJECTION = "code_injection"
    AUTH = "authentication"
    CRYPTO = "cryptography"
    INPUT_VALIDATION = "input_validation"
    FILE_OPERATIONS = "file_operations"
    NETWORK = "network"
    DATA_HANDLING = "data_handling"
    SESSION = "session"


@dataclass
class CodeAnalysisResult:
    """Result of code analysis for security-relevant keywords and patterns."""
    suspicious_keywords: List[str]
    suspicious_functions: List[str]
    library_calls: List[str]
    code_patterns: List[str]
    security_categories: Set[SecurityCategory]


class QdrantService:
    """Service for Qdrant vector database operations with hybrid search support."""

    # Security-relevant keywords per language
    KEYWORD_MAP = {
        "python": {
            "sql_injection": ["execute", "cursor", "query", "sql", "select", "insert", "update", "delete", "database", "db"],
            "xss": ["escape", "sanitize", "html", "render", "template", "script", "javascript"],
            "code_injection": ["eval", "compile", "exec", "__import__", "importlib", "subprocess", "os.system"],
            "auth": ["password", "login", "authenticate", "session", "token", "jwt", "auth", "encrypt", "decrypt"],
            "crypto": ["hash", "md5", "sha", "rsa", "aes", "crypto", "cipher", "key", "salt"],
            "input_validation": ["input", "form", "request", "user", "data", "sanitize", "validate"],
            "file_operations": ["open", "read", "write", "file", "upload", "download", "path"],
            "network": ["request", "http", "url", "api", "endpoint", "socket", "connect"],
            "data_handling": ["json", "xml", "pickle", "unpickle", "serializ", "deserializ"],
            "session": ["session", "cookie", "csrf", "xsrf", "token", "auth"]
        },
        "javascript": {
            "sql_injection": ["query", "sql", "execute", "database", "db", "orm", "sql"],
            "xss": ["innerhtml", "dangerouslysetinnerhtml", "escape", "sanitize", "html", "script"],
            "code_injection": ["eval", "function", "settimeout", "new function", "require"],
            "auth": ["password", "login", "auth", "token", "jwt", "session", "cookie"],
            "crypto": ["hash", "crypto", "encrypt", "decrypt", "key", "salt"],
            "input_validation": ["input", "form", "request", "user", "sanitize", "validate"],
            "file_operations": ["file", "upload", "download", "path", "fs"],
            "network": ["fetch", "ajax", "xmlhttprequest", "http", "api", "url"],
            "data_handling": ["json", "parse", "stringify", "eval", "function"],
            "session": ["session", "cookie", "token", "jwt", "auth"]
        },
        "go": {
            "sql_injection": ["query", "sql", "db", "database", "select", "insert", "update", "delete", "rows", "exec", "prepare", "querycontext"],
            "xss": ["escape", "sanitize", "html", "template", "script", "javascript", "execstandard", "exec", "template", "html"],
            "code_injection": ["eval", "exec", "command", "shell", "cmd", "run", "output", "start", "command", "sh", "bash", "powershell"],
            "auth": ["password", "login", "authenticate", "session", "token", "jwt", "auth", "encrypt", "decrypt", "bcrypt", "hash"],
            "crypto": ["hash", "crypto", "encrypt", "decrypt", "aes", "rsa", "sha", "md5", "cipher", "key", "salt", "pbkdf2", "scrypt"],
            "input_validation": ["input", "form", "request", "user", "data", "sanitize", "validate", "parse", "query"],
            "file_operations": ["open", "read", "write", "file", "upload", "download", "path", "io", "os", "filepath", "close"],
            "network": ["request", "http", "url", "api", "endpoint", "socket", "connect", "net", "dial", "listen", "get", "post", "put", "delete"],
            "data_handling": ["json", "xml", "marshal", "unmarshal", "encoding", "serializ", "deserializ"],
            "session": ["session", "cookie", "csrf", "xsrf", "token", "auth", "middleware", "context"]
        }
    }

    # Suspicious function patterns by language
    SUSPICIOUS_PATTERNS = {
        "python": [
            r"\.execute\s*\(",
            r"exec\s*\(",
            r"eval\s*\(",
            r"subprocess\.call\s*\(",
            r"os\.system\s*\(",
            r"open\s*\(",
            r"\.format\s*\(",
            r"f[\"'].*\{.*\}",
            r"pickle\.load",
            r"\.render\s*\(",
            r"\.escape\s*\("
        ],
        "javascript": [
            r"eval\s*\(",
            r"innerHTML\s*=",
            r"dangerouslySetInnerHTML\s*=",
            r"document\.write\s*\(",
            r"setTimeout\s*\(",
            r"new Function\s*\(",
            r"\.html\s*\(",
            r"\.exec\s*\("
        ],
        "go": [
            # SQL Injection patterns
            r"db\.Query\s*\([^)]*\+[^)]*\)",          # String concatenation in Query
            r"db\.Exec\s*\([^)]*\+[^)]*\)",           # String concatenation in Exec
            r"db\.QueryRow\s*\([^)]*\+[^)]*\)",       # String concatenation in QueryRow
            r"fmt\.Sprintf\s*\(\s*[\"'].*%s.*[\"']\s*,",  # String formatting with user input
            r"Query\s*\(\s*[\"'].*\+.*[\"']\s*",     # Direct concatenation in Query
            r"Exec\s*\(\s*[\"'].*\+.*[\"']\s*",      # Direct concatenation in Exec

            # XSS patterns
            r"template\.Execute\s*\(",                # Template execution (potential XSS if input not sanitized)
            r"exec\.Execute\s*\(",                   # exec.Execute for Windows (potential command injection)
            r"html\.Escape\s*\(",                    # HTML escaping (suspicious if missing in code)
            r"template\.New\s*\(",                   # Template creation
            r"template\.Parse\s*\(",                 # Template parsing

            # Code Injection/Command Execution patterns
            r"exec\.Command\s*\(\s*",                # Command execution
            r"exec\.Cmd\s*\(",                       # Command structure
            r"os\.Exec\s*\(",                        # Old exec package (dangerous)
            r"syscall\.Exec\s*\(",                   # Direct syscall exec
            r"sh\.Command\s*\(",                     # Shell command (if using shell wrappers)
            r"cmd\.Run\s*\(",                        # Running commands
            r"cmd\.Output\s*\(",                     # Getting command output
            r"cmd\.Start\s*\(",                      # Starting commands
            r"cmd\.CombinedOutput\s*\(",             # Combined command output

            # File operations (potential path traversal)
            r"os\.Open\s*\(",                        # File opening
            r"os\.Create\s*\(",                      # File creation
            r"os\.OpenFile\s*\(",                    # File opening with flags
            r"io\.ioutil\.WriteFile\s*\(",           # Writing files
            r"io\.ioutil\.ReadFile\s*\(",            # Reading files
            r"os\.ReadFile\s*\(",                    # Reading files
            r"os\.WriteFile\s*\(",                   # Writing files
            r"os\.Remove\s*\(",                      # File deletion
            r"os\.RemoveAll\s*\(",                   # Directory deletion
            r"os\.ReadDir\s*\(",                     # Reading directory
            r"os\.Mkdir\s*\(",                       # Creating directory
            r"os\.MkdirAll\s*\(",                    # Creating nested directories
            r"os\.Rename\s*\(",                      # Renaming files
            r"os\.Symlink\s*\(",                     # Creating symlinks (path traversal risk)

            # Network operations (potential SSRF, injection)
            r"net\.http\.Get\s*\(",                  # HTTP GET requests
            r"net\.http\.Post\s*\(",                 # HTTP POST requests
            r"http\.Client\s*\(",                    # HTTP client creation
            r"http\.NewRequest\s*\(",                # Creating HTTP requests
            r"request\.Do\s*\(",                     # Executing HTTP requests
            r"net\.dial\s*\(",                       # Network connections
            r"net\.listen\s*\(",                     # Network listening
            r"gnet\.dial\s*\(",                      # GNET dialing (if using gnet)
            r"grpc\.Dial\s*\(",                      # gRPC connections
            r"net\.url\.Parse\s*\(",                 # URL parsing (SSRF risk)

            # Data deserialization (potential injection)
            r"encoding/json\.Unmarshal\s*\(",        # JSON unmarshaling
            r"encoding/xml\.Unmarshal\s*\(",         # XML unmarshaling
            r"gob\.Decode\s*\(",                     # GOB decoding
            r"yaml\.Unmarshal\s*\(",                 # YAML unmarshaling (if using yaml package)

            # Template rendering (XSS risk)
            r"template\.Execute\s*\(",
            r"template\.ExecuteTemplate\s*\(",
            r"html/template\.Execute\s*\(",          # HTML template execution
            r"text/template\.Execute\s*\(",          # Text template execution

            # Cryptography (suspicious if weak algorithms)
            r"md5\.Sum\s*\(",                        # MD5 (weak)
            r"sha1\.Sum\s*\(",                       # SHA1 (weak)
            r"crypto/des\s*\(",                      # DES (weak)
            r"crypto/rc4\s*\(",                      # RC4 (weak)

            # Interpolation (potential injection)
            r"fmt\.Sprintf\s*\(",
            r"fmt\.Printf\s*\(",
            r"fmt\.Print.ln\s*\(",
            r"log\.Print\s*\(",                      # Log printing (potential info leak)
            r"log\.Printf\s*\(",
            r"log\.Println\s*\(",
            r"strings\.Join\s*\([^,]*\+.+",         # String concatenation with Join and +
            r"bytes\.Buffer\s*\(\)",                 # Buffer operations (if formed from user input)

            # Environment and system operations
            r"os\.Getenv\s*\(",                      # Get environment variables (potential injection)
            r"os\.Setenv\s*\(",                      # Set environment variables
            r"os\.Unsetenv\s*\(",                    # Unset environment variables
            r"os\.Environ\s*\(",                     # Environment access
            r"syscall\.Setuid\s*\(",                 # User ID change (privilege escalation risk)
            r"syscall\.Setgid\s*\(",                 # Group ID change
            r"runtime\.Goexit\s*\(",                 # Forced exit (potential DoS)
            r"runtime\.Exec\s*\(",                   # Runtime execution
        ]
    }

    def __init__(self, url: str = settings.qdrant_url) -> None:
        self._client = QdrantClient(url=url)
        self._default_lang = "python"

    def get_client(self) -> QdrantClient:
        """Get the Qdrant client instance."""
        return self._client

    def analyze_code_security(self, code: str, lang: str) -> CodeAnalysisResult:
        """Analyze code for security-relevant keywords and patterns."""
        lang = lang.lower() if lang else self._default_lang

        # Get keywords for the language
        lang_keywords = self.KEYWORD_MAP.get(lang, self.KEYWORD_MAP["python"])

        suspicious_keywords = []
        relevant_categories = set()

        # Check for suspicious keywords
        code_lower = code.lower()
        for category, keywords in lang_keywords.items():
            found_keywords = [kw for kw in keywords if kw in code_lower]
            if found_keywords:
                suspicious_keywords.extend(found_keywords)
                relevant_categories.add(SecurityCategory(category))

        # Check for suspicious patterns (regex-based)
        patterns = self.SUSPICIOUS_PATTERNS.get(lang, [])
        suspicious_functions = []
        code_patterns = []

        # Use Go-specific patterns for Go language
        if lang.lower() == "go":
            detected_patterns = GoSecurityPatterns.detect_patterns(code, "go")
            go_keywords = GoSecurityPatterns.get_security_keywords(code)
            suspicious_functions.extend([f"Go: {cat} - {pat[:40]}..." for cat, pat in detected_patterns])
            suspicious_keywords.extend(go_keywords)
            go_categories = GoSecurityPatterns.get_categories_from_keywords(go_keywords)
            for category in go_categories:
                relevant_categories.add(SecurityCategory(category))
        else:
            for pattern in patterns:
                matches = re.findall(pattern, code, re.IGNORECASE)
                suspicious_functions.extend(matches)

        # Extract library calls and common imports
        library_calls = self._extract_library_calls(code, lang)

        # Extract code patterns (continue for non-Go languages)
        if lang.lower() != "go":
            code_patterns = self._extract_code_patterns(code, lang)

        return CodeAnalysisResult(
            suspicious_keywords=list(set(suspicious_keywords)),
            suspicious_functions=list(set(suspicious_functions)),
            library_calls=library_calls,
            code_patterns=code_patterns,
            security_categories={SecurityCategory(cat.value) if isinstance(cat, str) else cat for cat in relevant_categories}
        )

    def _extract_library_calls(self, code: str, lang: str) -> List[str]:
        """Extract library calls from code."""
        library_calls = []

        if lang == "python":
            # Python imports and library calls
            import_pattern = r"(?:from\s+(\w+)|import\s+(\w+))"
            library_calls.extend(re.findall(import_pattern, code, re.IGNORECASE))

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

        return list(set(library_calls))

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

    def search_general_rules_hybrid(
        self,
        embedding: List[float],
        code: str,
        lang: str,
        limit: int = 3
    ) -> List[dict]:
        """
        Hybrid search combining semantic and keyword-based search for general security rules.

        This method improves upon pure semantic search by:
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

            logger.info(
                f"Code analysis found: {len(code_analysis.suspicious_keywords)} keywords, "
                f"{len(code_analysis.suspicious_functions)} suspicious functions, "
                f"{len(code_analysis.library_calls)} library calls, "
                f"{len(code_analysis.security_categories)} security categories"
            )

            # Step 2: Semantic search (using existing scroll approach)
            semantic_results = self._sematic_search_general_rules(embedding, lang)

            logger.info(f"Semantic search found {len(semantic_results)} candidates")

            # Step 3: Apply keyword-based scoring and fusion ranking
            ranked_rules = self._apply_hybrid_ranking(semantic_results, code_analysis, lang)

            # Step 4: Return top results
            top_rules = ranked_rules[:limit]

            # Log final results
            if top_rules:
                scores_str = ", ".join([f"{r['hybrid_score']:.3f}" for r in top_rules])
                logger.info(f"Selected {len(top_rules)} best rules via hybrid search (scores: [{scores_str}])")
            else:
                logger.warning(f"No best rules found via hybrid search")

            return [
                {
                    "rule_id": rule['rule_id'],
                    "text": rule['text'][:1000],
                    "url": rule['url']
                }
                for rule in top_rules
            ]

        except Exception as e:
            error_msg = f"Hybrid general rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []

    def _sematic_search_general_rules(
        self,
        embedding: List[float],
        lang: str,
        semantic_limit: int = 50
    ) -> List[dict]:
        """
        Semantic search for general security rules.
        Extracted from original search_general_rules method.
        """
        try:
            points_data = self._client.scroll(
                collection_name="general_best_practices",
                limit=semantic_limit,
                with_payload=True,
                with_vectors=True
            )

            security_rules_points = []
            for point in points_data[0]:
                payload = point.payload
                if any(key in payload for key in ["vulnerability_type", "sample_id", "code"]):
                    continue
                if not all(key in payload for key in ["title", "source"]):
                    continue

                try:
                    point_vector = point.vector
                    similarity = self._compute_cosine_similarity(embedding, point_vector)

                    # Get text content
                    text_content = point.payload.get("text", "")
                    if not text_content:
                        text_content = point.payload.get("content", "")
                    if not text_content:
                        text_content = point.payload.get("description", "")

                    security_rules_points.append({
                        'point': point,
                        'similarity': similarity,
                        'text': text_content,
                        'rule_id': point.payload.get("title", "unknown"),
                        'url': point.payload.get("url", ""),
                        'source': point.payload.get("source", ""),
                        'lang': point.payload.get("lang", "")
                    })
                except Exception as e:
                    logger.debug(f"Error processing point: {e}")
                    continue

            # Sort by similarity
            security_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            return security_rules_points

        except Exception as e:
            error_msg = f"Semantic search error: {e}"
            logger.error(error_msg)
            return []

    def _apply_hybrid_ranking(
        self,
        semantic_results: List[dict],
        code_analysis: CodeAnalysisResult,
        lang: str
    ) -> List[dict]:
        """
        Apply hybrid ranking combining semantic and keyword-based scoring.

        Score = 0.7 * semantic_score + 0.3 * keyword_score
        """
        ranked_rules = []

        for rule in semantic_results:
            rule_text = rule['text'].lower()
            rule_lang = rule.get('lang', '').lower() if rule.get('lang') else ''

            # Semantic score (normalized)
            semantic_score = rule['similarity']

            # Keyword score - check if rule text contains suspicious keywords
            keyword_score = 0.0

            # Boost for matching keywords
            for kw in code_analysis.suspicious_keywords:
                if kw in rule_text:
                    keyword_score += 0.1  # +0.1 for each matching keyword

            # Boost for matching security categories
            category_boost = 0.15  # +0.15 for matching security category
            for category in code_analysis.security_categories:
                if category.value in rule_text or category.value.replace('_', ' ') in rule_text:
                    keyword_score += category_boost

            # Language matching bonus
            if lang and rule_lang and lang.lower() == rule_lang:
                keyword_score += 0.05  # +0.05 for language match

            # Boost for suspicious functions matching rule content
            for func in code_analysis.suspicious_functions:
                if any(func in rule_text for func in code_analysis.suspicious_functions):
                    keyword_score += 0.05

            # Cap keyword score
            keyword_score = min(keyword_score, 0.5)

            # Hybrid score
            hybrid_score = 0.7 * semantic_score + 0.3 * keyword_score

            # Store hybrid score
            rule['hybrid_score'] = hybrid_score
            rule['keyword_score'] = keyword_score

            ranked_rules.append(rule)

        # Sort by hybrid score
        ranked_rules.sort(key=lambda x: x['hybrid_score'], reverse=True)

        return ranked_rules

    def search_general_rules(
        self,
        embedding: List[float],
        lang: str,
        limit: int = 3
    ) -> List[dict]:
        """Search for general security rules using hybrid semantic + keyword approach."""
        if not embedding:
            return []

        try:
            # Use hybrid search approach by default
            # Note: We need code for hybrid search, but legacy method doesn't have it
            # Fall back to semantic search with keyword analysis approximation

            # For backward compatibility, we use semantic search with basic keyword matching
            return self._search_general_rules_semantic_with_keywords(embedding, lang, limit)

        except Exception as e:
            error_msg = f"General rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
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

            # Фильтруем ТОЛЬКО правила безопасности (как в working примере)
            security_rules_points = []
            for point in points_data[0]:
                # Пропускаем точки с полями кода уязвимостей
                payload = point.payload
                if any(key in payload for key in ["vulnerability_type", "sample_id", "code"]):
                    continue
                # Пропускаем точки без базовых полей правил безопасности
                if not all(key in payload for key in ["title", "source"]):
                    continue

                # Вычисляем сходство только для правил безопасности
                try:
                    point_vector = point.vector
                    similarity = self._compute_cosine_similarity(embedding, point_vector)

                    # Получаем текст из разных полей
                    text_content = point.payload.get("text", "")
                    if not text_content:
                        text_content = point.payload.get("content", "")
                    if not text_content:
                        text_content = point.payload.get("description", "")

                    security_rules_points.append({
                        'point': point,
                        'similarity': similarity,
                        'text': text_content,
                        'rule_id': point.payload.get("title", "unknown"),
                        'url': point.payload.get("url", ""),
                        'source': point.payload.get("source", ""),
                        'lang': point.payload.get("lang", "")
                    })
                except Exception as e:
                    # Пропускаем точки с ошибками
                    logger.debug(f"Error processing point: {e}")
                    continue

            logger.info(f"General rules search: {len(points_data[0])} total points, {len(security_rules_points)} security rules")

            # Сортируем по similarity и берем top limit
            security_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            top_rules = security_rules_points[:limit]

            # Формируем список scores для логирования
            if top_rules:
                scores_str = ", ".join([f"{r['similarity']:.3f}" for r in top_rules])
            else:
                scores_str = "none"

            logger.info(f"Selected {len(top_rules)} best general rules (top scores: [{scores_str}])")

            return [
                {
                    "rule_id": rule['rule_id'],
                    "text": rule['text'][:1000],
                    "url": rule['url']
                }
                for rule in top_rules
            ]

        except Exception as e:
            error_msg = f"General rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []  # Return empty for graceful degradation

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

            logger.info(
                f"Code analysis for internal rules: {len(code_analysis.suspicious_keywords)} keywords, "
                f"{len(code_analysis.security_categories)} security categories"
            )

            # Step 2: Semantic search for internal rules
            semantic_results = self._semantic_search_internal_rules(embedding)

            logger.info(f"Semantic internal rules search found {len(semantic_results)} candidates")

            # Step 3: Apply hybrid ranking for internal rules
            ranked_rules = self._apply_hybrid_ranking_internal(semantic_results, code_analysis)

            # Step 4: Return top results
            top_rules = ranked_rules[:limit]

            if top_rules:
                scores_str = ", ".join([f"{r['hybrid_score']:.3f}" for r in top_rules])
                logger.info(f"Selected {len(top_rules)} best internal rules via hybrid search (scores: [{scores_str}])")
            else:
                logger.warning(f"No best internal rules found via hybrid search")

            return [
                {
                    "rule_id": rule['rule_id'],
                    "text": rule['text'][:1000],
                    "url": rule['url']
                }
                for rule in top_rules
            ]

        except Exception as e:
            error_msg = f"Hybrid internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
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

            internal_rules_points = []
            for point in points_data[0]:
                payload = point.payload
                if not all(key in payload for key in ["title", "text"]):
                    continue

                try:
                    point_vector = point.vector
                    similarity = self._compute_cosine_similarity(embedding, point_vector)

                    text_content = point.payload.get("text", "")[:1000]

                    internal_rules_points.append({
                        'point': point,
                        'similarity': similarity,
                        'text': text_content,
                        'rule_id': point.payload.get("title", "unknown"),
                        'url': point.payload.get("url", "")
                    })
                except Exception as e:
                    logger.debug(f"Error processing internal rule point: {e}")
                    continue

            # Sort by similarity
            internal_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            return internal_rules_points

        except Exception as e:
            error_msg = f"Semantic internal rules search error: {e}"
            logger.error(error_msg)
            return []

    def _apply_hybrid_ranking_internal(
        self,
        semantic_results: List[dict],
        code_analysis: CodeAnalysisResult
    ) -> List[dict]:
        """
        Apply hybrid ranking for internal security policies.
        Internal policies have different structure and needs.
        """
        ranked_rules = []

        for rule in semantic_results:
            rule_text = rule['text'].lower()

            # Semantic score (normalized)
            semantic_score = rule['similarity']

            # Keyword score - adapted for internal policies
            keyword_score = 0.0

            # Boost for matching keywords
            for kw in code_analysis.suspicious_keywords:
                if kw in rule_text:
                    keyword_score += 0.08  # Slightly lower boost for internal policies

            # Boost for matching security categories (internal policies are more category-specific)
            category_boost = 0.12  # Internal policies tend to be more category-focused
            for category in code_analysis.security_categories:
                if category.value in rule_text or category.value.replace('_', ' ') in rule_text:
                    keyword_score += category_boost

            # Boost for specific library/function mentions
            for lib in code_analysis.library_calls:
                if lib.lower() in rule_text:
                    keyword_score += 0.03

            # Boost for code patterns
            for pattern in code_analysis.code_patterns:
                if pattern in rule_text:
                    keyword_score += 0.05

            # Cap keyword score
            keyword_score = min(keyword_score, 0.4)  # Slightly lower cap for internal rules

            # Hybrid score with different weighting for internal rules
            # Internal rules benefit from keyword matching because they're more specific
            hybrid_score = 0.65 * semantic_score + 0.35 * keyword_score

            # Store hybrid score
            rule['hybrid_score'] = hybrid_score
            rule['keyword_score'] = keyword_score

            ranked_rules.append(rule)

        # Sort by hybrid score
        ranked_rules.sort(key=lambda x: x['hybrid_score'], reverse=True)

        return ranked_rules

    def search_internal_rules(
        self,
        embedding: List[float],
        limit: int = 2
    ) -> List[dict]:
        """Search for internal security policies using hybrid semantic + keyword approach."""
        if not embedding:
            return []

        try:
            # Use hybrid search with default code analysis
            # For backward compatibility when code is not available
            return self._search_internal_rules_semantic(embedding, limit)

        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
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
            # Используем scroll для получения внутренних правил
            points_data = self._client.scroll(
                collection_name="internal_policies",
                limit=50,  # Меньше точек для внутренних правил
                with_payload=True,
                with_vectors=True
            )

            # Фильтруем внутренние правила
            internal_rules_points = []
            for point in points_data[0]:
                # Пропускаем точки без базовых полей
                payload = point.payload
                if not all(key in payload for key in ["title", "text"]):
                    continue

                # Вычисляем сходство
                try:
                    point_vector = point.vector
                    similarity = self._compute_cosine_similarity(embedding, point_vector)

                    text_content = point.payload.get("text", "")[:1000]

                    internal_rules_points.append({
                        'point': point,
                        'similarity': similarity,
                        'text': text_content,
                        'rule_id': point.payload.get("title", "unknown"),
                        'url': point.payload.get("url", "")
                    })
                except Exception as e:
                    logger.debug(f"Error processing internal rule point: {e}")
                    continue

            logger.info(f"Internal rules search: {len(points_data[0])} total points, {len(internal_rules_points)} internal rules")

            # Сортируем по similarity и берем top limit
            internal_rules_points.sort(key=lambda x: x['similarity'], reverse=True)
            top_rules = internal_rules_points[:limit]

            logger.info(f"Selected {len(top_rules)} best internal rules")

            return [
                {
                    "rule_id": rule['rule_id'],
                    "text": rule['text'],
                    "url": rule['url']
                }
                for rule in top_rules
            ]

        except Exception as e:
            error_msg = f"Internal rules search error: {e}"
            logger.error(error_msg)
            logger.debug("Returning empty list instead of raising error for graceful degradation")
            return []  # Return empty for graceful degradation

    def _compute_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Вычисляет косинусное сходство между двумя векторами."""
        try:
            import math

            # Убеждаемся что векторы одной длины
            if len(vec1) != len(vec2):
                return 0.0

            # Dot product
            dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))

            # Magnitudes
            magnitude1 = math.sqrt(sum(v1 ** 2 for v1 in vec1))
            magnitude2 = math.sqrt(sum(v2 ** 2 for v2 in vec2))

            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0

            return dot_product / (magnitude1 * magnitude2)

        except Exception:
            return 0.0

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
