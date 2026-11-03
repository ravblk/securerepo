# ADR: Embedding model — BAAI/bge-m3

> 🇷🇺 [Russian version](../../ru/adr/000-bge-m3-embedding-model.md)

## Status

Accepted

## Context

SecureRepo Batch Auditor uses RAG for policy and code search. Requirements:

- Text (Confluence): Russian support
- Code: syntax and structure understanding

**BAAI/bge-m3:** 100+ languages, 1024 dimensions, 512 token context, trained on code and natural language.

## Decision

Single model **BAAI/bge-m3** for both text and code.

| Data | Model | Qdrant collection |
|------|-------|-------------------|
| Text | BAAI/bge-m3 | internal_policies |
| Code | BAAI/bge-m3 | code_repo |

## Consequences

**Pros:** one deployment, unified 1024-dim collections, Russian support, good code quality.

**Cons:** specialized code models may score higher on code-only tasks.

**Mitigations:** single TEI server on port 8080, one endpoint for all payloads.
