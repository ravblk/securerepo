from pathlib import Path
from typing import Optional

from tree_sitter import Parser
import tree_sitter_languages

from .config import settings
from .models import CodeChunk

_LANGUAGE_MAP = {
    "python": "python",
    "go": "go",
}

_EXTENSION_MAP = {
    ".py": "python",
    ".go": "go",
}

_FUNCTION_NODE_TYPES = frozenset({
    "function_definition",
    "function_declaration",
    "method_declaration",
})


def supported_extensions() -> dict[str, str]:
    return dict(_EXTENSION_MAP)


def _get_parser(lang: str) -> Parser:
    parser = Parser()
    ts_lang_name = _LANGUAGE_MAP.get(lang, "python")
    parser.set_language(tree_sitter_languages.get_language(ts_lang_name))
    return parser


def _extract_function_name(node, content: str) -> Optional[str]:
    for child in node.children:
        if child.type == "identifier":
            return content[child.start_byte:child.end_byte]
    return None


def parse_file(file_path: Path, lang: str) -> list[CodeChunk]:
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    parser = _get_parser(lang)
    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception:
        return []

    chunks: list[CodeChunk] = []

    def _walk(node, depth: int) -> None:
        if depth > settings.max_walk_depth:
            return

        if node.type in _FUNCTION_NODE_TYPES:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            code = content[node.start_byte:node.end_byte]
            chunks.append(CodeChunk(
                id=f"{file_path}:{start_line}",
                file_path=str(file_path),
                function_name=_extract_function_name(node, content),
                class_name=None,
                code=code[:settings.max_code_length],
                start_line=start_line,
                end_line=end_line,
            ))

        for child in node.children:
            _walk(child, depth + 1)

    _walk(tree.root_node, 0)
    return chunks
