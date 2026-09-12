"""
Go-specific suspicious patterns for security vulnerability detection.

Эти паттерны предназначены для детекции уязвимых паттернов в Go коде,
которые часто используются в атаках типа SQL Injection, XSS, Command Injection и других.
"""

import re
from typing import List, Tuple


class GoSecurityPatterns:
    """Комплексное обнаружение подозрительных паттернов в Go коде."""

    # Паттерны для SQL Injection (ухудшённые для многострочного кода)
    SQL_INJECTION_PATTERNS = [
        # String concatenation in SQL queries (простые паттерны)
        r'db\.Query\s*\(.*\+',
        r'db\.Exec\s*\(.*\+',
        r'db\.QueryContext\s*\(.*\+',
        r'db\.ExecContext\s*\(.*\+',
        r'query\s*:\s*".*".*\+',  # Улучшенный: query := "..." + ...
        r'Select\s*\(.*\+',       # Select-case (не путать с SQL SELECT)
        r'Query\s*\(.*\+',        # Общий шаблон Query с + (может быть false positive)
        # String formatting with user input (fmt.Sprintf, fmt.Sprintf)
        r'fmt\.Sprintf\s*\(.*%[s]?.*\+',
        # Direct concatenation
        r'"SELECT.*".*\+',  # SELECT... + user_input
        r'"INSERT.*".*\+',  # INSERT... + user_input
        r'"UPDATE.*".*\+',  # UPDATE... + user_input
        r'"DELETE.*".*\+',  # DELETE... + user_input
    ]

    # Паттерны для Command Injection
    COMMAND_INJECTION_PATTERNS = [
        r'exec\.Command\s*\(',
        r'os\.Exec\s*\(',
        r'syscall\.Exec\s*\(',
        r'cmd\s*:=\s*exec\.Command',  # cmd := exec.Command(...)
        r'\.Output\s*\(',            # cmd.Output()
        r'\.Run\s*\(',              # cmd.Run()
        r'\.Start\s*\(',            # cmd.Start()
        r'Shell\s*:',               # Shell := ...
        r'bash\s+-c',               # bash -c
        r'sh\s+-c',                 # sh -c
        r'eval\s*\(',               # eval() (редко в Go, но может быть через unsafe)
    ]

    # Паттерны для XSS (Cross-Site Scripting)
    XSS_PATTERNS = [
        r'template\.Execute\s*\(',
        r'\.Execute\s*\(',          # Go templates
        r'tmpl\.Execute\s*\(',      # tmpl.Execute()
        r'Parse\s*\(.*userInput',   # template.Parse(userInput)
        r'render\s*\(.*userInput',  # render(userInput)
        r'dangerouslySetInnerHTML', # React JSX (если есть Go/WASM)
        r'\.innerHTML\s*=',        # DOM manipulation (если есть Go JIT)
        r'html\.UnescapeString',   # html.UnescapeString
        r'UnescapeString\s*\(',    # Общий паттерн
    ]

    # Паттерны для File Operations (Path Traversal)
    FILE_OPERATION_PATTERNS = [
        r'os\.Open\s*\(',
        r'os\.OpenFile\s*\(',
        r'os\.Create\s*\(',
        r'os\.ReadFile\s*\(',
        r'os\.WriteFile\s*\(',
        r'os\.Remove\s*\(',
        r'os\.RemoveAll\s*\(',
        r'io\.ioutil\.WriteFile\s*\(',
        r'io\.ioutil\.ReadFile\s*\(',
        r'afero\.Open\s*\(',       # Afero library
        r'filepath\.Join\s*\(',    # filepath.Join (может уменьшить риск, но не полностью)
        r'\.Open\s*\(',            # Общий паттерн Open()
    ]

    # Паттерны для Network Operations (SSRF, XXE)
    NETWORK_OPERATION_PATTERNS = [
        r'net\.http\.Get\s*\(',
        r'http\.Get\s*\(',
        r'http\.Post\s*\(',
        r'http\.NewRequest\s*\(',
        r'request\.Do\s*\(',
        r'net\.Dial\s*\(',
        r'net\.Listen\s*\(',
        r'net\.DialTCP\s*\(',
        r'net\.DialUDP\s*\(',
        r'grpc\.Dial\s*\(',
        r'net\.url\.Parse\s*\(',
        'url\.Parse\s*\(',
    ]

    # Паттерны для Deserialization (Injection)
    DESERIALIZATION_PATTERNS = [
        r'encoding/json\.Unmarshal\s*\(',
        r'encoding/xml\.Unmarshal\s*\(',
        r'gob\.Decode\s*\(',
        r'yaml\.Unmarshal\s*\(',
        r'Unmarshal\s*\(',          # Общий паттерн
        r'Decode\s*\(',             # Общий паттерн
    ]

    # Паттерны для Cryptographic Weaknesses
    CRYPTO_PATTERNS = [
        r'md5\.Sum\s*\(',
        r'sha1\.Sum\s*\(',
        r'crypto/des\s*\(',
        r'crypto/rc4\s*\(',
        r'crypto/md5\s*\(',
        r'crypto/sha1\s*\(',
        r'AES\.NewCipher\s*\(',     # Обязательно проверить режим шифрования
        r'rsa\.GenerateKey\s*\(',   # Check key size
    ]

    # Паттерны для Environment Variable Injection
    ENV_PATTERNS = [
        r'os\.Getenv\s*\(',
        r'os\.Setenv\s*\(',
        r'os\.Unsetenv\s*\(',
        r'os\.Environ\s*\(',
        r'os\.ExpandEnv\s*\(',
    ]

    # Паттерны для Privilege Escalation
    PRIVILEGE_PATTERNS = [
        r'syscall\.Setuid\s*\(',
        r'syscall\.Setgid\s*\(',
        r'runtime\.Goexit\s*\(',
        r'runtime\.Exec\s*\(',
        r'Setuid\s*\(',
        r'Setgid\s*\(',
    ]

    # Паттерны для String Interpolation (потенциальное инъекция)
    INTERPOLATION_PATTERNS = [
        r'fmt\.Sprintf\s*\(',
        r'fmt\.Printf\s*\(',
        r'fmt\.Println\s*\(',
        r'log\.Printf\s*\(',
        r'log\.Println\s*\(',
        r'log\.Print\s*\(',
        r'fmt\.Print\s*\(',
        r'strings\.Join\s*\(',     # strings.Join(...) (может быть безопасно, но проверять)
    ]

    @staticmethod
    def detect_patterns(code: str, language: str = "go") -> List[Tuple[str, str]]:
        """
        Детектирует подозрительные паттерны в коде.

        Args:
            code: Исходный код для анализа
            language: Язык программирования (по умолчанию "go")

        Returns:
            List[Tuple[str, str]]: Список (категория_уязвимости, найденный_паттерн)
        """
        if language.lower() != "go":
            return []

        detected_patterns = []

        # Проверяем все категории
        pattern_categories = [
            ("SQL Injection", GoSecurityPatterns.SQL_INJECTION_PATTERNS),
            ("Command Injection", GoSecurityPatterns.COMMAND_INJECTION_PATTERNS),
            ("XSS", GoSecurityPatterns.XSS_PATTERNS),
            ("Path Traversal", GoSecurityPatterns.FILE_OPERATION_PATTERNS),
            ("Network Injection", GoSecurityPatterns.NETWORK_OPERATION_PATTERNS),
            ("Deserialization", GoSecurityPatterns.DESERIALIZATION_PATTERNS),
            ("Weak Cryptography", GoSecurityPatterns.CRYPTO_PATTERNS),
            ("Environment Injection", GoSecurityPatterns.ENV_PATTERNS),
            ("Privilege Escalation", GoSecurityPatterns.PRIVILEGE_PATTERNS),
            ("Interpolation", GoSecurityPatterns.INTERPOLATION_PATTERNS),
        ]

        for category, patterns in pattern_categories:
            for pattern in patterns:
                if re.search(pattern, code, re.DOTALL | re.IGNORECASE):
                    detected_patterns.append((category, pattern))
                    # Не прерываем после первого совпадения
                    # break  # Убираем break для поиска всех совпадений

        return detected_patterns

    @staticmethod
    def get_security_keywords(code: str) -> List[str]:
        """
        Извлекает security-keywords из Go кода.

        Returns:
            List[str]: Список найденных security-релевантных keywords
        """
        security_keywords = {
            # SQL Injection keywords
            "sql", "query", "execute", "select", "insert", "update", "delete", "database",
            "db", "rows", "exec", "prepare", "querycontext",

            # XSS keywords
            "html", "template", "escape", "sanitize", "javascript", "script",

            # Code Injection keywords
            "command", "shell", "cmd", "run", "output", "start", "sh", "bash", "powershell",

            # Auth keywords
            "password", "login", "authenticate", "session", "token", "jwt", "auth",
            "encrypt", "decrypt", "bcrypt", "hash",

            # Crypto keywords
            "hash", "crypto", "encrypt", "decrypt", "aes", "rsa", "sha", "md5", "cipher",
            "key", "salt", "pbkdf2", "scrypt",

            # Input Validation keywords
            "input", "form", "request", "user", "data", "sanitize", "validate", "parse",

            # File Operations keywords
            "file", "open", "read", "write", "upload", "download", "path", "io", "os",
            "filepath", "close",

            # Network keywords
            "request", "http", "url", "api", "endpoint", "socket", "connect", "net",
            "dial", "listen", "get", "post", "put", "delete",

            # Data Handling keywords
            "json", "xml", "marshal", "unmarshal", "encoding", "serialize", "deserialize",

            # Session keywords
            "session", "cookie", "csrf", "xsrf", "token", "auth", "middleware", "context",
        }

        code_lower = code.lower()
        found_keywords = [kw for kw in security_keywords if kw in code_lower]

        return found_keywords

    @staticmethod
    def get_categories_from_keywords(keywords: List[str]) -> set:
        """
        Классифицирует найденные keywords по категориям безопасности.

        Args:
            keywords: Список найденных security-keywords

        Returns:
            set: Набор security-категорий
        """
        category_mapping = {
            "sql_injection": ["sql", "query", "execute", "select", "insert", "update", "delete",
                            "database", "db", "rows", "exec", "prepare", "querycontext"],

            "xss": ["html", "template", "escape", "sanitize", "javascript", "script"],

            "code_injection": ["command", "shell", "cmd", "run", "output", "start",
                             "sh", "bash", "powershell"],

            "auth": ["password", "login", "authenticate", "session", "token", "jwt", "auth",
                   "encrypt", "decrypt", "bcrypt", "hash"],

            "crypto": ["hash", "crypto", "encrypt", "decrypt", "aes", "rsa", "sha", "md5",
                     "cipher", "key", "salt", "pbkdf2", "scrypt"],

            "input_validation": ["input", "form", "request", "user", "data", "sanitize",
                                "validate", "parse"],

            "file_operations": ["file", "open", "read", "write", "upload", "download",
                              "path", "io", "os", "filepath", "close"],

            "network": ["request", "http", "url", "api", "endpoint", "socket", "connect",
                       "net", "dial", "listen", "get", "post", "put", "delete"],

            "data_handling": ["json", "xml", "marshal", "unmarshal", "encoding", "serialize",
                            "deserialize"],

            "session": ["session", "cookie", "csrf", "xsrf", "token", "auth", "middleware",
                       "context"],
        }

        found_categories = set()
        keywords_lower = [kw.lower() for kw in keywords]

        for category, category_keywords in category_mapping.items():
            if any(kw in keywords_lower for kw in category_keywords):
                found_categories.add(category)

        return found_categories