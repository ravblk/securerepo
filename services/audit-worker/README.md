# Audit Worker

Обработка задач аудита через LangGraph с модульной архитектурой.

## Архитектура

Сервис организован как модуль `audit/` с чётким разделением ответственности:
- `config.py` — настройки (через `dataclass(frozen=True)`)
- `models.py` — Pydantic модели для валидации и состояния
- `exceptions.py` — кастомные исключения сервисов
- `language_detector.py` — определение языка программирования
- `llm_service.py` — сервис для работы с LLM
- `database_service.py` — сервис для работы с PostgreSQL
- `qdrant_service.py` — сервис для работы с Qdrant
- `embedding_service.py` — сервис для получения эмбеддингов
- `kafka_service.py` — сервис для работы с Kafka
- `prompts.py` — системные промпты для LLM
- `audit_workflow.py` — LangGraph оркестрация (RAG пайплайн)
- `audit_controller.py` — бизнес-логика обработки задач
- `guardrails.py` — система валидации и контроля качества результатов
- `main.py` — FastAPI приложение и запуск Kafka consumer

## Функции

- Чтение из Kafka топика `audit.tasks`
- Семантический поиск правил по эмбеддингу
- Параллельный RAG через LangGraph (fan-out / fan-in)
- LLM анализ кода с найденными правилами
- Сохранение результатов в PostgreSQL
- Отправка статусов в Kafka

## LangGraph Pipeline

```
[compute_embedding] ─▶ [retrieve_general] ─▶ [retrieve_internal] ─▶ [analyze] ─▶ [validate]
```

- **compute_embedding**: Расчёт эмбеддинга кода (1 раз, кэшируется в state)
- **retrieve_general**: Эмбеддинг → Qdrant `general_best_practices` (OWASP, с фильтром по языку)
- **retrieve_internal**: Эмбеддинг → Qdrant `internal_policies` (корпоративные)
- **analyze**: LLM — сравнение кода с правилами
- **validate**: валидация нарушений (проверка наличия уязвимых строк в коде)

## Как работает

1. Получает чанк кода из Kafka
2. Автоматически определяет язык программирования
3. Рассчитывает эмбеддинг кода (BAAI/bge-m3, 1024 dim)
4. Параллельно ищет релевантные правила в Qdrant через LangGraph:
   - Общие правила (OWASP) — с фильтром по языку программирования
   - Корпоративные политики
5. LLM анализирует код с найденными правилами через структурированный промпт
6. **Применяется система Guardrails** для валидации результатов:
   - Проверка JSON-структуры ответов LLM
   - Проверка grounding (наличие уязвимых строк в коде)
   - Обнаружение галлюцинаций (соответствие rule_id)
   - Консистентность severity-уровней
   - Качество объяснений
   - Обнаружение дубликатов
   - Контекстная релевантность
7. Результаты валидации сохраняются в PostgreSQL
8. Статус отправляется в Kafka

**Оптимизация производительности:**
- Проверка подключения LLM выполняется **только один раз** при запуске сервиса
- Нет дополнительных тестов перед каждой задачей, что сокращает количество LLM-вызовов на **50%**
- Приблизительная производительность: ~2-5 сек на один чанк кода

## Kafka топики

### Вход
- `audit.tasks` — {chunk_id, code, file_path, audit_id, chunk_index, total_chunks}

### Выход
- `audit.status` — {audit_id, status: "auditing", progress, chunk_index, total_chunks}
- `audit.status` — {audit_id, status: "completed", progress: 100}
- `audit.status` — {audit_id, status: "failed", error: "..."}

### Надёжность

- Ручной коммит offset после успешной обработки
- При ошибке — offset не коммитится, сообщение будет переобработано
- Отслеживание неудачных аудитов для предотвращения повторных сообщений об ошибках

## Поддерживаемые языки программирования

- Python (.py)
- Go (.go)
- JavaScript (.js)
- TypeScript (.ts)
- Java (.java)
- C/C++ (.c, .cpp)
- C# (.cs)
- Ruby (.rb)
- PHP (.php)
- Swift (.swift)
- Kotlin (.kt)
- Rust (.rs)
- Scala (.scala)
- Dart (.dart)

Для неизвестных расширений используется Python по умолчанию.

## PostgreSQL

Таблица `audit_results`:

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

CREATE INDEX idx_audit_results_audit_id ON audit_results(audit_id);
```

Структура JSON в поле `findings`:
```json
[
  {
    "rule_id": "ID правила",
    "rule_url": "URL на правило (внешний источник, например, CWE или OWASP)",
    "repository_url": "Прямая ссылка на файл правила в репозитории",
    "severity": "Critical | High | Medium | Low",
    "explanation": "Объяснение нарушения",
    "vulnerable_line": "Уязвимая строка кода"
  }
]
```

## Зависимости

| Сервис | Назначение |
|--------|------------|
| Kafka | Топик `audit.tasks` (вход), `audit.status` (выход) |
| Qdrant | Коллекции `internal_policies`, `general_best_practices` |
| Embedding Service | Эмбеддинги (BAAI/bge-m3, 1024 dim) |
| PostgreSQL | Таблица `audit_results` |
| Foundation Models API | LLM для анализа кода |

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| KAFKA_BROKER | Kafka broker | kafka:9092 |
| QDRANT_URL | URL Qdrant | http://qdrant:6333 |
| EMBEDDING_URL | URL Embedding Service | http://embedding:8080/embed |
| POSTGRES_URL | URL PostgreSQL |postgresql://securerepo:securerepo_pass@postgres:5432/securerepo |
| OAPI_MODELS_URL | URL Foundation Models API | https://foundation-models.api.cloud.ru/v1 |
| OAPI_API_KEY | API ключ | none |
| LLM_MODEL | Модель LLM | Qwen/Qwen2.5-Coder-7B-Instruct |

## Запуск

```bash
# С локальными переменными окружения
python main.py

# Или с переменными окружения
export OAPI_MODELS_URL="https://your-model-api.com/v1"
export OAPI_API_KEY="your-api-key"
python main.py
```

## Масштабирование

Сервис масштабируется горизонтально:
- Нескольких воркеров читают из одной группы потребителей Kafka
- Каждый воркер обрабатывает свою порцию сообщений
- Координация через Kafka consumer group

## Мониторинг

### Health check
```bash
curl http://localhost:8003/health
```

### Service info
```bash
curl http://localhost:8003/
```

## Получение отчёта

Через API: `GET /audit/{audit_id}/report` (в api-service)

Или напрямую из PostgreSQL:
```sql
SELECT jsonb_agg(row_to_json(r))
FROM (
  SELECT chunk_id, file_path, findings, severity
  FROM audit_results
  WHERE audit_id = '<audit-id>'
) r;
```

## Отладка

Логи содержат информацию о каждом этапе обработки:
- Получение задачи из Kafka
- Определение языка программирования
- Этапы LangGraph workflow
- Результаты поиска в Qdrant
- Ответ LLM и найденные нарушения
- Результаты валидации
- Сохранение в БД
- Отправка статусов

## Архитектурные преимущества

1. **Модульность**: Каждый сервис инкапсулирован и может быть заменён
2. **Тестируемость**: Компоненты легко мокаются для unit тестов
3. **Поддерживаемость**: Чёткое разделение ответственности
4. **Масштабируемость**: Горизонтальное масштабирование через Kafka
5. **Надёжность**: Собственная обработка ошибок и retry логика
6. **Современность**: Использование LangGraph для оркестрации ML пайплайнов
