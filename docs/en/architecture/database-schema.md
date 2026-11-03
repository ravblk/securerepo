# Database schema — PostgreSQL & Qdrant

> 🇷🇺 [Russian version](../../ru/architecture/database-schema.md)

---

## PostgreSQL

### Tables

```sql
-- Audit records (user_id from Keycloak JWT)
CREATE TABLE audits (
    id VARCHAR(255) PRIMARY KEY,  -- UUID
    user_id VARCHAR(255) NOT NULL,  -- from JWT
    repo_url TEXT NOT NULL,
    branch VARCHAR(255) DEFAULT 'main',
    lang VARCHAR(50) DEFAULT 'python',  -- python, go
    status VARCHAR(50) DEFAULT 'pending',  -- pending → indexing → indexed → auditing → completed → failed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Run logs
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,  -- started, indexed, auditing, completed, failed
    details TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (audit_id) REFERENCES audits(id)
);

-- Per-chunk analysis results (JSONB)
CREATE TABLE audit_results (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    findings JSONB NOT NULL,  -- {"violations": [...]}
    severity VARCHAR(50),  -- Critical, High, Medium, Low
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (audit_id) REFERENCES audits(id)
);

-- Indexes
CREATE INDEX idx_audits_status ON audits(status);
CREATE INDEX idx_audits_created_at ON audits(created_at);
CREATE INDEX idx_audit_logs_audit_id ON audit_logs(audit_id);
CREATE INDEX idx_audit_results_audit_id ON audit_results(audit_id);
CREATE INDEX idx_audit_results_severity ON audit_results(severity);
```

### ER diagram

```
┌─────────────────┐       ┌─────────────────┐
│                 │       │     audits      │
├─────────────────┤       ├─────────────────┤
│                 │       │ id (PK)         │
│    (users in    │       │ user_id         │
│    Keycloak)    │       │ repo_url        │
│                 │       │ branch          │
│                 │       │ lang            │
│                 │       │ status          │
└─────────────────┘       │ created_at      │
                          │ updated_at      │
                          └────────┬────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│    audit_logs       │   │   audit_results    │   │                     │
├─────────────────────┤   ├─────────────────────┤   │                     │
│ id (PK)             │   │ id (PK)            │   │                     │
│ audit_id (FK) ──────┼──▶│ audit_id (FK) ─────┼──▶│                     │
│ action              │   │ chunk_id           │   │                     │
│ details             │   │ file_path          │   │                     │
│ created_at          │   │ findings (JSONB)  │   │                     │
└─────────────────────┘   │ severity           │   │                     │
                          │ created_at         │   │                     │
                          └─────────────────────┘   │                     │
                                                     │                     │
                                                     ▼                     │
                                           (linked by audit_id)            │
```

---

## Qdrant (vector DB)

### Collections

| Collection | Purpose | Dimensions | Distance |
|------------|---------|------------|----------|
| `internal_policies` | Corporate security policies (internal rules) | 1024 | Cosine |
| `code_repo` | Repository AST chunks | 1024 | Cosine |

### Point structure

#### internal_policies

```json
{
  "id": "uuid",
  "vector": [float, ...],
  "payload": {
    "title": "Policy title",
    "text": "Full policy text",
    "source": "internal_rules",
    "url": "https://internal-rules.company.com/...",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### code_repo

```json
{
  "id": "uuid",
  "vector": [float, ...],
  "payload": {
    "chunk_id": "unique-chunk-id",
    "file_path": "src/auth.py",
    "function_name": "validate_password",
    "lang": "python",
    "code": "def validate_password(pwd): ...",
    "audit_id": "audit-uuid"
  }
}
```

### Indexes

```python
# Text search on payload
from qdrant_client.models import TextIndex, TokenizerType

TextIndex(
    type=TextIndexType.TEXT,
    tokenizer=TokenizerType.WORD,
    min_token_len=2,
    max_token_len=20,
    lowercase=True
)
```

---

## PostgreSQL ↔ Qdrant

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SecureRepo                                  │
├──────────────────────────────┬──────────────────────────────────────┤
│      PostgreSQL              │           Qdrant                      │
│                              │                                       │
│  audits ────────────────────┼──▶ code_repo                          │
│  │                          │     (chunk_id → vector)              │
│  │                          │                                       │
│  ▼                          │  internal_policies                    │
│  audit_results              │     (vector → text)                  │
│  (findings JSONB)           │                                       │
└──────────────────────────────┴──────────────────────────────────────┘
```

### Data flow

1. **Audit started** → `audits` (status: pending)
2. **Code indexed** → `code_repo` (chunk vectors)
3. **Zero-shot analysis** → only `internal_policies` (7 rules as context)
4. **Results** → `audit_results` (JSONB with CWE-ID)
5. **Report ready** → `audits` (status: completed)
