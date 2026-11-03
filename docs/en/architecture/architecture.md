# SecureRepo Batch Auditor — Architecture (MVP)

> 🇷🇺 [Russian version](../../ru/architecture/architecture.md)

## 1. Overview

**SecureRepo Batch Auditor** is an enterprise batch security auditing platform for codebases (SaaS, private cloud, on-premise).

- **Air-gapped**: runs without external APIs
- **Batch processing**: repositories with 100k+ lines of code
- **Zero-shot security**: LLM analysis with CWE-ID identification plus corporate policies (Confluence)

---

## 2. Knowledge & Data Layer

### 2.1 Qdrant — Vector DB

| Collection | Purpose | Source | Embedding model |
|------------|---------|--------|-----------------|
| `internal_policies` | Corporate security policies | Confluence API | BAAI/bge-m3 (1024) |
| `code_repo` | AST code chunks | Tree-sitter parser | BAAI/bge-m3 (1024) |

### 2.2 Apache Kafka — Message broker

| Topic | Direction | Description |
|-------|-----------|-------------|
| `repo.parsed` | API → Indexer | Repository URL |
| `audit.tasks` | Indexer → Workers | Audit tasks |
| `audit.status` | Workers → API | Audit statuses |
| `audit.dlq` | — | Reserved; services do not use this topic yet |

Message format, partitions, and consumer groups: [Kafka topics](kafka-topics.md).

### 2.3 PostgreSQL — Relational data

| Table | Purpose |
|-------|---------|
| `users` | Users and RBAC |
| `audits` | Audit statuses (pending → indexing → indexed → auditing → completed) |
| `audit_logs` | Run logs |
| `audit_results` | Per-chunk analysis results (JSONB) |

---

## 3. Application Layer

### 3.1 Confluence Ingestion Service

- **HTML parser**: extract text from Confluence pages
- **Qdrant indexer**: load vectors into the vector DB

Periodic sync of policies from Confluence.

### 3.3 API Service

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/audit/start` | POST | Start repository audit |
| `/audit/{id}/status` | GET | Audit status |
| `/audit/{id}/report` | GET | Audit results |

### 3.4 Indexer Service

- **Git clone**: clone repository
- **Tree-sitter parser**: AST parsing for Python and Go
- **Code chunker**: split by functions/classes
- **Qdrant indexer**: load into vector DB

### 3.5 Embedding Service

Single universal service:

| Model | Dimensions | Purpose |
|-------|------------|---------|
| BAAI/bge-m3 | 1024 | Code + text + multilingual |

**BAAI/bge-m3 benefits:**

- One model for code and text
- 100+ languages (including Russian)
- Trained on code and natural language

### 3.4 Audit Worker (zero-shot LangGraph)

Processing flow for one code unit:

```
[retrieve_internal_rules] ➜ [zero_shot_analyze] ➜ [validate] ➜ PostgreSQL
```

- **retrieve_internal_rules**: fetch exactly 7 corporate policies as zero-shot context
- **zero_shot_analyze**: zero-shot LLM analysis — independent detection of all vulnerabilities with CWE-ID
- **validate**: CWE format validation, grounding, guardrails, persist to PostgreSQL

#### `audit_results` table schema

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

## 4. AI Layer (LLM)

| Model | Purpose | Provider |
|-------|---------|----------|
| LLM (Qwen2.5-Coder-7B-Instruct) | Code analysis | Foundation Models API / Ollama |

---

## 5. Data flows

```
[Confluence API] --> [Ingestion Service] --> [Qdrant: internal_policies]
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

## 6. Service list

| # | Service | Type | Description |
|---|---------|------|-------------|
| 1 | Qdrant | Data | Vector DB |
| 2 | Apache Kafka | Data | Message broker |
| 3 | PostgreSQL | Data | Relational data + audit results |
| 4 | Keycloak | Auth | Authentication and authorization |
| 5 | Langfuse | Observability | LLM request tracing |
| 6 | Internal Rules Ingestion | App | Load corporate policies (JSON / Confluence API) |
| 7 | API Service | App | HTTP endpoints |
| 8 | Indexer Service | App | Parsing + code indexing |
| 9 | Embedding Service | App | Embeddings (BAAI/bge-m3) |
| 10 | Audit Worker | App | Zero-shot audit processing |

---

## 7. MVP vs post-MVP

| Component | MVP | Post-MVP |
|-----------|-----|----------|
| LLM | Foundation Models API | vLLM + Qwen2.5-7B (air-gapped) |
| Policies | JSON via Internal Rules Ingestion | Confluence API |
| Embeddings | BAAI/bge-m3 (1024) | BAAI/bge-m3 |
| Result storage | PostgreSQL (`audit_results`) | PostgreSQL |
| Neo4j (call graphs) | No | Yes |
| Jira integration | No | Yes |
