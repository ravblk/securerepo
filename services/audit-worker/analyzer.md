# Analyzer — механизм логического вывода

Это сердце системы — **механизм логического вывода (Inference Engine)** для Zero-Shot анализа безопасности кода с Symbol-Context поддержкой.

---

## Архитектура: Zero-Shot Security Analysis с Symbol-Context

LLM выполняет независимый анализ безопасности кода, используя свои знания о CWE-ID и уязвимостях, с enhanced контекстом через Symbol-Context.

**Ключевое отличие:** LLM не зависит от внешних наборов правил и самостоятельно идентифицирует уязвимости с поддержкой cross-chunk анализа через tables символов.

---

## Pipeline (Zero-Shot + Symbol-Context оптимизирован)

```
[compute_embedding] ─▶ [enrich_context] ─▶ [retrieve_internal_rules] ─▶ [zero_shot_analyze] ─▶ [validate]
```

**Шаги:**
1. **compute_embedding**: Расчёт эмбеддинга кода (один раз, кэшируется в state)
2. **enrich_context**: Symbol-Context enrichment — резолв вызванных функций из таблицы символов
3. **retrieve_internal_rules**: Эмбеддинг → Qdrant `internal_policies` (ТОЛЬКО 3 правила как контекст)
4. **zero_shot_analyze**: Zero-Shot LLM анализ с Cross-Chunk контекстом — самостоятельный поиск ВСЕХ уязвимостей с CWE-ID
5. **validate**: Валидация CWE формата + grounding + guardrails
6. **хранение**: Сохранение результатов в PostgreSQL

---

## Шаг 1: Семантический поиск (Semantic RAG)

Эмбеддинг кода (model: `BAAI/bge-m3`, 1024 dim) рассчитывается **один раз** и кэшируется в state:

```python
def compute_embedding(state: AuditState) -> dict:
    code = state["code"]
    embedding = get_embedding(code[:5000])
    return {"code_embedding": embedding or []}
```

Поиск ТОЛЬКО 3 наиболее релевантных внутренних правил:

```python
# Семантический поиск ТОЛЬКО в internal policies
results = client.search(
    collection_name="internal_policies",
    query_vector=embedding,
    limit=3  # ТОЛЬКО 3 правила для zero-shot контекста
)
```

**Почему именно 3:**
- Достаточно контекста для улучшения качества анализа без перегрузки
- Перегрузка не требует больших вычислений
- Оптимальный баланс между контекстом и скоростью
- Минимальный контекст для Zero-Shot анализа

---

## Шаг 2: Symbol-Context Enrichment (Cross-Chunk Analysis)

**Критическое улучшение:** Пока чанковый анализ автоматический слеп к cross-chunk уязвимостям,Symbol-Context это исправляет.

### Механика работы

1. **Извлечение вызовов:** Определяем, какие функции вызываются в текущем чанке

```python
# специфика для Python
PYTHON_SINK_PATTERNS = (
    r'\b(os\.system|subprocess\.(run|call|Popen))\s*\(',
    r'\b(exec|eval)\s*\(',
    r'\b(sqlalchemy\.(create_engine|text)|cursor\.(execute|executemany))\s*\(',
)

# специфика для Go
GO_SINK_PATTERNS = (
    r'\b(exec\.Command)\s*\(',
    r'\b(sql\.(Open|DB\.Exec|DB\.Query|DB\.QueryRow))\s*\(',
)

def extract_calls(code: str, lang: str) -> Set[str]:
    """Извлекает вызовы функций, только если есть sink/source паттерны"""
    calls = set()
    if needs_context(code, lang):  # проверка на sink/source
        if lang == "python":
            calls.update(PYTHON_CALL_RE.findall(code))
        elif lang == "go":
            calls.update(GO_FUNC_CALL_RE.findall(code))
    return calls - SKIP_NAMES  # исключаем stdlib
```

2. **Определение ранга:** Выбираем, какие функции нужно резолвить

```python
def rank_functions_to_resolve(extracted_calls, code, lang, budget=2000):
    """Ранжирование по безопасности → имени → размеру"""
    scored = []
    for func_name in extracted_calls:
        score = 0
        if SECURITY_NAME_HINTS.match(func_name):  # sanitize*, validate*, etc.
            score += 10.0
        if func_name in sink_patterns:
            score += 8.0
        if func_name in source_patterns:
            score += 6.0
        scored.append((func_name, score))

    # Выбираем до 2000 символов контекста
    sorted_by_score = sorted(scored, key=lambda x: -x[1])
    return [f for f, s in sorted_by_score if current_budget + len(f)*50 < budget]
```

