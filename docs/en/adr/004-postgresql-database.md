# ADR: PostgreSQL for audit results storage

> 🇷🇺 [Russian version](../../ru/adr/004-postgresql-database.md)

## Status

Accepted

## Context

Store audit findings with flexible JSON structure and ACID guarantees; Keycloak already expects PostgreSQL.

## Decision

**PostgreSQL** for JSONB findings, ACID, Keycloak/Langfuse stack alignment, and broad cloud support.

## Consequences

**Pros:** JSONB indexes, replication, large talent pool, optional pgvector later.

**Cons:** shared cluster with Keycloak needs connection pooling and DB isolation (`audit` vs `keycloak` databases).

**Mitigations:** separate databases on one cluster, PgBouncer, Alembic migrations, pg_exporter.

## Why not MongoDB

Would force two DB engines (Mongo + PostgreSQL for Keycloak/Langfuse).
