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


class CodeSymbol(BaseModel):
    """Model for a code symbol (function/method) stored in database for Symbol-Context."""
    audit_id: str
    symbol: str
    symbol_type: str
    file_path: str
    start_line: int
    end_line: int
    code: str
    length: int
    package: Optional[str] = None
