"""Security patterns and keyword mappings for code analysis."""
from dataclasses import dataclass
from typing import Dict, List, Set


class SecurityCategory:
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


# Mapping from lowercase category keys to category string values
CATEGORY_KEY_TO_ENUM = {
    "sql_injection": SecurityCategory.SQL_INJECTION,
    "xss": SecurityCategory.XSS,
    "code_injection": SecurityCategory.CODE_INJECTION,
    "auth": SecurityCategory.AUTH,
    "crypto": SecurityCategory.CRYPTO,
    "input_validation": SecurityCategory.INPUT_VALIDATION,
    "file_operations": SecurityCategory.FILE_OPERATIONS,
    "network": SecurityCategory.NETWORK,
    "data_handling": SecurityCategory.DATA_HANDLING,
    "session": SecurityCategory.SESSION,
}


class SecurityPatternsConfig:
    """Configuration for security patterns by language."""

    # Security-relevant keywords per language
    KEYWORD_MAP = {
        "python": {
            SecurityCategory.SQL_INJECTION: ["execute", "cursor", "query", "sql", "select", "insert", "update", "delete", "database", "db"],
            SecurityCategory.XSS: ["escape", "sanitize", "html", "render", "template", "script", "javascript"],
            SecurityCategory.CODE_INJECTION: ["eval", "compile", "exec", "__import__", "importlib", "subprocess", "os.system"],
            SecurityCategory.AUTH: ["password", "login", "authenticate", "session", "token", "jwt", "auth", "encrypt", "decrypt"],
            SecurityCategory.CRYPTO: ["hash", "md5", "sha", "rsa", "aes", "crypto", "cipher", "key", "salt"],
            SecurityCategory.INPUT_VALIDATION: ["input", "form", "request", "user", "data", "sanitize", "validate"],
            SecurityCategory.FILE_OPERATIONS: ["open", "read", "write", "file", "upload", "download", "path"],
            SecurityCategory.NETWORK: ["request", "http", "url", "api", "endpoint", "socket", "connect"],
            SecurityCategory.DATA_HANDLING: ["json", "xml", "pickle", "unpickle", "serializ", "deserializ"],
            SecurityCategory.SESSION: ["session", "cookie", "csrf", "xsrf", "token", "auth"]
        },
        "javascript": {
            SecurityCategory.SQL_INJECTION: ["query", "sql", "execute", "database", "db", "orm", "sql"],
            SecurityCategory.XSS: ["innerhtml", "dangerouslysetinnerhtml", "escape", "sanitize", "html", "script"],
            SecurityCategory.CODE_INJECTION: ["eval", "function", "settimeout", "new function", "require"],
            SecurityCategory.AUTH: ["password", "login", "auth", "token", "jwt", "session", "cookie"],
            SecurityCategory.CRYPTO: ["hash", "crypto", "encrypt", "decrypt", "key", "salt"],
            SecurityCategory.INPUT_VALIDATION: ["input", "form", "request", "user", "sanitize", "validate"],
            SecurityCategory.FILE_OPERATIONS: ["file", "upload", "download", "path", "fs"],
            SecurityCategory.NETWORK: ["fetch", "ajax", "xmlhttprequest", "http", "api", "url"],
            SecurityCategory.DATA_HANDLING: ["json", "parse", "stringify", "eval", "function"],
            SecurityCategory.SESSION: ["session", "cookie", "token", "jwt", "auth"]
        },
        "go": {
            SecurityCategory.SQL_INJECTION: ["query", "sql", "db", "database", "select", "insert", "update", "delete", "rows", "exec", "prepare", "querycontext"],
            SecurityCategory.XSS: ["escape", "sanitize", "html", "template", "script", "javascript", "execstandard", "exec", "template", "html"],
            SecurityCategory.CODE_INJECTION: ["eval", "exec", "command", "shell", "cmd", "run", "output", "start", "command", "sh", "bash", "powershell"],
            SecurityCategory.AUTH: ["password", "login", "authenticate", "session", "token", "jwt", "auth", "encrypt", "decrypt", "bcrypt", "hash"],
            SecurityCategory.CRYPTO: ["hash", "crypto", "encrypt", "decrypt", "aes", "rsa", "sha", "md5", "cipher", "key", "salt", "pbkdf2", "scrypt"],
            SecurityCategory.INPUT_VALIDATION: ["input", "form", "request", "user", "data", "sanitize", "validate", "parse", "query"],
            SecurityCategory.FILE_OPERATIONS: ["open", "read", "write", "file", "upload", "download", "path", "io", "os", "filepath", "close"],
            SecurityCategory.NETWORK: ["request", "http", "url", "api", "endpoint", "socket", "connect", "net", "dial", "listen", "get", "post", "put", "delete"],
            SecurityCategory.DATA_HANDLING: ["json", "xml", "marshal", "unmarshal", "encoding", "serializ", "deserializ"],
            SecurityCategory.SESSION: ["session", "cookie", "csrf", "xsrf", "token", "auth", "middleware", "context"]
        }
    }

    # Suspicious function patterns by language
    PATTERN_MAP = {
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
            r"db\.Query\s*\([^)]*\+[^)]*\)",
            r"db\.Exec\s*\([^)]*\+[^)]*\)",
            r"db\.QueryRow\s*\([^)]*\+[^)]*\)",
            r"fmt\.Sprintf\s*\(\s*[\"'].*%s.*[\"']\s*,",
            r"Query\s*\(\s*[\"'].*\+.*[\"']\s*",
            r"Exec\s*\(\s*[\"'].*\+.*[\"']\s*",

            # XSS patterns
            r"template\.Execute\s*\(",
            r"exec\.Execute\s*\(",
            r"html\.Escape\s*\(",
            r"template\.New\s*\(",
            r"template\.Parse\s*\(",

            # Code Injection/Command Execution patterns
            r"exec\.Command\s*\(\s*",
            r"exec\.Cmd\s*\(",
            r"os\.Exec\s*\(",
            r"syscall\.Exec\s*\(",
            r"sh\.Command\s*\(",
            r"cmd\.Run\s*\(",
            r"cmd\.Output\s*\(",
            r"cmd\.Start\s*\(",
            r"cmd\.CombinedOutput\s*\(",

            # File operations (potential path traversal)
            r"os\.Open\s*\(",
            r"os\.Create\s*\(",
            r"os\.OpenFile\s*\(",
            r"io\.ioutil\.WriteFile\s*\(",
            r"io\.ioutil\.ReadFile\s*\(",
            r"os\.ReadFile\s*\(",
            r"os\.WriteFile\s*\(",
            r"os\.Remove\s*\(",
            r"os\.RemoveAll\s*\(",
            r"os\.ReadDir\s*\(",
            r"os\.Mkdir\s*\(",
            r"os\.MkdirAll\s*\(",
            r"os\.Rename\s*\(",
            r"os\.Symlink\s*\(",

            # Network operations (potential SSRF, injection)
            r"net\.http\.Get\s*\(",
            r"net\.http\.Post\s*\(",
            r"http\.Client\s*\(",
            r"http\.NewRequest\s*\(",
            r"request\.Do\s*\(",
            r"net\.dial\s*\(",
            r"net\.listen\s*\(",
            r"gnet\.dial\s*\(",
            r"grpc\.Dial\s*\(",
            r"net\.url\.Parse\s*\(",

            # Data deserialization (potential injection)
            r"encoding/json\.Unmarshal\s*\(",
            r"encoding/xml\.Unmarshal\s*\(",
            r"gob\.Decode\s*\(",
            r"yaml\.Unmarshal\s*\(",

            # Template rendering (XSS risk)
            r"template\.Execute\s*\(",
            r"template\.ExecuteTemplate\s*\(",
            r"html/template\.Execute\s*\(",
            r"text/template\.Execute\s*\(",

            # Cryptography (suspicious if weak algorithms)
            r"md5\.Sum\s*\(",
            r"sha1\.Sum\s*\(",
            r"crypto/des\s*\(",
            r"crypto/rc4\s*\(",

            # Interpolation (potential injection)
            r"fmt\.Sprintf\s*\(",
            r"fmt\.Printf\s*\(",
            r"fmt\.Print.ln\s*\(",
            r"log\.Print\s*\(",
            r"log\.Printf\s*\(",
            r"log\.Println\s*\(",
            r"strings\.Join\s*\([^,]*\+.+",
            r"bytes\.Buffer\s*\(\)",

            # Environment and system operations
            r"os\.Getenv\s*\(",
            r"os\.Setenv\s*\(",
            r"os\.Unsetenv\s*\(",
            r"os\.Environ\s*\(",
            r"syscall\.Setuid\s*\(",
            r"syscall\.Setgid\s*\(",
            r"runtime\.Goexit\s*\(",
            r"runtime\.Exec\s*\(",
        ]
    }

    @classmethod
    def get_keywords_for_language(cls, lang: str) -> Dict[str, List[str]]:
        """Get security keywords for a specific language."""
        return cls.KEYWORD_MAP.get(lang.lower().replace('-', '_'), cls.KEYWORD_MAP.get("python", {}))

    @classmethod
    def get_patterns_for_language(cls, lang: str) -> List[str]:
        """Get security patterns for a specific language."""
        return cls.PATTERN_MAP.get(lang.lower().replace('-', '_'), [])