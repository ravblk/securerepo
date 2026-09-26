import logging
from pathlib import Path
from typing import Optional

from tree_sitter import Parser
import tree_sitter_languages

from .config import settings
from .models import CodeChunk

logger = logging.getLogger(__name__)

_LANGUAGE_MAP = {"python": "python", "go": "go"}
_EXTENSION_MAP = {".py": "python", ".go": "go"}

_FUNCTION_NODE_TYPES = frozenset({
    "function_definition",       # python (методы — вложены в class_definition)
    "function_declaration",      # go: func
    "method_declaration",        # go: method
})

# Код вне функций: package-level секреты, конфиги — раньше невидимы
_TOP_LEVEL_TYPES = {
    "go": {"var_declaration", "const_declaration"},
    "python": {"assignment"},
}


def supported_extensions() -> dict[str, str]:
    return dict(_EXTENSION_MAP)


def _get_parser(lang: str) -> Parser:
    ts_name = _LANGUAGE_MAP.get(lang)
    if ts_name is None:
        raise ValueError(f"Unsupported language: {lang!r}")   # не тихий python-fallback
    parser = Parser()
    parser.set_language(tree_sitter_languages.get_language(ts_name))
    return parser


def _text(node, content: str) -> str:
    return content[node.start_byte:node.end_byte]


def _function_name(node, content: str) -> Optional[str]:
    for child in node.children:
        if child.type == "identifier":
            return _text(child, content)
    return None


def _cut_at_line_boundary(code: str, limit: int) -> tuple[str, bool]:
    """Рез по границе СТРОКИ. Никогда посреди комментария/идентификатора."""
    if len(code) <= limit:
        return code, False
    window = code[:limit]
    nl = window.rfind("\n")
    return (window[:nl] if nl > 0 else window), True


def _emit(chunks, file_path, code, start_line, function_name, part=None) -> None:
    chunks.append(CodeChunk(
        id=f"{file_path}:{start_line}" + (f"#{part}" if part else ""),
        file_path=str(file_path),
        function_name=function_name,
        class_name=None,
        code=code,
        start_line=start_line,
        end_line=start_line + code.count("\n"),   # честный конец РЕАЛЬНОГО текста
    ))


def _emit_function(node, content, file_path, chunks) -> None:
    """Функция → один чанк; длинную режем по statement'ам тела, не теряя хвост."""
    code = _text(node, content)
    start_line = node.start_point[0] + 1
    name = _function_name(node, content)

    if len(code) <= settings.max_code_length:
        _emit(chunks, file_path, code, start_line, name)
        return

    body = node.child_by_field_name("body")        # поле 'body' есть и в go, и в python
    signature = content[node.start_byte:body.start_byte].rstrip()
    statements = [s for s in body.named_children if _text(s, content).strip()]

    part, buf, buf_len = 1, [], len(signature)
    for stmt in statements:
        stmt_text = _text(stmt, content)
        if buf and buf_len + len(stmt_text) > settings.max_code_length:
            _emit(chunks, file_path, signature + "\n" + "\n".join(buf),
                  start_line, name, part=part)
            part += 1
            buf, buf_len = [], len(signature)
        buf.append(stmt_text)
        buf_len += len(stmt_text) + 1
    if buf:
        _emit(chunks, file_path, signature + "\n" + "\n".join(buf),
              start_line, name, part=part)


def parse_file(file_path: Path, lang: str) -> list[CodeChunk]:
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning(f"Cannot read {file_path}")
        return []

    parser = _get_parser(lang)
    tree = parser.parse(content.encode("utf-8"))
    root = tree.root_node

    chunks: list[CodeChunk] = []

    def _walk(node) -> None:
        if node.type in _FUNCTION_NODE_TYPES:
            _emit_function(node, content, file_path, chunks)
        elif node.type in _TOP_LEVEL_TYPES.get(lang, ()):      # код вне функций
            code, _ = _cut_at_line_boundary(_text(node, content), settings.max_code_length)
            if code.strip():
                _emit(chunks, file_path, code, node.start_point[0] + 1, None)
        for child in node.children:
            _walk(child)

    _walk(root)

    # Fallback: файл без функций не должен молча исчезать из аудита
    if not chunks:
        code, _ = _cut_at_line_boundary(content, settings.max_code_length)
        _emit(chunks, file_path, code, 1, None)

    return chunks