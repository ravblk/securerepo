# ADR: Выбор PostgreSQL для хранения результатов аудита

## Status
Accepted

## Context

SecureRepo Batch Auditor сохраняет результаты аудита. Нужна надёжная БД для хранения результатов (findings) с гибкой JSON-структурой.

*PostgreSQL*
- Тип: Реляционная СУБД (объектно-реляционная)
- License: PostgreSQL License (MIT-подобная, permissive open source)
- Language: C
- ACID: Полная поддержка
- JSONB: Нативная поддержка (удобно для находок findвings)
- Replication: Streaming replication, logical replication
- Partitioning: Нативная поддержка табличных партиций
- Sharding: Citus extension (опционально)
- Интеграции: psycopg2, SQLAlchemy, Prisma
- Cloud: Yandex Cloud, SberCloud, VK Cloud, AWS RDS, GCP Cloud SQL
- Популярность в России: #1 среди реляционных БД

*MongoDB*
- Тип: Документо-ориентированная СУБД (NoSQL)
- License: SSPL (Server Side Public License)
- Data Model: BSON (бинарный JSON)
- ACID: Многодокументные транзакции (с версии 4.0)
- Scaling: Встроенный sharding, replica sets
- Популярность: Высокая для NoSQL

*MySQL*
- Тип: Реляционная СУБД
- License: GPLv2
- JSON: Ограниченная поддержка (JSON only, не JSONB)
- Replication: Binlog-based

*ClickHouse*
- Тип: Колонночная СУБД (OLAP)
- License: Apache 2.0 (open source)
- Analytical: Отлично для аналитики
- Transactions: Ограниченная поддержка

## Decision

Выбран **PostgreSQL**.

Обоснование:
1. **JSONB**: нативная поддержка, индексация, компактное хранение findings. Покрывает потребности NoSQL без необходимости ввода новой БД.
2. **ACID**: гарантия целостности результатов аудита и ручного коммита Kafka offset.
3. **Унификация стека (Keycloak)**: Инфраструктура проекта использует Keycloak для авторизации (SSO). Keycloak нативно требует и работает на PostgreSQL. Выбор PostgreSQL позволит в будущем использовать совместный кластер БД.
4. **Облака**: полная поддержка во всех российских облаках.
5. **Open Source**: PostgreSQL License, не требует лицензирования.

## Consequences

**Pros:**
- Надёжность: ACID-транзакции, WAL-логирование
- Удобство: JSONB для гибкой структуры findings
- Масштабирование: streaming replication, partition by audit_id
- Экспертиза: огромное количество специалистов в России
- Унификация: возможность использовать одну БД для приложения и Keycloak
- Экосистема: psycopg2, pgvector для векторного поиска в будущем

**Cons:**
- **Возможная совместная БД с Keycloak**: так как Keycloak работает на PostgreSQL, есть риск объединения БД в один инстанс. Это потребует строгой настройки изоляции ресурсов (connection limits, pooler) для избежания влияния (noisy neighbor problem) аудиторского пайплайна на работу авторизации.
- Требует настройки резервного копирования
- Версионирование схемы требует миграций

**Mitigations:**
- Разделение баз данных (audit_db и keycloak_db) в рамках одного PostgreSQL-кластера (изолированные роли и схемы).
- Использование PgBouncer для пула соединений и ограничения нагрузки.
- Мониторинг через Prometheus + pg_exporter
- Alembic для миграций схемы

## Почему не MongoDB

| Фактор | PostgreSQL | MongoDB |
|--------|------------|---------|
| JSON хранение | JSONB (с индексами) | BSON (нативный NoSQL) |
| Интеграция с Keycloak| Идеальная (Keycloak работает на PG)| Требует отдельной БД для Keycloak |
| ACID | Полные, зрелые | Многодокументные транзакции (тяжелее) |
| Экспертиза в России | #1 | Высокая, но реляционные преобладают |
| Унификация стека | 1 БД для всего | 2 разные БД в стеке (Mongo + PG для Keycloak)|

## Почему не MySQL / ClickHouse

| Фактор | PostgreSQL | MySQL | ClickHouse |
|--------|------------|-------|------------|
| JSONB | + | Ограниченно | + |
| ACID / Транзакции| Полная | Полная | Ограниченные |
| Keycloak Support | Нативный | Нативный | Нет |
| OLTP | + | + | - |
| Сложность | Средняя | Средняя | Высокая |

## Альтернативы (рассмотрены)

| БД | Причина отклонения |
|----|-------------------|
| MongoDB | Отлично подходит для JSON, но Keycloak требует PostgreSQL. Выбор Mongo привел бы к необходимости поддерживать 2 разные СУБД в проекте. |
| SQLite | Нет репликации, не для production |
| CockroachDB | Избыточно для текущих задач |
| ClickHouse | OLAP, нет OLTP, не подходит для реляционных связей и Keycloak |