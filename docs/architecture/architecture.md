# SecureRepo Batch Auditor — Архитектура (MVP)

## 1. Обзор

**SecureRepo Batch Auditor** — корпоративная система массового аудита безопасности кодовых баз (SaaS, Private Cloud / On-Premise).

- **Air-gapped**: система готова к работе без внешних API
- **Batch Processing**: обработка репозиториев 100k+ строк
- **Zero-Shot Security**: LLM анализ с CWE-ID идентификацией + корпоративные политики (Confluence)

---

## 2. Слой данных и знаний (Knowledge & Data Layer)

### 2.1 Qdrant — Векторная БД

| Коллекция | Назначение | Источник | Модель эмбеддингов |
|-----------|------------|----------|-------------------|
| `internal_policies` | Корпоративные политики безопасности | Confluence API | BAAI/bge-m3 (1024) |
| `code_repo` | AST-чанки кода | Tree-sitter парсер | BAAI/bge-m3 (1024) |

### 2.2 Apache Kafka — Брокер сообщений

| Топик | Направление | Описание |
|-------|-------------|----------|
| `repo.parsed` | API → Indexer | URL репозитория |
| `audit.tasks` | Indexer → Workers | Задачи аудита |
| `audit.status` | Workers → API | Статусы аудитов |
| `audit.dlq` | Workers | Dead Letter Queue |

### 2.3 PostgreSQL — Реляционные данные

| Таблица | Назначение |
|---------|------------|
| `users` | Пользователи и RBAC |
| `audits` | Статусы аудитов (pending → indexing → indexed → auditing → completed) |
| `audit_logs` | Логи запусков |
| `audit_results` | Результаты анализа чанков (JSONB) |

---

## 3. Слой приложения (Application Layer)

### 3.1 Confluence Ingestion Service

- **HTML Parser**: извлечение текста из Confluence страниц
- **Qdrant Indexer**: заливка в векторную БД

Периодическая синхронизация политик из Confluence.

### 3.3 API Service

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/audit/start` | POST | Запуск аудита репозитория |
| `/audit/{id}/status` | GET | Статус аудита |
| `/audit/{id}/report` | GET | Результаты аудита |

### 3.4 Indexer Service

- **Git Clone**: клонирование репозитория
- **Tree-sitter Parser**: AST-парсинг Python и Go
- **Code Chunker**: разбиение на чанки по функциям/классам
- **Qdrant Indexer**: заливка в векторную БД

### 3.5 Embedding Service

Один универсальный сервис:

| Модель | Размерность | Назначение |
|--------|-------------|------------|
| BAAI/bge-m3 | 1024 | Код + Текст + Мультиязычный |

**Преимущества BAAI/bge-m3:**
- Одна модель для кода и текста
- Понимает 100+ языков (включая русский)
- Обучен на коде и естественном языке

### 3.4 Audit Worker (Zero-Shot LangGraph)

Поток обработки одной единицы кода:

```
[retrieve_internal_rules] ➜ [zero_shot_analyze] ➜ [validate] ➜ PostgreSQL
```

- **retrieve_internal_rules**: поиск ТОЛЬКО 7 корпоративных политик как zero-shot контекст
- **zero_shot_analyze**: Zero-Shot LLM анализ - независимый поиск ВСЕХ уязвимостей с CWE-ID
- **validate**: валидация CWE формата, grounding и guardrails, сохранение в PostgreSQL

#### Схема таблицы audit_results

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

---

## 4. AI Layer (Внешняя LLM)

| Модель | Назначение | Провайдер |
|--------|------------|-----------|
| LLM (Qwen2.5-Coder-7B-Instruct) | Анализ кода | Foundation Models API |

---

## 5. Потоки данных

```
[Confluence API] --> [Ingestion Service] --> [Qdrant: internal_policies]
[Static DB]      --> [Seed]              --> [Qdrant: general_best_practices]
[Git Repo]       --> [Indexer]           --> [Qdrant: code_repo]
                                                              |
[User API: Start Audit] ------------------------------------>|
                                                              v
                                                       [Kafka: audit.tasks]
                                                              |
                                                     +-------+-------+
                                                     | Audit Workers  |
                                                     +-------+-------+
                                                              |
                                                            [LLM]
                                                              |
                                                       [PostgreSQL: audit_results]
                                                              |
                                                   [API: GET /audit/{id}/report]
                                                              |
                                                            [UI]
```

---

## 6. Список сервисов

| # | Сервис | Тип | Описание |
|---|--------|-----|----------|
| 1 | Qdrant | Data | Векторная БД |
| 2 | Apache Kafka | Data | Брокер сообщений |
| 3 | PostgreSQL | Data | Реляционные данные + результаты аудитов |
| 4 | Keycloak | Auth | Аутентификация и авторизация пользователей |
| 5 | Langfuse | Observability | Мониторинг и трассировка LLM запросов |
| 6 | Internal Rules Ingestion | App | Загрузка корпоративных политик (JSON/Confluence API) |
| 7 | API Service | App | Эндпоинты |
| 8 | Indexer Service | App | Парсинг + индексация кода |
| 9 | Embedding Service | App | Эмбеддинги (BAAI/bge-m3) |
| 10 | Audit Worker | App | Zero-Shot обработка аудита |

---

## 7. MVP vs Post-MVP

| Компонент | MVP | Post-MVP |
|-----------|-----|----------|
| LLM | Foundation Models API | vLLM + Qwen2.5-7B (Air-gapped) |
| Политики | JSON файл через Internal Rules Ingestion | Confluence API |
| Embeddings | BAAI/bge-m3 (1024) | BAAI/bge-m3 |
| Хранение результатов | PostgreSQL (audit_results) | PostgreSQL |
| Neo4j (Call Graphs) | Нет | Да |
| Jira интеграция | Нет | Да |
