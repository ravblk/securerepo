# ADR-001: Keycloak for authentication and authorization

> 🇷🇺 [Russian version](../../ru/adr/001-use-keycloak-for-authentication.md)

**Date:** 2026-08-31  
**Status:** Accepted

## Context

SecureRepo needs auth that works air-gapped (no cloud IAM).

## Options

1. **Keycloak (chosen)** — Apache 2.0, OAuth2/OIDC, self-hosted
2. **Custom JWT** — full control, high maintenance
3. **Cloud IAM** — not air-gapped

## Decision

Use **Keycloak** as self-hosted IAM.

## Rationale

Popular OSS IAM, no vendor lock-in, RBAC and OIDC built-in, Kubernetes-ready images.

## Consequences

**Pros:** fast integration, standard protocols, scalability.

**Cons:** extra component to operate.

## Future alternatives

Dex, ORY Hydra, or a minimal custom OIDC stack if Keycloak is too heavy.
