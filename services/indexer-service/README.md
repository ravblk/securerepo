# Indexer Service

Парсинг и индексация кодовой базы с модульной архитектурой.

## Архитектура

Сервис организован как модуль `indexer/` с чётким разделением ответственности:
- `config.py` — настройки (через `dataclass(frozen=True)`)
- `models.py` — Pydantic модели (RepoMessage, CodeChunk)
- `parsers.py` — AST-парсинг через Tree-sitter (Python, Go)
- `embedding_service.py` — получение эмбеддингов
- `qdrant_service.py` — взаимодействие с Qdrant
- `kafka_service.py` — Kafka producer/consumer
- `repo_service.py` — git clone и сбор чанков
- `main.py` — FastAPI приложение и оркестрация

## Поток данных

1. Читает из Kafka топика `repo.parsed` (URL репозитория, branch, lang, audit_id, token)
2. Клонирует Git-репозиторий (во `/tmp/repos/<uuid>`)
3. AST-парсинг через Tree-sitter (Python, Go)
4. Разбиение на чанки по функциям/классам
5. Генерация эмбеддингов через embedding-service (BAAI/bge-m3)
6. Заливка в Qdrant (коллекция `code_repo`)
7. Отправляет задачи в Kafka топик `audit.tasks`
8. Отправляет статус в Kafka топик `audit.status`

## Kafka топики

### Вход
- `repo.parsed` — {repo_url, branch, lang, audit_id, token}

### Выход
- `audit.tasks` — {chunk_id, code, file_path, audit_id}
- `audit.status` — {audit_id, status: "indexing" | "indexed" | "failed"}

## Зависимости

| Сервис | Назначение |
|--------|------------|
| Kafka | Топик `repo.parsed` (вход), `audit.tasks` (выход), `audit.status` (выход) |
| Qdrant | Коллекция `code_repo` |
| Embedding Service | Генерация эмбеддингов |

## Эмбеддинги

Использует **BAAI/bge-m3** (порт 8080):

```python
response = requests.post(
    "http://localhost:8080/embed",
    json={"inputs": "def hello(): pass"}
)
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| KAFKA_BROKER | Kafka broker |
| QDRANT_URL | URL Qdrant |
| EMBEDDING_URL | URL Embedding Service (по умолчанию http://embedding:8080) |

## Запуск

```bash
python main.py
```
