from pathlib import Path
from typing import Optional

from .models import FileLanguage


class LanguageDetector:
    """Detects programming language from file extensions."""

    EXTENSION_MAP = {
        ".py": FileLanguage(name="python", extension=".py"),
        ".go": FileLanguage(name="go", extension=".go"),
        ".js": FileLanguage(name="javascript", extension=".js"),
        ".ts": FileLanguage(name="typescript", extension=".ts"),
        ".java": FileLanguage(name="java", extension=".java"),
        ".cpp": FileLanguage(name="cpp", extension=".cpp"),
        ".c": FileLanguage(name="c", extension=".c"),
        ".cs": FileLanguage(name="csharp", extension=".cs"),
        ".rb": FileLanguage(name="ruby", extension=".rb"),
        ".php": FileLanguage(name="php", extension=".php"),
        ".swift": FileLanguage(name="swift", extension=".swift"),
        ".kt": FileLanguage(name="kotlin", extension=".kt"),
        ".rs": FileLanguage(name="rust", extension=".rs"),
        ".scala": FileLanguage(name="scala", extension=".scala"),
        ".dart": FileLanguage(name="dart", extension=".dart"),
    }

    @classmethod
    def detect(cls, file_path: str) -> str:
        """Detect programming language from file path."""
        path = Path(file_path)
        extension = path.suffix.lower()

        for ext, lang_info in cls.EXTENSION_MAP.items():
            if extension == ext:
                return lang_info.name

        # Default to python for unknown extensions
        return "python"

    @classmethod
    def get_supported_extensions(cls) -> list[str]:
        """Get list of supported file extensions."""
        return list(cls.EXTENSION_MAP.keys())
