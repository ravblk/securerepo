# Analyzer — механизм логического вывода

Это сердце системы — **механизм логического вывода (Inference Engine)**.

---

## Архитектура: Semantic Code Search

Вместо генерации запросов через LLM, используем **эмбеддинг кода** для семантического поиска правил безопасности. Это:
- Быстрее (один вызов вместо двух)
- Точнее (семантический поиск по смыслу кода)

---

## Pipeline (оптимизированный)

```
[compute_embedding] ─▶ [retrieve_general] ─▶ [retrieve_internal] ─▶ [analyze] ─▶ [validate]
```

**Шаги:**
1. Расчёт эмбеддинга кода (один раз, кэшируется в state)
2. Эмбеддинг → Qdrant `general_best_practices` (OWASP, с фильтром по языку)
3. Эмбеддинг → Qdrant `internal_policies` (корпоративные)
4. LLM анализирует код с найденными правилами
5. Валидация и сохранение в PostgreSQL

---

## Шаг 1: Семантический поиск (Semantic RAG)

Эмбеддинг кода (model: `BAAI/bge-m3`, 1024 dim) рассчитывается **один раз** и кэшируется в state:

```python
def compute_embedding(state: AuditState) -> dict:
    code = state["code"]
    embedding = get_embedding(code[:5000])
    return {"code_embedding": embedding or []}
```

Поиск с фильтром по языку программирования:

```python
# Семантический поиск в Qdrant
results = client.search(
    collection_name="general_best_practices",
    query_vector=embedding,
    limit=3,
    query_filter={
        "must": [
            {"key": "source", "match": {"value": "owasp-top-10"}},
            {"key": "lang", "match": {"value": lang}}  # Фильтр по языку
        ]
    }
)
```

**Почему это лучше:**
- Код семантически близкий к SQL-injection правилам → найдет даже если нет явных ключевых слов
- Один вызов эмбеддинга вместо двух (до/после LLM)
- Фильтр по языку исключает нерелевантные правила

---

## Шаг 2: Последовательный RAG

Эмбеддинг кэшируется в state, затем используется для обоих поисков:

```python
# LangGraph (последовательный пайплайн)
workflow.set_entry_point("compute_embedding")
workflow.add_edge("compute_embedding", "retrieve_general")
workflow.add_edge("retrieve_general", "retrieve_internal")
workflow.add_edge("retrieve_internal", "analyze")
```

Это надёжнее для MVP: эмбеддинг рассчитывается 1 раз, затем переиспользуется.

---

## Шаг 3: LLM Анализ кода

LLM получает код + найденные правила через SystemMessage:

```python
from langchain_core.messages import SystemMessage

SYSTEM_PROMPT = """Ты — строгий аудитор безопасности.

### ПРАВИЛА БЕЗОПАСНОСТИ:
{rules}

### КОД ДЛЯ АУДИТА:
Язык: {lang} | Файл: {file_path}
{code}

ФОРМАТ ОТВЕТА (JSON):
{{
  "violations": [
    {{
      "rule_id": "CWE-XX",
      "rule_url": "URL на правило (внешний источник)",
      "repository_url": "Прямая ссылка на файл правила в репозитории",
      "severity": "Critical | High | Medium | Low",
      "explanation": "Почему код нарушает правило",
      "vulnerable_line": "Строка кода"
    }}
  ]
}}
Если нарушений нет: {{"violations": []}}"""

# Явная передача SystemMessage
response = llm.invoke([SystemMessage(content=system_prompt)])
```

---

## Шаг 4: Валидация

1. **Grounding Check:** Проверяем, что `vulnerable_line` содержится в коде
2. **Определение severity:** По максимальной критичности

---

## Шаг 5: Надёжность Kafka

Ручной коммит offset после успешной записи в PostgreSQL:

```python
# consume_tasks()
consumer = KafkaConsumer(
    AUDIT_TASKS_TOPIC,
    enable_auto_commit=False  # Ручной коммит
)

# Обработка
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
