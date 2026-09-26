# Analyzer — механизм логического вывода

Это сердце системы — **механизм логического вывода (Inference Engine)** для Zero-Shot анализа безопасности кода.

---

## Архитектура: Zero-Shot Security Analysis

LLM выполняет независимый анализ безопасности кода, используя свои знания о CWE-ID и уязвимостях, с минимальным контекстом.

**Ключевое отличие:** LLM не зависит от внешних наборов правил и самостоятельно идентифицирует уязвимости.

---

## Pipeline (Zero-Shot оптимизирован)

```
[compute_embedding] ─▶ [retrieve_internal_rules] ─▶ [zero_shot_analyze] ─▶ [validate]
```

**Шаги:**
1. **compute_embedding**: Расчёт эмбеддинга кода (один раз, кэшируется в state)
2. **retrieve_internal_rules**: Эмбеддинг → Qdrant `internal_policies` (ТОЛЬКО 7 правил как контекст)
3. **zero_shot_analyze**: Zero-Shot LLM анализ — самостоятельный поиск ВСЕХ уязвимостей с CWE-ID
4. **validate**: Валидация CWE формата + grounding + guardrails
5. **хранение**: Сохранение результатов в PostgreSQL

---

## Шаг 1: Семантический поиск (Semantic RAG)

Эмбеддинг кода (model: `BAAI/bge-m3`, 1024 dim) рассчитывается **один раз** и кэшируется в state:

```python
def compute_embedding(state: AuditState) -> dict:
    code = state["code"]
    embedding = get_embedding(code[:5000])
    return {"code_embedding": embedding or []}
```

Поиск ТОЛЬКО 7 наиболее релевантных внутренних правил:

```python
# Семантический поиск ТОЛЬКО в internal policies
results = client.search(
    collection_name="internal_policies",
    query_vector=embedding,
    limit=7  # ТОЛЬКО 7 правил для zero-shot контекста
)
```

**Почему именно 7:**
- Достаточно контекста для улучшения качества анализа
- Перегрузка не требует больших вычислений
- Оптимальный баланс между контекстом и скоростью

---

## Шаг 2: Zero-Shot LLM Анализ кода

LLM получает код + ТОЛЬКО 7 внутренних правил как минимальный контекст через Zero-Shot промпт:

```python
from langchain_core.messages import SystemMessage

SYSTEM_PROMPT = """Ты — экспертная система Zero-Shot анализа безопасности кода.
Твоя задача: самостоятельно найти ВСЕ уязвимости безопасности в предоставленном коде,
определить их CWE-ID и точные строки.

## ВНУТРЕННИЕ ПРАВИЛА (ДОПОЛНЕНИЕ, ТОЛЬКО 7 ШТ):
{rules}

## КОД ДЛЯ АНАЛИЗА:
Язык: {lang} | Файл: {file_path}
{code}

## ТРЕБОВАНИЯ:
- Найди **ВСЕ** уязвимости, даже если их много
- Точные CWE ID (формат: CWE-XXX)
- Точные строки кода (обязательно должны существовать)
- Если уязвимостей нет - верни пустой массив

ФОРМАТ ОТВЕТА (JSON):
{{
  "violations": [
    {{
      "rule_id": "CWE-XXX",
      "rule_url": "https://cwe.mitre.org/data/definitions/XXX.html",
      "severity": "Critical | High | Medium | Low",
      "explanation": "Детальное описание уязвимости",
      "vulnerable_line": "Точная строка кода"
    }}
  ]
}}"""

# Zero-Shot анализ с минимальным контекстом
response = llm.invoke([SystemMessage(content=system_prompt)])
```

**Key Features:**
- **Independent reasoning**: LLM использует свои знания о CWE-ID и уязвимостях
- **7 rules augmentation**: Внутренние правила улучшают качество, но не ограничивают
- **Comprehensive coverage**: Сканирование ВСЕХ категорий уязвимостей

---

## Шаг 3: Валидация Zero-Shot результатов

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

## Шаг 4: Надёжность Kafka

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

PostgreSQL таблица `audit_results`:

```sql
CREATE TABLE audit_results (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    findings JSONB NOT NULL,
    severity VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
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

## Zero-Shot Преимущества

### По сравнению с традиционным RAG:
- **Broader coverage**: LLM находит уязвимости вне предоставленных правил
- **CWE accuracy**: Точные идентификаторы из MITRE CWE standard
- **Adaptable**: Автоматически адаптируется к новым типам уязвимостей
- **Context efficient**: 7 правил вместо сотен для покрытия

### Ограничения:
- **Hallucination risk**: Требуется строгий guardrails контроль
- **CWE awareness**: LLM должен быть обучен на CWE стандарт
- **Grounding verification**: Необходима проверка уязвимых строк

---

## Архитектурные решения

### Why 7 Internal Rules?
- **Context coverage**: Достаточно для улучшения качества без перегрузки
- **Performance**: Баланс между глубиной и скоростью
- **Focus**: Специфические корпоративные политики безопасности

### Zero-Shot Primary, Rules Secondary
- **LLM leads**: Независимый анализ всех категорий уязвимостей
- **Rules augment**: Улучшают точность специфических контекстов
- **Validation ensures**: CWE format и grounding гарантируют качество

### Guardrails Essential
- **CWE validation**: Формат CWE-\d+ pattern
- **Grounding check**: Строки должны существовать в коде
- **Quality control**: JSON структура, severity consistency
