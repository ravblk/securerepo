# ADR: Выбор PostgreSQL для хранения результатов аудита

## Status
Accepted

## Context

SecureRepo Batch Auditor сохраняет результаты аудита. Нужна надёжная реляционная БД.

*PostgreSQL*
- Тип: Реляционная СУБД
- License: PostgreSQL License (MIT-подобная, permissive open source)
- Language: C
- ACID: Полная поддержка
- JSONB: Нативная поддержка (удобно для findings)
- Replication: Streaming replication, logical replication
- Partitioning: Нативная поддержка табличных партиций
- Sharding: Citus extension (опционально)
- Интеграции: psycopg2, SQLAlchemy, Prisma
- Cloud: Yandex Cloud, SberCloud, VK Cloud, AWS RDS, GCP Cloud SQL
- Популярность в России: #1 среди реляционных БД

*MySQL*
- Тип: Реляционная СУБД
- License: GPLv2
- JSON: Ограниченная поддержка (JSON only, не JSONB)
- Replication: Binlog-based
- Partitioning: Ограниченная поддержка

*ClickHouse*
- Тип: Колонночная СУБД (OLAP)
- License: Apache 2.0 (open source)
- Analytical: Отлично для аналитики
- Transactions: Ограниченная поддержка (MergeTree)

## Decision

Выбран **PostgreSQL**.

Обоснование:
1. **JSONB**: нативная поддержка, индексация, компактное хранение findings
2. **ACID**: гарантия целостности результатов аудита
3. **Экспертиза**: #1 в России, легко найти специалистов
4. **Облака**: полная поддержка во всех российских облаках
5. **Open Source**: PostgreSQL License, не требует лицензирования
6. **Масштабирование**: репликация, партиционирование, Citus
7. **Экосистема**: psycopg2, pgvector для векторного поиска в будущем

## Consequences

**Pros:**
- Надёжность: ACID-транзакции, WAL-логирование
- Удобство: JSONB для гибкой структуры findings
- Масштабирование: streaming replication, partition by audit_id
- Экспертиза: огромное количество специалистов в России
- Облака: Yandex Cloud, SberCloud, VK Cloud, AWS, GCP
- Open Source: бесплатная, не требует лицензий

**Cons:**
- Дополнительная БД в стеке
- Требует настройки резервного копирования
- Версионирование схемы требует миграций

**Mitigations:**
- Один контейнер в docker-compose для dev
- Мониторинг через Prometheus + pg_exporter
- Alembic для миграций схемы

## Почему не MySQL

| Фактор | PostgreSQL | MySQL |
|--------|------------|-------|
| JSONB | + | Ограниченно |
| ACID | Полная | Полная |
| Partitioning | Нативное | Ограниченное |
| Экспертиза в России | #1 | Высокая |
| Open Source | PostgreSQL License | GPLv2 |

## Почему не ClickHouse

| Фактор | PostgreSQL | ClickHouse |
|--------|------------|------------|
| OLTP | + | - |
| JSONB | + | + |
| Транзакции | Полные | Ограниченные |
| Экспертиза в России | #1 | Растущая |
| Сложность | Средняя | Высокая |

## Альтернативы (рассмотрены)

| БД | Причина отклонения |
|----|-------------------|
| SQLite | Нет репликации, не для production |
| CockroachDB | Избыточно для текущих задач |
| YugabyteDB | Требует больших ресурсов |
