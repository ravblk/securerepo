# Database Schema — PostgreSQL & Qdrant

---

## PostgreSQL

### Таблицы

```sql
-- Статусы аудитов (user_id из JWT токена Keycloak)
CREATE TABLE audits (
    id VARCHAR(255) PRIMARY KEY,  -- UUID
    user_id VARCHAR(255) NOT NULL,  -- user_id из JWT токена
    repo_url TEXT NOT NULL,
    branch VARCHAR(255) DEFAULT 'main',
    lang VARCHAR(50) DEFAULT 'python',  -- python, go
    status VARCHAR(50) DEFAULT 'pending',  -- pending → indexing → indexed → auditing → completed → failed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Логи запусков
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,  -- started, indexed, auditing, completed, failed
    details TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (audit_id) REFERENCES audits(id)
);

-- Результаты анализа чанков (JSONB)
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

-- Индексы
CREATE INDEX idx_audits_status ON audits(status);
CREATE INDEX idx_audits_created_at ON audits(created_at);
CREATE INDEX idx_audit_logs_audit_id ON audit_logs(audit_id);
CREATE INDEX idx_audit_results_audit_id ON audit_results(audit_id);
CREATE INDEX idx_audit_results_severity ON audit_results(severity);
```

### ER-диаграмма

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
                                           (зависит от audit_id)           │
```

---

## Qdrant (Vector DB)

### Коллекции

| Коллекция | Назначение | Размерность | Distance |
|-----------|------------|-------------|----------|
| `internal_policies` | Корпоративные политики (Internal Rules) | 1024 | Cosine |
| `general_best_practices` | OWASP/CWE база знаний | 1024 | Cosine |
| `code_repo` | AST-чанки кода репозитория | 1024 | Cosine |

### Структура точек (Points)

#### internal_policies

```json
{
  "id": "uuid",
  "vector": [float, ...],  // 1024 dim
  "payload": {
    "title": "Заголовок политики",
    "text": "Полный текст политики",
    "source": "internal_rules",
    "url": "https://internal-rules.company.com/...",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### general_best_practices

```json
{
  "id": "uuid",
  "vector": [float, ...],  // 1024 dim
  "payload": {
    "title": "CWE-89: SQL Injection",
    "text": "Описание уязвимости и рекомендации",
    "source": "owasp-top-10",  // или "cwe-top-25"
    "url": "https://owasp.org/...",
    "severity": "Critical"
  }
}
```

#### code_repo

```json
{
  "id": "uuid",
  "vector": [float, ...],  // 1024 dim
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

### Индексы

```python
# Текстовый поиск по payload
from qdrant_client.models import TextIndex, TokenizerType

# Для title и text полей
TextIndex(
    type=TextIndexType.TEXT,
    tokenizer=TokenizerType.WORD,
    min_token_len=2,
    max_token_len=20,
    lowercase=True
)
```

---

## Связь PostgreSQL ↔ Qdrant

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
│                              │  general_best_practices               │
│                              │     (vector → text)                  │
└──────────────────────────────┴──────────────────────────────────────┘
```

### Data Flow

1. **Аудит запущен** → `audits` (status: pending)
2. **Индексация кода** → `code_repo` (вектора чанков)
3. **Поиск правил** → `general_best_practices` + `internal_policies`
4. **Результаты** → `audit_results` (JSONB)
5. **Готов отчёт** → `audits` (status: completed)
