# SecureRepo

SecureRepo Batch Auditor — enterprise batch security auditing for codebases (SaaS, private cloud, on-premise).

Microservices stack:

- **PostgreSQL** — relational metadata
- **Qdrant** — vector store for embeddings
- **Kafka** — async task processing
- **Keycloak** — authentication and authorization
- **Langfuse** — LLM observability

Services: API Service, Frontend Service, Indexer Service, Embedding Service, Internal Rules Ingestion, Audit Worker.

## Documentation

Full documentation hub: **[docs/README.md](docs/README.md)**

| Language | Path |
|----------|------|
| English | [docs/en/](docs/en/) |
| Русский | [docs/ru/](docs/ru/) |

### Deployment
- [Kubernetes deployment guide (EN)](docs/en/k8s-deployment-guide.md)
- [Kubernetes deployment guide (RU)](docs/ru/k8s-deployment-guide.md)
- [Kubernetes secrets example](k8s/secrets-example/)

### Architecture
- [System architecture (EN)](docs/en/architecture/architecture.md)
- [Deployment diagram (EN)](docs/en/deployment-diagram.md)
- [API (OpenAPI)](services/api-service/openapi.yaml)

### Operations
- [Resource requirements (EN)](docs/en/RESOURCES.md)
- [Vulnerability detection tests](tests/test_vulnerability_detection.py)

**Warning:** The project is under active development. Review the latest documentation before production use.
