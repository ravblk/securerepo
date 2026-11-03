# ADR: Qdrant vs ChromaDB for vector search

> 🇷🇺 [Russian version](../../ru/adr/003-qdrant-vs-chromadb.md)

## Status

Accepted

## Context

RAG over policies and code requires production-grade vector search with payload filters.

## Decision

**Qdrant** — HNSW performance, payload filtering, Kubernetes deployment, hybrid search path, REST/gRPC.

## Consequences

**Pros:** scale, filtering, replication, LangChain/LlamaIndex integrations.

**Cons:** another stateful service, no embedded mode.

**Mitigations:** single container in compose/K8s, dashboard monitoring.

## Rejected

Pinecone (cloud-only), Weaviate (heavier setup), Milvus (resource-heavy), pgvector alone (not specialized enough).
