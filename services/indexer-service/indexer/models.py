from typing import Optional

from pydantic import BaseModel


class RepoMessage(BaseModel):
    repo_url: str
    branch: str
    lang: str
    audit_id: str
    token: Optional[str] = None


class CodeChunk(BaseModel):
    id: str
    file_path: str
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    code: str
    start_line: int
    end_line: int
