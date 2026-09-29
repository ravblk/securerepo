"""Symbol-Context Enricher for cross-chunk vulnerability analysis."""
import re
import logging
from typing import List, Dict, Optional, Set
import psycopg2
from .config import settings

logger = logging.getLogger(__name__)


# Python specific patterns
PYTHON_CALL_RE = re.compile(r'\b([a-zA-Z_]\w*)\s*\(')
PYTHON_METHOD_CALL_RE = re.compile(r'\b([a-zA-Z_]\w+)\.([a-zA-Z_]\w*)\s*\(')

# Go specific patterns
GO_FUNC_CALL_RE = re.compile(r'\b([a-zA-Z]+\.)?([A-Z]?\w+)\s*\(')
GO_METHOD_CALL_RE = re.compile(r'\b([a-z]\w+)\.([A-Z]\w+)\s*\(')

# Security patterns for Python
PYTHON_SINK_PATTERNS = (
    r'\b(os\.system|subprocess\.(run|call|Popen))\s*\(',
    r'\b(exec|eval)\s*\(',
    r'\b(pickle\.loads|pickle\.load)\s*\(',
    r'\bopen\s*\(',
    r'\b(shutil\.(copy|move|rmtree))\s*\(',
    r'\b(sqlalchemy\.(create_engine|text)|cursor\.(execute|executemany))\s*\(',
    r'\b(requests\.(get|post|put|delete))\s*\(',
    r'\b(urllib\.(request|parse))\s*\(',
    r'\b(PIL\.Image)\s*\(',
)

PYTHON_SOURCE_PATTERNS = (
    r'\b(request\.(flask.Request|args|form|files|json|headers))\s*\(',
    r'\b(os\.environ|environ\.get)\s*\(',
    r'\b(sys\.argv)\s*\(',
    r'\b(input\(.*\))\s*\(',
    r'\b(request\.(get_data|get_json))\s*\(',
)

# Security patterns for Go
GO_SINK_PATTERNS = (
    r'\b(exec\.Command)\s*\(',
    r'\b(os\.(OpenFile|Open|ReadFile|WriteFile))\s*\(',
    r'\b(sql\.(Open|DB\.Exec|DB\.Query|DB\.QueryRow))\s*\(',
    r'\b(http\.Get|http\.Post)\s*\(',
    r'\b(Exec|Query|QueryRow)\s*\(',
    r'\b(Open|OpenFile)\s*\(',
)

GO_SOURCE_PATTERNS = (
    r'\b(r\.(URL|Header|Form|FormValue|Query|Query\.Get|PostForm|PostFormValue|Body))\s*\(',
    r'\b(os\.Args|os\.Getenv)\s*\(',
    r'\b(flag\.(Args|Arg|String|Int))\s*\(',
)

# Name hints for security-relevant functions
SECURITY_NAME_HINTS = re.compile(
    r'^(sanitize|validate|parse|process|handle|exec|run|get|read|write|load|save|open|close|delete|escape|filter)', re.I
)

# Never resolve these (stdlib and common utilities)
SKIP_NAMES = {
    # Python stdlib
    'print', 'len', 'str', 'int', 'float', 'dict', 'list', 'set', 'tuple', 'bool', 'type', 'isinstance',
    'range', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'sum', 'min', 'max', 'abs', 'round',
    'open', 'close', 'read', 'write', 'file', 'Path', 'os', 'sys', 'json', 'time', 'datetime',
    'logging', 'random', 'math', 'collections', 'itertools', 'functools',
    # Go stdlib
    'fmt', 'log', 'http', 'os', 'io', 'strings', 'strconv', 'time', 'json', 'encoding',
    'reflect', 'context', 'sync', 'testing', 'errors', 'net', 'database/sql',
}