3. **Резолв из таблицы символов:** Получаем тела функций из PostgreSQL

```python
def get_context_symbols(audit_id: str, function_names: List[str]) -> Dict[str, List[dict]]:
    """Запрос к PostgreSQL таблице symbols"""
    result = {}
    for func_name in function_names:
        cursor.execute("""
            SELECT id, audit_id, symbol, symbol_type, file_path, start_line, end_line, code, length, package
            FROM symbols
            WHERE audit_id = %s AND symbol = %s
            ORDER BY length ASC
            LIMIT 2
        """, (audit_id, func_name))

        symbols = [dict(zip(columns, row)) for row in cursor.fetchall()]
        if symbols:
            result[func_name] = symbols
    return result
```

4. **Форматирование для LLM:** Подготовка prompта с контекстом

```python
def format_context_for_prompt(context_symbols: Dict[str, List[dict]]) -> str:
    """Format context section with warning about citation rules"""
    sections = []
    for func_name, symbols in context_symbols.items():
        for symbol in symbols:
            section = f"--- {symbol['file_path']}:{symbol['start_line']} {func_name}() ---\n"
            section += symbol['code'] + "\n"
            sections.append(section)

    context_header = "КОНТЕКСТ: тела функций, вызываемых из кода выше.\n"
    context_header += "Используй контекст для ПОНИМАНИЯ потоков данных. "
    context_header += "НЕ ФЛАГАЙ уязвимости, находящиеся только в контексте — "
    context_header += "в находке цитируй ТОЛЬКО строки из основного чанка.\n\n"

    return context_header + "\n".join(sections)
```

### Cross-Chunk Detection Пример

**Без Symbol-Context (System слеп):**
```python
# ЧАНК 1: бросивающий source
def handle_request(w, r):
    user_input = r.url.query.get("id")   # ← tainted source
    process_input(user_input)            # ← модель видит вызов, но не тело
```

**С Symbol-Context (System видит связку):**
```python
# ЧАНК 1 + CONTEXT: source (вы видите оба)
def handle_request(w, r):
    user_input = r.url.query.get("id")   # ← tainted source
    process_input(user_input)            # ← резолвится в контекст!

# КОНТЕКСТ: processInput() из ЧАНКА 2 (подгружен из таблицы symbols)
def process_input(input):
    query = f"SELECT * FROM users WHERE id='{input}'"  # ← SQL injection!
    db.exec(query)                                  # ← LLM теперь видит связку source→sink!
```

---

## Шаг 3: Zero-Shot LLM Анализ кода с Symbol-Context

LLM получает код + 7 внутренних правил + Symbol-Context как расширенный контекст:

