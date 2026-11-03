# Документация SecureRepo

SecureRepo Batch Auditor — корпоративная система массового аудита безопасности кодовых баз.

| Язык | Индекс |
|------|--------|
| **English** | [docs/en/](../en/) |
| **Русский** | [docs/ru/](.) |

## Быстрые ссылки

### Развертывание
- [Руководство по развертыванию в Kubernetes](k8s-deployment-guide.md)
- [Пример секретов Kubernetes](../../k8s/secrets-example/)

### Архитектура
- [Архитектура системы](architecture/architecture.md)
- [Deployment Diagram](deployment-diagram.md)
- [Kafka-топики](architecture/kafka-topics.md)
- [Схема БД](architecture/database-schema.md)
- [Последовательность запуска аудита](architecture/audit-start-sequence.md)
- [OpenAPI](../../services/api-service/openapi.yaml)

### Требования и ресурсы
- [Бизнес-функциональные требования](Biznes-funktsionalnye_trebovania.md)
- [Требования к ресурсам](RESOURCES.md)

### ADR
- [000 — BGE-m3](adr/000-bge-m3-embedding-model.md)
- [001 — Keycloak](adr/001-use-keycloak-for-authentication.md)
- [002 — Kafka vs RabbitMQ](adr/002-kafka-vs-rabbitmq.md)
- [003 — Qdrant vs ChromaDB](adr/003-qdrant-vs-chromadb.md)
- [004 — PostgreSQL](adr/004-postgresql-database.md)
- [005 — Qwen Coder 7B](adr/005-qwen-coder-7b-instruct.md)
