# SecureRepo documentation

SecureRepo Batch Auditor — enterprise batch security auditing for codebases (SaaS, private cloud, on-premise).

| Language | Index |
|----------|--------|
| **English** | [docs/en/](en/) |
| **Русский** | [docs/ru/](ru/) |

## Quick links (English)

### Deployment
- [Kubernetes deployment guide](en/k8s-deployment-guide.md)
- [Kubernetes secrets example](../k8s/secrets-example/)

### Architecture
- [System architecture](en/architecture/architecture.md)
- [Deployment diagram](en/deployment-diagram.md)
- [Kafka topics](en/architecture/kafka-topics.md)
- [Database schema](en/architecture/database-schema.md)
- [Audit start sequence](en/architecture/audit-start-sequence.md)
- [OpenAPI](../services/api-service/openapi.yaml)

### Requirements & capacity
- [Business & functional requirements](en/business-functional-requirements.md)
- [Resource requirements](en/RESOURCES.md)

### Architecture Decision Records (ADR)
- [000 — BGE-m3 embeddings](en/adr/000-bge-m3-embedding-model.md)
- [001 — Keycloak](en/adr/001-use-keycloak-for-authentication.md)
- [002 — Kafka vs RabbitMQ](en/adr/002-kafka-vs-rabbitmq.md)
- [003 — Qdrant vs ChromaDB](en/adr/003-qdrant-vs-chromadb.md)
- [004 — PostgreSQL](en/adr/004-postgresql-database.md)
- [005 — Qwen Coder 7B](en/adr/005-qwen-coder-7b-instruct.md)

---

**Note:** The project is under active development. Review the latest docs before production use.