```python
from langchain_core.messages import SystemMessage

SYSTEM_PROMPT = """Ты — экспертная система Zero-Shot анализа безопасности кода с Symbol-Context поддержкой.
Твоя задача: самостоятельно найти ВСЕ уязвимости безопасности в предоставленном коде,
определить их CWE-ID и точные строки.
С Symbol-Context ты можешь видеть вызываемые функции и анализировать cross-chunk потоки данных.

## ПРИНЦИПЫ АНАЛИЗА (ZERO-SHOT с Cross-Chunk):

1. **Полный сканирование без ограничений**: Ты обязан найти абсолютно все уязвимости независимо от категории
2. **Точная идентификация CWE**: Для каждой уязвимости определи точный CWE ID из стандарта MITRE CWE
3. **Точные строки кода**: Укажи конкретную строку кода, где находится уязвимость
4. **Независимый анализ**: Не перегружайся предоставленными правилами - они только контекст
5. **Cross-Chunk анализ**: Используй Symbol-Context для анализа входов/выходов через границы функций

## ВНУТРЕННИЕ ПРАВИЛА (ДОПОЛНЕНИЕ, ТОЛЬКО 3 ШТ):
{rules}

{optimized_context}

## КОД ДЛЯ АНАЛИЗА:
Язык: {lang} | Файл: {file_path}
{code}

## ТРЕБОВАНИЯ К ОТВЕТУ:

Каждая обнаруженная уязвимость должна содержать:
1. **Точный CWE ID** (формат: CWE-XXX)
2. **Описание проблемы** с указанием конкретного места в коде
3. **Severity** (Critical/High/Medium/Low) в соответствии с CWE official severity
4. **Точная строка кода** где находится уязвимость (обязательно должна существовать в основном коде)
5. **URL** на MITRE CWE описание идентификатора

## ФОРМАТ ОТВЕТА (JSON):
{{
  "violations": [
    {{
      "rule_id": "Точный CWE ID (например: CWE-89)",
      "rule_url": "Полный URL на MITRE CWE в формате: https://cwe.mitre.org/data/definitions/XXX.html где XXX - номер CWE",
      "severity": "Critical | High | Medium | Low",
      "explanation": "Детальное объяс vulnerabilitiy с указанием конкретного места в коде",
      "vulnerable_line": "Точная строка кода (обязательно должна существовать в основном коде)"
    }}
  ]
}}

ВАЖНОЕ ТРЕБОВАНИЕ:
- Найди **ВСЕ** уязвимости, даже если их много
- Точное совпадение строки кода обязательно (только из основного кода, не из контекста)
- CWE ID должны быть корректными стандартными идентификаторами
- Внутренние правила и Symbol-Context только как контекст для понимания потоков данных
- Используй контекст для анализа cross-chunk уязвимостей, но цитируй только из основного кода
- Если уязвимостей нет - верни пустой массив

ВАЖНО: В ответ должен быть ТОЛЬКО валидный JSON без других текстовых комментариев."""

# Zero-Shot анализ с Symbol-Context поддержкой
response = llm.invoke([SystemMessage(content=system_prompt)])
```

**Key Features:**
- **Independent reasoning**: LLM использует свои знания о CWE-ID и уязвимостях
- **3 rules augmentation**: Внутренние правила улучшают качество, но не ограничивают
- **Symbol-Context cross-chunk**: Позволяет увидеть связку source→sink через границы функций
- **Comprehensive coverage**: Сканирование ВСЕХ категорий уязвимостей

---

## Шаг 4: Валидация Zero-Shot результатов

1. **CWE Format Check:** `CWE-\d+` pattern validation
2. **Grounding Check:** Проверяем, что `vulnerable_line` содержится в коде
3. **Guardrails:** JSON структура, severity consistency, качество объяснений

```python
# CWE format validation
CWE_PATTERN = r'^CWE-\d+$'
validated_cwe_violations = [
    v for v in grounded_violations
    if re.match(CWE_PATTERN, v.get("rule_id", ""))
]

# Grounding validation
grounded_violations = [
    v for v in violations
    if v.get("vulnerable_line", "") in code
]
```

---

## Шаг 5: Надёжность Kafka

Ручной коммит offset после успешной записи в PostgreSQL:

```python
# consume_tasks()
consumer = KafkaConsumer(
    AUDIT_TASKS_TOPIC,
    enable_auto_commit=False  # Ручной коммит
)

# Обработка с надежной дубль-блокировкой
try:
    violations, severity = process_task(task)
    save_result_to_db(...)    # Запись в БД
    consumer.commit()          # Коммит ПОСЛЕ записи
except Exception as e:
    # Не коммитим — сообщение будет переобработано
    send_status_to_kafka(task.audit_id, "failed", error=str(e))
```

---

## Хранение

PostgreSQL таблицы:

```sql
-- Уже существующая таблица для результатов аудита
CREATE TABLE audit_results (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    findings JSONB NOT NULL,
    severity VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Новая таблица для Symbol-Context (Migration 005)
CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    symbol_type VARCHAR(50) NOT NULL,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    code TEXT NOT NULL,
    length INTEGER NOT NULL,
    package VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (audit_id) REFERENCES audits(id) ON DELETE CASCADE
);
```

---

## Оптимизация: Grounding Check

Для надёжности валидации используем fuzzy matching:

```python
import difflib

def is_grounded(vuln_line: str, code: str) -> bool:
    """Проверка что строка реально есть в коде (с учётом whitespace)"""
    code_normalized = ' '.join(code.split())
    line_normalized = ' '.join(vuln_line.split())

    # Точное совпадение
    if line_normalized in code_normalized:
        return True

    # Fuzzy matching
    ratio = difflib.SequenceMatcher(None, line_normalized, code_normalized).ratio()
    return ratio > 0.8
```

