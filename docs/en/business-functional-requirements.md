# Business and functional requirements: SecureRepo Batch Auditor

> 🇷🇺 [Russian version](../ru/Biznes-funktsionalnye_trebovania.md)

**Project:** Batch security auditing for codebases  
**Audience:** Enterprise (fintech, public sector, healthcare)  
**Document version:** 1.2  
**Status:** Ready for design

---

## 1. Glossary and roles

| Term | Definition |
| :--- | :--- |
| **System (Auditor)** | Platform that parses code, runs RAG search, LLM analysis, and produces vulnerability reports. |
| **Qdrant** | Vector database for semantic (RAG) search. |
| **Kafka** | Message broker for async audit tasks. |
| **vLLM** | Local LLM inference server. |
| **Keycloak** | Identity and access management (OAuth2/OIDC). |
| **Chunk** | Logical code unit (function, class, interface) analyzed separately. |
| **Intent** | LLM-recognized outcome (e.g. vulnerability found, false positive). |

### User roles

| Role | Permissions |
| :--- | :--- |
| **Admin** | User management, policy configuration, start audits, view all reports. |
| **Auditor** | Start audits, view own audit results. |

---

## 2. Business rules (BR)

Hard constraints enforced before or during execution.

- **BR-01 [Audit scope and volume]:** One repository per audit session. Expected average size is **50 chunks**. The system must process the full codebase without forced truncation; throughput and parallelism planning uses the average.
- **BR-02 [Air-gapped]:** No external LLM APIs (OpenAI, Anthropic). All inference runs inside the customer perimeter.
- **BR-03 [Determinism]:** The LLM must not rely on internal world knowledge. Analysis uses RAG context only. Each finding must reference a specific policy clause.
- **BR-04 [Policy context]:** Audits use corporate policies (Internal Rules Ingestion, RAG on `internal_policies`); vulnerability classification uses CWE via zero-shot LLM.
- **BR-05 [Concurrency]:** Up to **5 repositories** audited in parallel (5 concurrent sessions).

---

## 3. Functional requirements (FR)

### 3.1 Integration and audit initiation

| ID | Name | Requirement | Priority |
| :--- | :--- | :--- | :--- |
| FR-1.1 | Webhook trigger | Accept webhook with repository URL and enqueue audit. | high |
| FR-1.2 | Parallel processing | Process up to **5 audits** concurrently; the 6th waits for a Kafka slot. | high |
| FR-1.3 | LLM throttling | Up to 5 concurrent LLM calls (one per active audit). | high |
| FR-1.4 | Volume handling | Handle repositories of any size by queuing excess chunks. Baseline: 5 repos × 50 chunks (250 chunks in flight). | high |

### 3.2 Indexing and parsing

| ID | Name | Requirement | Priority |
| :--- | :--- | :--- | :--- |
| FR-2.1 | Tree-sitter parsing | Chunk code by logical units (functions, classes) via Tree-sitter. | high |
| FR-2.2 | Language support | Python and Go for MVP. | high |
| FR-2.3 | Vectorization | Each chunk embedded with BGE-m3 and stored in Qdrant. | high |

### 3.3 RAG and LLM analysis

| ID | Name | Requirement | Priority |
| :--- | :--- | :--- | :--- |
| FR-3.1 | Internal retriever | Semantic search on `internal_policies`. | high |
| FR-3.2 | LLM analyzer | Zero-shot audit with internal rules; strict JSON output with CWE-ID. | high |
| FR-3.3 | Result format | Each incident: file, lines, description, CWE, MITRE link. | high |

### 3.4 Auth and security

| ID | Name | Requirement | Priority |
| :--- | :--- | :--- | :--- |
| FR-4.1 | Keycloak integration | OAuth2/OIDC; validate JWT on every request. | high |
| FR-4.2 | RBAC | Admin (full access), Auditor (run audits, view results). | high |
| FR-4.3 | TLS | TLS 1.2+ for HTTP between components. | high |

### 3.5 Reporting

| ID | Name | Requirement | Priority |
| :--- | :--- | :--- | :--- |
| FR-5.1 | JSON report | JSON file with vulnerability list when audit completes. | high |

---

## 4. Non-functional requirements (NFR)

1. **Performance:** 5 concurrent repository audits; ~50 chunks per repo average (up to 250 chunks × ~1000 tokens in queue); up to 5 CPS; LLM latency &lt; 5000 ms per chunk.
2. **Availability (SLA):** 99.9% (≤ 43.8 minutes downtime per month).
3. **Security:** TLS 1.2+; air-gapped; local data storage only.
4. **Scalability:** Kafka orchestration; Qdrant up to 1M vectors per collection.
5. **Monitoring:** Audit logs in PostgreSQL; metrics on chunks processed, repo size, errors, duration, active sessions.

---

## 5. Risks and assumptions

1. **Parsing risk:** Tree-sitter may fail on complex files — fallback regex for known patterns.
2. **RAG quality:** Poor embeddings → missed vulnerabilities — MVP cap ~50 policies, test recall.
3. **LLM hallucinations:** Strict prompts; if no relevant rules, return not applicable.
4. **Above-average repo size:** Queue buildup — concurrency cap 5, Kafka buffering, monitoring.
5. **Assumptions:** Repository accessible with or without token; Internal Rules Ingestion for policies in MVP.

---

## 6. Technology stack

| Component | Technology |
| :--- | :--- |
| API | FastAPI |
| Vector DB | Qdrant |
| Message broker | Apache Kafka |
| LLM | vLLM + Qwen2.5-Coder-7B-Instruct-GGUF |
| Embeddings | BGE-m3 (Hugging Face TEI) |
| Orchestration | LangGraph |
| Auth | Keycloak (OAuth2/OIDC) |
| Relational DB | PostgreSQL |
| Parsing | Tree-sitter |

---

## 7. MVP scope

**In scope:**

- API for audit start and policy upload
- Tree-sitter for Python and Go
- Preloaded OWASP Top 10 baseline
- Kafka (task topic, **5 parallel workers**)
- Up to **5 concurrent audits**, ~50 chunks per repo average
- LangGraph (Retriever → Analyzer → Formatter)
- Keycloak (OAuth2, 2 roles) + RBAC
- JSON results report

**Out of scope:**

- Grafana metrics
- Semantic cache for RAG
- KEDA autoscaling
- TLS everywhere (listed as post-MVP in source doc)
- Vault for secrets
- MITRE rules catalog
- Cleanup worker for Postgres/Qdrant
- Neo4j call graphs
- Admin UI
- Extended audit logging
