# Kafka-топики

Брокер: `kafka:9092` (переменная `KAFKA_BROKER`). Сообщения — JSON в UTF-8. Продюсеры публикуют с `acks=all`.

Топики создаёт API Service при старте (`KafkaAdminClient`). Если топик уже есть, повторное создание пропускается. У брокера включён `KAFKA_AUTO_CREATE_TOPICS_ENABLE`, срок хранения логов — 168 часов.

| Топик | Партиции | Replication | Ключ | Продюсер | Консьюмер | Consumer group |
|-------|----------|-------------|------|----------|-----------|----------------|
| `repo.parsed` | 5 | 1 | `audit_id` | API Service | Indexer Service | `indexer-group` |
| `audit.tasks` | 5 | 1 | `audit_id` | Indexer Service | Audit Worker | `audit-worker` |
| `audit.status` | 1 | 1 | нет | Indexer Service, Audit Worker | API Service | `api-service-status` |

Одинаковый ключ `audit_id` попадает в одну партицию, поэтому чанки одного аудита обрабатываются по порядку. Разные аудиты могут идти параллельно на разных партициях. `audit.status` состоит из одной партиции: обновления статуса читаются в порядке публикации.

Топик `audit.dlq` в обзоре архитектуры указан как задел. Сервисы его не создают и не пишут в него.

## Поток

```
API Service  --repo.parsed-->  Indexer Service
                                    |
                                    +--audit.status-->  API Service
                                    |
                                    +--audit.tasks-->   Audit Worker
                                                            |
                                                            +--audit.status-->  API Service
```

1. `POST /audit/start` создаёт запись аудита в PostgreSQL (`pending`) и публикует сообщение в `repo.parsed`.
2. Indexer клонирует репозиторий, режет код на чанки и пишет их в Qdrant. Затем публикует `indexed` в `audit.status` и по одному сообщению на чанк в `audit.tasks`.
3. Audit Worker читает задачи, анализирует чанк и публикует `auditing`, затем `completed` или `failed` в `audit.status`.
4. API Service читает `audit.status`, обновляет строку аудита и рассылает то же событие подписчикам SSE (`GET /audit/{audit_id}/live-status`).

## `repo.parsed`

Задание на индексацию репозитория. Indexer читает топик с `auto_offset_reset=latest` и автоматическим коммитом offset: группа без сохранённого offset начинает с конца лога и не подхватывает сообщения, опубликованные до её первого подключения.

```json
{
  "audit_id": "3f1c2a40-7b2e-4d1a-9c55-0a1b2c3d4e5f",
  "user_id": "keycloak-subject",
  "repo_url": "https://git.example.com/org/service.git",
  "branch": "main",
  "lang": "python"
}
```

| Поле | Обязательно | Кто использует |
|------|-------------|----------------|
| `audit_id` | да | ключ партиции и идентификатор аудита |
| `repo_url` | да | клонирование |
| `branch` | да | клонирование |
| `lang` | да | язык по умолчанию для задач аудита |
| `user_id` | да в сообщении API | Indexer не читает |
| `token` | нет | опциональный git-токен; API его сейчас не передаёт |

Ошибки клонирования Indexer не возвращает в этот топик: он публикует `failed` в `audit.status` и прекращает обработку.

## `audit.tasks`

Одна задача — один чанк кода. Indexer отправляет их после статуса `indexed`. Ключ сообщения — `audit_id`.

```json
{
  "chunk_id": "a1b2c3d4",
  "code": "def login(user):\n    ...",
  "file_path": "src/auth.py",
  "audit_id": "3f1c2a40-7b2e-4d1a-9c55-0a1b2c3d4e5f",
  "lang": "python",
  "chunk_index": 0,
  "total_chunks": 12
}
```

| Поле | Смысл |
|------|--------|
| `chunk_id` | идентификатор чанка в Qdrant и в `audit_results` |
| `code` | исходный текст чанка |
| `file_path` | путь файла в репозитории |
| `audit_id` | аудит-владелец |
| `lang` | язык чанка; если в payload Qdrant его нет, берётся `lang` из `repo.parsed` |
| `chunk_index` | номер чанка с нуля |
| `total_chunks` | сколько задач отправлено для этого аудита |

Audit Worker читает группу `audit-worker` с `auto_offset_reset=earliest`, `enable_auto_commit=false` и `max_poll_records=1`. Offset коммитится после успешной обработки. При ошибке сообщение остаётся непрочитанным и будет взято снова.

Сессия консьюмера удлинена под вызов LLM: `session_timeout_ms=300000`, `heartbeat_interval_ms=10000`.

`auditing` публикуется один раз на аудит — перед первым чанком. `completed` публикуется, когда обработан чанк с `chunk_index >= total_chunks - 1`. Если обработка чанка падает, воркер один раз публикует `failed` и пропускает остальные чанки этого `audit_id` в рамках процесса.

Пустой репозиторий (ноль чанков) в `audit.tasks` не попадает: Indexer ограничивается статусом `indexed` с `total_chunks: 0`.

## `audit.status`

Единый канал статусов. API пишет значение `status` в PostgreSQL как есть и пересылает весь JSON в SSE.

Общие поля:

| Поле | Кто пишет | Когда есть |
|------|-----------|------------|
| `audit_id` | оба | всегда |
| `status` | оба | всегда |
| `error` | оба | только при `failed` |
| `total_chunks` | оба | после индексации и во время аудита |
| `progress` | Audit Worker | `auditing` (50) и `completed` (100) |
| `chunk_index` | Audit Worker | вместе с `progress` |

Indexer:

```json
{ "audit_id": "…", "status": "indexed", "total_chunks": 12 }
```

```json
{ "audit_id": "…", "status": "failed", "error": "clone failed" }
```

Audit Worker:

```json
{
  "audit_id": "…",
  "status": "auditing",
  "progress": 50,
  "chunk_index": 0,
  "total_chunks": 12
}
```

```json
{
  "audit_id": "…",
  "status": "completed",
  "progress": 100,
  "chunk_index": 11,
  "total_chunks": 12
}
```

```json
{ "audit_id": "…", "status": "failed", "error": "Error processing task …: …" }
```

Статусы, которые сейчас публикуют сервисы: `indexed`, `auditing`, `completed`, `failed`. Начальный `pending` выставляется в PostgreSQL при создании аудита и в Kafka не отправляется. Значение `all_completed` API считает финальным наравне с `completed` и `failed`, но ни один продюсер его не шлёт.

API читает топик с `auto_offset_reset=earliest` и автоматическим коммитом, поэтому после рестарта группа дочитывает ещё не закоммиченные статусы.
