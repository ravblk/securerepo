# API Service

Точка входа в систему. FastAPI-приложение с модульной архитектурой.

## Архитектура

Сервис организован как модуль `api/` с чётким разделением ответственности:
- `config.py` — настройки (через `dataclass(frozen=True)`)
- `models.py` — Pydantic модели для API валидации
- `exceptions.py` — кастомные исключения и обработчики
- `db_models.py` — SQLAlchemy ORM модели
- `database.py` — операции с базой данных
- `qdrant_service.py` — сервис для векторной базы данных
- `kafka_service.py` — сервис для работы с Kafka
- `audit_controller.py` — бизнес-логика аудита
- `main.py` — FastAPI приложение и оркестрация

## Функции

- Запуск аудита репозитория
- Отслеживание статуса аудита
- Получение отчёта
- Инициализация зависимостей (БД, Kafka, Qdrant)

## Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/audit/start` | Запуск аудита репозитория |
| GET | `/audit` | Список аудитов для пользователя |
| GET | `/audit/{id}/status` | Статус аудита |
| GET | `/audit/{id}/report` | Результаты аудита из PostgreSQL |
| GET | `/init` | Инициализация зависимостей |
| GET | `/health` | Проверка здоровья |

## Инициализация зависимостей

При запуске через lifespan контекст автоматически:
- Создаёт таблицы в PostgreSQL (таблица `audits`)
- Создаёт коллекции в Qdrant (`internal_policies`, `general_best_practices`, `code_repo`)
- Создаёт топики в Kafka (`repo.parsed`, `audit.tasks`, `audit.status`)
- Запускает consumer для прослушивания `audit.status`

## Поток данных

1. `POST /audit/start` — создаёт запись в PostgreSQL (status: pending)
2. Отправляет в Kafka топик `repo.parsed`
3. Слушает топик `audit.status` для обновления статуса
4. `GET /audit/{id}/status` — читает из PostgreSQL
5. `GET /audit/{id}/report` — читает из PostgreSQL (таблица `audit_results`)

## Kafka топики

- `repo.parsed` — вход (запуск аудита)
- `audit.status` — слушает (обновление статуса)

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| POSTGRES_URL | URL PostgreSQL |
| KAFKA_BROKER | Kafka broker |
| QDRANT_URL | URL Qdrant |

## Запуск

```bash
 curl -X POST http://localhost:8000/audit/start -H "Content-Type: application/json" -d '{"repo_url": "https://github.com/ravblk/auth", "branch": "master", "lang": "go"}'

  Ответит:                   
  {"audit_id": "uuid", "status": "pending"}
```

## Статус

```bash
  curl http://localhost:8000/audit/{audit_id}/status  
```


## Проверка результата 

```bash
 curl  http://localhost:8000/audit/{audit_id}/report 
```