class SymbolContextEnricher:
    """Service for enriching code chunks with called function bodies for cross-chunk analysis."""

    def __init__(self, postgres_url: Optional[str] = None):
        """Initialize SymbolContextEnricher."""
        self._postgres_url = postgres_url or settings.postgres_url
        self._connection = None

    def _get_connection(self):
        """Get database connection."""
        try:
            if self._connection is None:
                self._connection = psycopg2.connect(self._postgres_url)
            return self._connection
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            return None

    def extract_calls(self, code: str, lang: str) -> Set[str]:
        """Extract function calls from code block.

        Args:
            code: Code content
            lang: Programming language

        Returns:
            Set of function names being called
        """
        calls = set()

        if lang == "python":
            calls.update(self._extract_python_calls(code))
        elif lang == "go":
            calls.update(self._extract_go_calls(code))
        else:
            logger.warning(f"Unsupported language for call extraction: {lang}")

        return calls

    def _extract_python_calls(self, code: str) -> Set[str]:
        """Extract function calls from Python code."""
        calls = set()

        # Simple bare function calls: func()
        for match in PYTHON_CALL_RE.finditer(code):
            name = match.group(1)
            if name and name not in SKIP_NAMES:
                calls.add(name)

        # Method calls: object.method()
        for match in PYTHON_METHOD_CALL_RE.finditer(code):
            name = match.group(2)
            if name and name not in SKIP_NAMES:
                calls.add(name)

        return calls

    def _extract_go_calls(self, code: str) -> Set[str]:
        """Extract function calls from Go code."""
        calls = set()

        # Package function calls: package.Func()
        for match in GO_FUNC_CALL_RE.finditer(code):
            name = match.group(2)
            if name and name not in SKIP_NAMES:
                calls.add(name)

        # Method calls: object.Method()
        for match in GO_METHOD_CALL_RE.finditer(code):
            name = match.group(2)
            if name and name not in SKIP_NAMES:
                calls.add(name)

        return calls

    def needs_context(self, code: str, lang: str) -> bool:
        """Check if code block needs context enrichment.

        Args:
            code: Code content
            lang: Programming language

        Returns:
            Boolean indicating if context is needed
        """
        if lang == "python":
            result = self._needs_context_python(code)
        elif lang == "go":
            result = self._needs_context_go(code)
        else:
            return False

        if result:
            logger.info(f"Chunk needs context enrichment (sink/source patterns found)")
        return result

    def _needs_context_python(self, code: str) -> bool:
        """Check if Python code has sink/source patterns."""
        for pattern in PYTHON_SINK_PATTERNS:
            if re.search(pattern, code):
                return True
        for pattern in PYTHON_SOURCE_PATTERNS:
            if re.search(pattern, code):
                return True
        return False

    def _needs_context_go(self, code: str) -> bool:
        """Check if Go code has sink/source patterns."""
        for pattern in GO_SINK_PATTERNS:
            if re.search(pattern, code):
                return True
        for pattern in GO_SOURCE_PATTERNS:
            if re.search(pattern, code):
                return True
        return False

    def rank_functions_to_resolve(
        self,
        extracted_calls: Set[str],
        code: str,
        lang: str,
        budget: int = 2000
    ) -> List[str]:
        """Rank functions to be resolved.

        Args:
            extracted_calls: Set of extracted function names
            code: Code content
            lang: Programming language
            budget: Character budget

        Returns:
            Ranked list of function names
        """
        ranked_functions = []

        for func_name in extracted_calls:
            score = self._calculate_function_score(func_name, code, lang)
            ranked_functions.append((func_name, score))

        # 按分数排序（从高到低）
        ranked_functions.sort(key=lambda x: x[1], reverse=True)

        # 选择前几个函数
        result = []
        current_budget = 0

        for func_name, _ in ranked_functions:
            if current_budget >= budget:
                break
            result.append(func_name)
            current_budget += len(func_name) * 50  # 估算每个函数代码大小

        return result

    def _calculate_function_score(self, func_name: str, code: str, lang: str) -> float:
        """Calculate function importance score.

        Args:
            func_name: Function name
            code: Code content
            lang: Programming language

        Returns:
            Importance score
        """
        score = 0.0

        # 安全性名称提示
        if SECURITY_NAME_HINTS.match(func_name):
            score += 10.0

        # Sink/source 模式中的参数使用
        sink_patterns = GO_SINK_PATTERNS if lang == "go" else PYTHON_SINK_PATTERNS
        source_patterns = GO_SOURCE_PATTERNS if lang == "go" else PYTHON_SOURCE_PATTERNS

        for pattern in sink_patterns:
            if func_name in re.sub(pattern, '', code):
                score += 8.0

        for pattern in source_patterns:
            if func_name in re.sub(pattern, '', code):
                score += 6.0

        # 函数长度（短函数通常更相关）
        if len(func_name) < 10:
            score += 2.0

        return score

    def get_context_symbols(
        self,
        audit_id: str,
        function_names: List[str],
        limit_per_function: int = 2
    ) -> Dict[str, List[dict]]:
        """Get function definitions from symbol table.

        Args:
            audit_id: Audit ID
            function_names: List of function names
            limit_per_function: Maximum number of definitions per function

        Returns:
            Dictionary with function names as keys and symbol definitions as values
        """
        conn = self._get_connection()
        if not conn:
            logger.error("No database connection available")
            return {}

        cursor = conn.cursor()
        result = {}

        try:
            # Check what's actually in the database for this audit
            cursor.execute("""
                SELECT COUNT(*) FROM symbols WHERE audit_id = %s
            """, (audit_id,))
            symbol_count = cursor.fetchone()[0]
            logger.info(f"✓ Total symbols in database for audit {audit_id}: {symbol_count}")

            if symbol_count > 0:
                # Get a sample of symbols for info
                cursor.execute("""
                    SELECT symbol, symbol_type, file_path, start_line
                    FROM symbols
                    WHERE audit_id = %s
                    ORDER BY length ASC
                    LIMIT 5
                """, (audit_id,))
                sample_symbols = cursor.fetchall()
                for sym in sample_symbols:
                    logger.info(f"   - {sym[0]} at {sym[2]}:{sym[3]}")

            for func_name in function_names:
                # Parameterized query
                cursor.execute("""
                    SELECT id, audit_id, symbol, symbol_type, file_path, start_line, end_line, code, length, package
                    FROM symbols
                    WHERE audit_id = %s AND symbol = %s
                    ORDER BY length ASC
                    LIMIT %s
                """, (audit_id, func_name, limit_per_function))

                columns = [desc[0] for desc in cursor.description]
                symbols = [dict(zip(columns, row)) for row in cursor.fetchall()]

                if symbols:
                    result[func_name] = symbols

            symbols_found = len(result)
            logger.info(f"✓ Retrieved context for {symbols_found} out of {len(function_names)} functions")

            logger.info(f"Retrieved context for {len(result)} out of {len(function_names)} functions")
            return result

        except Exception as e:
            logger.error(f"Error retrieving symbols: {e}")
            return {}
        finally:
            cursor.close()

    def format_context_for_prompt(self, context_symbols: Dict[str, List[dict]], max_length: int = 2000) -> str:
        """Format context symbols into a prompt string.

        Args:
            context_symbols: Dictionary of context symbols
            max_length: Maximum character count

        Returns:
            Formatted context string
        """
        if not context_symbols:
            return ""

        sections = []
        current_length = 0

        for func_name, symbols in context_symbols.items():
            for symbol in symbols:
                if current_length >= max_length:
                    break

                section = f"--- {symbol['file_path']}:{symbol['start_line']} {func_name}() ---\n"
                section += symbol['code'] + "\n"

                if current_length + len(section) <= max_length:
                    sections.append(section)
                    current_length += len(section)

        if not sections:
            return ""

        context_header = "CONTEXT: function bodies called from the code above.\n"
        context_header += "Use context to UNDERSTAND data flows. DO NOT FLAG vulnerabilities that exist only in context — quote ONLY lines from the main chunk in findings.\n\n"

        return context_header + "\n".join(sections)

    def enrich_chunk(
        self,
        code: str,
        audit_id: str,
        lang: str,
        local_functions: Optional[Set[str]] = None
    ) -> str:
        """Enrich code block with context.

        Args:
            code: Code content
            audit_id: Audit ID
            lang: Programming language
            local_functions: Set of locally defined functions

        Returns:
            Formatted context string, empty string if context not needed
        """
        # Check if context is needed
        if not self.needs_context(code, lang):
            return ""

        # Extract calls
        extracted_calls = self.extract_calls(code, lang)
        logger.info(f"📞 Extracted {len(extracted_calls)} function calls: {sorted(extracted_calls)}")

        # Remove locally defined functions
        if local_functions:
            extracted_calls = extracted_calls - local_functions

        # Remove skipped function names
        filtered_calls = extracted_calls - SKIP_NAMES

        if not filtered_calls:
            return ""

        # Rank functions
        ranked_functions = self.rank_functions_to_resolve(filtered_calls, code, lang)
        logger.info(f"📊 Ranked {len(ranked_functions)} functions to resolve: {ranked_functions}")

        if not ranked_functions:
            return ""

        # Get context symbols
        context_symbols = self.get_context_symbols(audit_id, ranked_functions)

        if not context_symbols:
            return ""

        # Format for prompt
        context = self.format_context_for_prompt(context_symbols)

        if context:
            logger.info(f"✓ Enriched chunk with Symbol-Context ({len(context)} characters)")

        return context

    def close(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            logger.debug("Database connection closed")


# 全局实例
_context_enricher: Optional[SymbolContextEnricher] = None


def get_context_enricher() -> SymbolContextEnricher:
    """Get global context enricher instance."""
    global _context_enricher
    if _context_enricher is None:
        _context_enricher = SymbolContextEnricher()
    return _context_enricher
