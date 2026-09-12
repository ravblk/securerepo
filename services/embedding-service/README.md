# Embedding Service

Генерация эмбеддингов для RAG с использованием BAAI/bge-m3.

## Архитектура

Один универсальный сервис:

| Модель | Размерность | Назначение |
|--------|-------------|------------|
| `BAAI/bge-m3` | 1024 | Код + Текст + Мультиязычный |

**Преимущества:**
- Одна модель для кода и текста
- Понимает более 100 языков (включая русский)
- Обучен на коде и естественном языке

## API

### POST /embed

```bash
curl -X POST http://localhost:8080/embed \
  -H "Content-Type: application/json" \
  -d '{"inputs": "текст для эмбеддинга"}'
```

Ответ:
```json
{
  "embeddings": [[0.1, 0.2, ...]]
}
```

Для нескольких текстов:
```bash
curl -X POST http://localhost:8080/embed \
  -H "Content-Type: application/json" \
  -d '{"inputs": ["текст 1", "текст 2"]}'
```

### GET /health

Проверка здоровья сервиса.

### GET /

Информация о сервисе.

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|---------------|
| MODEL_NAME | Название модели | BAAI/bge-m3 |

## Запуск

```bash
MODEL_NAME=BAAI/bge-m3 uvicorn main:app --port 8080 --host 0.0.0.0
```

## Docker

```yaml
embedding:
  build: ./embedding-service
  ports:
    - "8080:8080"
  environment:
    - MODEL_NAME=BAAI/bge-m3
```
