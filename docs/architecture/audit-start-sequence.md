sequenceDiagram
    participant User as User
    participant API as API Service (FastAPI)
    participant SQL as PostgreSQL
    participant Kafka as Apache Kafka
    participant Indexer as Indexer Service
    participant Qdrant as Qdrant (Vector DB)
    participant Embed as Embedding Service
    participant Worker as Audit Worker
    participant LLM as LLM (Qwen-Coder-Next)

    User->>API: POST /audit/start<br/>(repo_url, branch, lang)
    API->>SQL: Создать запись аудита<br/>(status=pending)
    SQL-->>API: Audit created
    API->>Kafka: Отправить в repo.parsed<br/>(audit_id, repo_url, branch, lang)
    API-->>User: {audit_id, status: "pending"}

    par Асинхронная обработка
        Kafka->>Indexer: Получить сообщение<br/>(repo.parsed)
        Indexer->>Indexer: Клонировать репозиторий
        Indexer->>Indexer: Парсить код (tree-sitter)
        Indexer->>Embed: Эмбеддинг для каждого чанка
        Embed-->>Indexer: Векторы (1024 dim)
        Indexer->>Qdrant: Сохранить чанки<br/>(collection: code_repo)
        Qdrant-->>Indexer: Indexed
        Indexer->>Kafka: Отправить статус "indexed"<br/>(audit.status)
        Indexer->>Kafka: Отправить задачи в audit.tasks<br/>(по одной на чанк)

        par Параллельная обработка чанков
            loop Для каждой задачи из audit.tasks
                Kafka->>Worker: Получить задачу<br/>(chunk_id, code, file_path, audit_id)
                Worker->>Qdrant: Поиск общих правил<br/>(general_best_practices, фильтр по lang)
                Qdrant-->>Worker: OWASP правила
                Worker->>Qdrant: Поиск внутренних правил<br/>(internal_policies)
                Qdrant-->>Worker: Корпоративные политики
                Worker->>LLM: Анализ кода<br/>(код + правила)
                LLM-->>Worker: Нарушения (violations)
                Worker->>SQL: Сохранить результат<br/>(audit_results)
                Worker->>Kafka: Отправить статус "completed"<br/>(audit.status)
            end
        end
    end

    API->>Kafka: Слушать статус (audit.status)
    Kafka-->>API: Обновления статуса
    API->>SQL: Обновить статус аудита<br/>(pending → indexing → indexed → auditing → completed)

    Note over User,API: Polling: GET /audit/{audit_id}/status
    User->>API: GET /audit/{audit_id}/status
    API-->>User: {audit_id, status: "completed"}

    Note over User,API: Получение отчёта
    User->>API: GET /audit/{audit_id}/report
    API->>SQL: Запросить результаты<br/>(SELECT * FROM audit_results)
    SQL-->>API: Список findings
    API-->>User: {audit_id, results: [...]}
