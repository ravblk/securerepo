# Internal Rules Ingestion Service

Синхронизация корпоративных политик в Qdrant с модульной архитектурой.

## Архитектура

Сервис организован как модуль `ingestion/` с чётким разделением ответственности:
- `config.py` — настройки (через `dataclass(frozen=True)`)
- `models.py` — Pydantic API модели
- `exceptions.py` — кастомные исключения и обработчики
- `retry_service.py` — сервис для_retry логики с backoff
- `qdrant_service.py` — сервис для Qdrant операций
- `content_service.py` — сервис для получения контента
- `embedding_service.py` — сервис для эмбеддингов
- `sync_controller.py` — бизнес-логика синхронизации
- `main.py` — FastAPI приложение

## Функции

- Параллельная обработка страниц через ThreadPoolExecutor
- Извлечение текста из веб-страниц
- Генерация эмбеддингов через embedding-service
- Заливка в Qdrant (коллекция `internal_policies`)
- Использует **intfloat/multilingual-e5-large** (порт 8080)

## Retry логика

### Экспоненциальный backoff для всех операций

```python
# Qdrant операции
QDRANT_MAX_RETRIES=5          # Максимум попыток
QDRANT_BACKOFF_BASE=1.0       # Базовая задержка
QDRANT_BACKOFF_MAX=30.0        # Максимальная задержка

# HTTP запросы
HTTP_MAX_RETRIES=3             # Максимум попыток
HTTP_BACKOFF_BASE=1.0          # Базовая задержка
HTTP_BACKOFF_MAX=10.0          # Максимальная задержка
```

### Расчёт задержки
```python
delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
# Пытка 1: 1.0s
# Пытка 2: 2.0s
# Пытка 3: 4.0s
# Пытка 4: 8.0s
# Пытка 5: 16.0s
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `PAGES_JSON` | JSON массив страниц для синхронизации | `[]` |
| `MAX_WORKERS` | Количество ThreadPoolExecutor воркеров | `8` |
| `QDRANT_URL` | URL Qdrant | `http://qdrant:6333` |
| `EMBEDDING_URL` | URL Embedding Service | `http://embedding:8080` |

## Формат PAGES_JSON

```json
[
  {
    "id": 1,
    "title": "Go Architectural Plan: Security Guidelines",
    "url": "https://github.com/example/go-sast/blob/master/docs/sast-architecture.md"
  },
  {
    "id": 2,
    "title": "Python Security Best Practices",
    "url": "https://github.com/example/secure-python/blob/main/SECURITY.md"
  }
]
```

Или coma-separated список URL (автоматически генерируются ID и titles):
```json
["https://example.com/security-1.md", "https://example.com/security-2.md"]
```

## Запуск

### Health check
```bash
curl http://localhost:8001/health
```

### Запуск синхронизации
```bash
curl -X POST -H "Content-Type: application/json" -d '{}' http://localhost:8001/sync/start
```

### С кастомными страницами
```bash
curl -X POST -H "Content-Type: application/json" -d '{"pages_json": "PAGES_JSON"}' http://localhost:8001/sync/start
```

### Проверка статуса
```bash
curl http://localhost:8001/sync/{sync_id}/status
```

### История операций
```bash
curl http://localhost:8001/sync/history
```

## Параллельная обработка

Сервис использует `ThreadPoolExecutor` для параллельной обработки страниц:

```python
with ThreadPoolExecutor(max_workers=8) as executor:
    future_to_page = {
        executor.submit(process_page, page): page
        for page in pages
    }

    for future in as_completed(future_to_page):
        # Обработка результатов по мере завершения
        pass
```

### Преимущества

- **Утилизация ресурсов**: Все воркеры заняты
- **Минимальное время ожидания**: Результаты обрабатываются сразу по готовности
- **Отказоустойчивость**: Ошибка одной страницы не блокирует остальные
- **Масштабируемость**: Настраивается через `MAX_WORKERS`

## Retry логика

### Автоматические retry для:

1. **Qdrant операции**
   - Connection errors
   - Timeouts
   - Unexpected response

2. **HTTP запросы**
   - Network errors
   - Temporal failures

3. **Embedding service**
   - Transient errors
   - Service unavailable

### Логирование retry операций

```
[QdrantClient init] attempt 1/5 failed: Connection refused. Retrying in 1.0s...
[QdrantClient init] attempt 2/5 failed: Connection refused. Retrying in 2.0s...
[QdrantClient init] attempt 3/5: Connection refused. Retrying in 4.0s...
[QdrantClient init] connected
```

## Мониторинг

### Health check включает:
```json
{
  "status": "healthy | degraded",
  "qdrant": "reachable | unreachable",
  "embedding": "available | unavailable",
  "qdrant_url": "http://qdrant:6333"
}
```

### Статус синхронизации:
```json
{
  "sync_id": "uuid",
  "status": "running | completed | failed",
  "pages_processed": 5,
  "pages_failed": 1,
  "pages_total": 6,
  "started_at": "2026-09-08T10:00:00",
  "completed_at": "2026-09-08T10:05:00"
}
```

## Архитектурные преимущества

1. **Модульность**: Каждый сервис инкапсулирован
2. **Надёжность**: Экспоненциальный retry для всех операций
3. **Масштабируемость**: Настройка параллелизации через переменные окружения
4. **Поддерживаемость**: Чёткое разделение ответственности
5. **Тестируемость**: Easy dependency injection

## Использование

### Production
```bash
# Конфигурация через переменные окружения
export MAX_WORKERS=16
export PAGES_JSON='[...]'

# Запуск
python main.py
```

### Development
```bash
# Маленький воркер для отладки
export MAX_WORKERS=2

# Простой набор страниц
export PAGES_JSON='["https://example.com/security.md"]'
```

## Замечания по использованию

1. **Периодическое выполнение**: Рекомендуется запускать через Kubernetes CronJob
2. **Rate limiting**: Соблюдайте лимиты embedding service
3. **Мониторинг**: Следите за количеством неудачных страниц (pages_failed)
4. **Health checks**: Интегрируйте health endpoint в мониторинг