---

## Zero-Shot + Symbol-Context Преимущества

### По сравнению с традиционным RAG:
- **Broader coverage**: LLM находит уязвимости вне предоставленных правил
- **CWE accuracy**: Точные идентификаторы из MITRE CWE standard
- **Adaptable**: Автоматически адаптируется к новым типам уязвимостей
- **Context efficient**: 3 правила вместо сотен для покрытия
- **Cross-Chunk detection**: System видит связку source→sink через границы функций

### Symbol-Context конкретика:
- **Пополнение blind spots**: Чанковый анализ слеп к cross-chunk уязвимостям, Symbol-Context закрывает этот пробел
- **Снижение false positives**: Модель видит protective functions (`safeID()`, `sanitizeInput()`, `validateRef()`)
- **Улучшение recall**: Детекция цепочек source→sink через несколько файлов
- **Языковая специфика**: Разные sink/source паттерны для Python и Go

### Ограничения:
- **Hallucination risk**: Требуется строгий guardrails контроль
- **CWE awareness**: LLM должен быть обучен на CWE стандарт
- **Grounding verification**: Необходима проверка уязвимых строк
- **Symbol-Context constraints**: Не решает межрепозиторные вызовы, динамическая диспетчеризация (`map[string]func`), reflection
- **Контекстик ограничения**: максимум ~2000 символов контекста на чанк
- **Database overhead**: PostgreSQL нагрузка для хранения символов

---

## Архитектурные решения

### Why 7 Internal Rules?
- **Context coverage**: Достаточно для улучшения качества без перегрузки
- **Performance**: Баланс между глубиной и скоростью
- **Focus**: Специфические корпоративные политики безопасности

### Zero-Shot Primary, Rules Secondary
- **LLM leads**: Независимый анализ всех категорий уязвимостей
- **Rules augment**: Улучшают точность специфических контекстов
- **Symbol-Context bridges**: Позволяет видеть cross-chunk потоки данных

### Symbol-Context Importance
- **Cross-chunk detection**: Самый недооценённый источник ложных пропусков у LLM-аудиторов
- **Automatic taint analysis**: LLM видит связку source→sink без явного taint анализа
- **False positive reduction**: Модель видит защитные функции и не флагирует защищённый код

### Guardrails Essential
- **CWE validation**: Формат CWE-\d+ pattern
- **Grounding check**: Строки должны существовать в коде
- **Quality control**: JSON структура, severity consistency
- **Context citation check**: Требуется, чтобы уязвимости были найдены в основном чанке, не только в контексте

---

## Symbol-Context Implementation Details

### Python Specific Patterns

**Sink Patterns:**
```python
PYTHON_SINK_PATTERNS = (
    r'\b(os\.system|subprocess\.(run|call|Popen))\s*\(',
    r'\b(exec|eval)\s*\(',
    r'\b(pickle\.loads|pickle\.load)\s*\(',
    r'\b(open\s*\(',
    r'\b(shutil\.(copy|move|rmtree))\s*\(',
    r'\b(sqlalchemy\.(create_engine|text)|cursor\.(execute|executemany))\s*\(',
    r'\b(requests\.(get|post|put|delete))\s*\(',
    r'\b(urllib\.(request|parse))\s*\(',
    r'\b(PIL\.Image)\s*\(',
)
```

**Source Patterns:**
```python
PYTHON_SOURCE_PATTERNS = (
    r'\b(request\.(flask.Request|args|form|files|json|headers))\s*\(',
    r'\b(os\.environ|environ\.get)\s*\(',
    r'\b(sys\.argv)\s*\(',
    r'\b(input\(.*\))\s*\(',
    r'\b(request\.(get_data|get_json))\s*\(',
)
```

### Go Specific Patterns

**Sink Patterns:**
```go
GO_SINK_PATTERNS = (
    r'\b(exec\.Command)\s*\(',
    r'\b(os\.(OpenFile|Open|ReadFile|WriteFile))\s*\(',
    r'\b(sql\.(Open|DB\.Exec|DB\.Query|DB\.QueryRow))\s*\(',
    r'\b(http\.Get|http\.Post)\s*\(',
    r'\b(Exec|Query|QueryRow)\s*\(',
    r'\b(Open|OpenFile)\s*\(',
)
```

