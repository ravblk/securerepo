import logging
import uuid
from pathlib import Path
from typing import Optional

from git import Repo

from .config import settings
from .models import CodeChunk
from .parsers import parse_file, supported_extensions

logger = logging.getLogger(__name__)


def clone_repo(url: str, branch: str, token: Optional[str]) -> Path:
    clone_dir = Path(settings.clone_root) / str(uuid.uuid4())
    clone_dir.mkdir(parents=True, exist_ok=True)

    if token:
        url = url.replace("https://", f"https://oauth2:{token}@")

    Repo.clone_from(url, clone_dir, branch=branch, depth=1)
    return clone_dir


def collect_chunks(repo_path: Path) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for ext, lang in supported_extensions().items():
        for file_path in repo_path.rglob(f"*{ext}"):
            if settings.skip_dirs & set(file_path.parts):
                continue
            try:
                chunks.extend(parse_file(file_path, lang))
            except Exception:
                logger.exception("Error parsing %s", file_path)
    return chunks
