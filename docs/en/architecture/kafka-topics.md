# Kafka topics

> 🇷🇺 [Russian version](../../ru/architecture/kafka-topics.md)

Broker: `kafka:9092` (`KAFKA_BROKER`). Messages are JSON in UTF-8. Producers publish with `acks=all`.

Topics are created by API Service on startup (`KafkaAdminClient`). If a topic already exists, creation is skipped. The broker has `KAFKA_AUTO_CREATE_TOPICS_ENABLE`; log retention is 168 hours.

| Topic | Partitions | Replication | Key | Producer | Consumer | Consumer group |
|-------|------------|-------------|-----|----------|----------|----------------|
| `repo.parsed` | 5 | 1 | `audit_id` | API Service | Indexer Service | `indexer-group` |
| `audit.tasks` | 5 | 1 | `audit_id` | Indexer Service | Audit Worker | `audit-worker` |
| `audit.status` | 1 | 1 | none | Indexer Service, Audit Worker | API Service | `api-service-status` |

The same `audit_id` key lands in one partition, so chunks for one audit are processed in order. Different audits can run in parallel on different partitions. `audit.status` has a single partition: status updates are read in publish order.

The `audit.dlq` topic is listed in the architecture overview as reserved. Services do not create it or write to it.

## Flow

```
API Service  --repo.parsed-->  Indexer Service
                                    |
                                    +--audit.status-->  API Service
                                    |
                                    +--audit.tasks-->   Audit Worker
                                                            |
                                                            +--audit.status-->  API Service
```

1. `POST /audit/start` creates an audit row in PostgreSQL (`pending`) and publishes to `repo.parsed`.
2. Indexer clones the repository, chunks code, and writes to Qdrant. Then it publishes `indexed` to `audit.status` and one message per chunk to `audit.tasks`.
3. Audit Worker reads tasks, analyzes each chunk, and publishes `auditing`, then `completed` or `failed` to `audit.status`.
4. API Service reads `audit.status`, updates the audit row, and forwards the same event to SSE subscribers (`GET /audit/{audit_id}/live-status`).

## `repo.parsed`

Repository indexing job. Indexer reads the topic with `auto_offset_reset=latest` and auto commit: a group with no stored offset starts at the log end and does not consume messages published before its first connection.

```json
{
  "audit_id": "3f1c2a40-7b2e-4d1a-9c55-0a1b2c3d4e5f",
  "user_id": "keycloak-subject",
  "repo_url": "https://git.example.com/org/service.git",
  "branch": "main",
  "lang": "python"
}
```

| Field | Required | Used by |
|-------|----------|---------|
| `audit_id` | yes | partition key and audit identifier |
| `repo_url` | yes | clone |
| `branch` | yes | clone |
| `lang` | yes | default language for audit tasks |
| `user_id` | yes in API message | Indexer does not read it |
| `token` | no | optional git token; API does not send it today |

Clone errors are not sent back on this topic: Indexer publishes `failed` to `audit.status` and stops processing.

## `audit.tasks`

One task — one code chunk. Indexer sends them after `indexed` status. Message key is `audit_id`.

```json
{
  "chunk_id": "a1b2c3d4",
  "code": "def login(user):\n    ...",
  "file_path": "src/auth.py",
  "audit_id": "3f1c2a40-7b2e-4d1a-9c55-0a1b2c3d4e5f",
  "lang": "python",
  "chunk_index": 0,
  "total_chunks": 12
}
```

| Field | Meaning |
|-------|---------|
| `chunk_id` | chunk id in Qdrant and `audit_results` |
| `code` | source text of the chunk |
| `file_path` | path in the repository |
| `audit_id` | owning audit |
| `lang` | chunk language; if missing in Qdrant payload, `lang` from `repo.parsed` is used |
| `chunk_index` | zero-based chunk index |
| `total_chunks` | how many tasks were sent for this audit |

Audit Worker reads group `audit-worker` with `auto_offset_reset=earliest`, `enable_auto_commit=false`, and `max_poll_records=1`. Offset is committed after successful processing. On error the message stays uncommitted and will be retried.

Consumer session is extended for LLM calls: `session_timeout_ms=300000`, `heartbeat_interval_ms=10000`.

`auditing` is published once per audit — before the first chunk. `completed` is published when the chunk with `chunk_index >= total_chunks - 1` is processed. If chunk processing fails, the worker publishes `failed` once and skips remaining chunks for that `audit_id` in the process.

An empty repository (zero chunks) does not produce `audit.tasks` messages: Indexer only publishes `indexed` with `total_chunks: 0`.

## `audit.status`

Unified status channel. API writes the `status` value to PostgreSQL as-is and forwards the full JSON to SSE.

Common fields:

| Field | Writer | When present |
|-------|--------|--------------|
| `audit_id` | both | always |
| `status` | both | always |
| `error` | both | only on `failed` |
| `total_chunks` | both | after indexing and during audit |
| `progress` | Audit Worker | `auditing` (50) and `completed` (100) |
| `chunk_index` | Audit Worker | together with `progress` |

Indexer:

```json
{ "audit_id": "…", "status": "indexed", "total_chunks": 12 }
```

```json
{ "audit_id": "…", "status": "failed", "error": "clone failed" }
```

Audit Worker:

```json
{
  "audit_id": "…",
  "status": "auditing",
  "progress": 50,
  "chunk_index": 0,
  "total_chunks": 12
}
```

```json
{
  "audit_id": "…",
  "status": "completed",
  "progress": 100,
  "chunk_index": 11,
  "total_chunks": 12
}
```

```json
{ "audit_id": "…", "status": "failed", "error": "Error processing task …: …" }
```

Statuses currently published by services: `indexed`, `auditing`, `completed`, `failed`. Initial `pending` is set in PostgreSQL when the audit is created and is not sent to Kafka. API treats `all_completed` as terminal along with `completed` and `failed`, but no producer sends it.

API reads the topic with `auto_offset_reset=earliest` and auto commit, so after restart the group catches up on uncommitted statuses.