**Source Patterns:**
```go
GO_SOURCE_PATTERNS = (
    r'\b(r\.(URL|Header|Form|FormValue|Query|Query\.Get|PostForm|PostFormValue|Body))\s*\(',
    r'\b(os\.Args|os\.Getenv)\s*\(',
    r'\b(flag\.(Args|Arg|String|Int))\s*\(',
)
```

### Ranking Algorithm

```python
def _calculate_function_score(func_name: str, code: str, lang: str) -> float:
    """Score functions based on security relevance"""
    score = 0.0

    # Security name hints
    if SECURITY_NAME_HINTS.match(func_name):
        score += 10.0

    # Sink/source pattern usage
    sink_patterns = GO_SINK_PATTERNS if lang == "go" else PYTHON_SINK_PATTERNS
    source_patterns = GO_SOURCE_PATTERNS if lang == "go" else PYTHON_SOURCE_PATTERNS

    for pattern in sink_patterns:
        if func_name in re.sub(pattern, '', code):
            score += 8.0

    for pattern in source_patterns:
        if func_name in re.sub(pattern, '', code):
            score += 6.0

    # Function length (shorter functions are often more relevant)
    if len(func_name) < 10:
        score += 2.0

    return score
```

---

## Symbol-Context Cross-Chunk Detection Examples

### Example 1: SQL Injection (Python)

**Без Symbol-Context (System не видит связку):**
```python
# main.py (ЧАНК 1)
def handle_request(w, r):
    user_id = r.url.query.get("id")  # ← tainted source
    process_query(user_id)            # ← вызов без видимости тела

# System не видит, что processQuery() делает с tainted input → пропускает уязвимость
```

**С Symbol-Context (System видит полный поток):**
```python
# main.py (ЧАНК 1) + CONTEXT из database.py
def handle_request(w, r):
    user_id = r.url.query.get("id")  # ← tainted source
    process_query(user_id)            # ← резолвился в контекст!

# SYMBOL CONTEXT: processQuery() из database.py
def process_query(input):
    query = f"SELECT * FROM users WHERE id='{input}'"  # ← SQL injection!
    cursor.execute(query)                              # ← System видит связку!

# System: "CWE-89: SQL injection - tainted parameter from request reaches .execute() without sanitization"
```

### Example 2: False Positive Prevention (Go)

**Без Symbol-Context (System ошибочно флагает защищённый код):**
```go
// main.go (ЧАНК 1)
func handleRequest(w http.ResponseWriter, r *http.Request) {
    input := r.URL.Query().Get("id")  // ← tainted source
    safeID := sanitizeInput(input)    # ← System не видит, что это защита
    db.Exec(fmt.Sprintf("SELECT * FROM users WHERE id=%d", safeID))
    // ← System может флагировать False Positive
}
```

**С Symbol-Context (System видит защиту):**
```go
// main.go (ЧАНК 1) + CONTEXT из sanitize.go
func handleRequest(w http.ResponseWriter, r *http.Request) {
    input := r.URL.Query().Get("id")  // ← tainted source
    safeID := sanitizeInput(input)    # ← резолвилась в контекст!
    db.Exec(fmt.Sprintf("SELECT * FROM users WHERE id=%d", safeID))
}

// SYMBOL CONTEXT: sanitizeInput() из sanitize.go
func sanitizeInput(input string) int {
    id, _ := strconv.Atoi(input)  // ← Type conversion с error checking!
    if id < 0 || id > 1000 {
        return 0  // ← Boundary validation
    }
    return id
}

// System: "No vulnerability detected - input is properly type-validated and boundary-checked"
```

### Example 3: Multi-File Command Injection (Python)

**С Symbol-Context (System видит длинную цепочку):**
```python
# api.py (ЧАНК 1)
def api_endpoint(w, r):
    cmd = r.form.get("command")     # ← tainted source
    execute_command(cmd)            # → executor.py

# executor.py (ЧАНК 2) - через Symbol Context
def execute_command(user_cmd):
    validated_cmd = validate_command(user_cmd)  # → validator.py → subprocess.run()


# validator.py (ЧАНК 3) - через Symbol Context  
def validate_command(cmd):
    # ... validation logic ...
    return cmd

# System видит полный поток: request → validate_command() → subprocess.run()
# Может детектировать любые слабости в валидации!
```
