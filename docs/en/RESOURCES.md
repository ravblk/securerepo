# SecureRepo Kubernetes resource requirements

> 🇷🇺 [Russian version](../ru/RESOURCES.md)

## Minimum cluster requirements

**Development / testing:**

- **CPU:** at least 6 cores
- **Memory:** at least 8 GB
- **Storage:** at least 50 GB

**Production:**

- **CPU:** 16+ cores recommended
- **Memory:** 24+ GB recommended
- **Storage:** 100+ GB with backup strategy

## Per-service resources

### Infrastructure

| Service | Replicas | CPU Request | Memory Request | CPU Limit | Memory Limit | Storage |
|---------|----------|-------------|----------------|-----------|--------------|---------|
| PostgreSQL | 1 | 250m | 512Mi | 1 | 2Gi | 10Gi |
| Keycloak | 1 | 250m | 512Mi | 1 | 2Gi | 5Gi |
| Qdrant | 1 | 250m | 512Mi | 1 | 2Gi | 20Gi |
| Kafka | 1 | 250m | 512Mi | 2 | 4Gi | 10Gi |
| Langfuse | 1 | 250m | 512Mi | 500m | 1Gi | Shared with PostgreSQL |

**Infrastructure total:** 1.25 cores / 2.5 GB (requests) | 5.5 cores / 11 GB (limits)

### Application services

| Service | Replicas | CPU Request | Memory Request | CPU Limit | Memory Limit |
|---------|----------|-------------|----------------|-----------|--------------|
| Embedding Service | 1 | 1000m | 2Gi | 4000m | 8Gi |
| API Service | 1 | 250m | 512Mi | 1 | 1Gi |
| Frontend Service | 1 | 100m | 128Mi | 500m | 512Mi |
| Internal Rules Ingestion | 1 | 200m | 256Mi | 1 | 1Gi |
| Indexer Service | 1 | 250m | 512Mi | 1 | 1Gi |
| Audit Worker | 1 | 300m | 768Mi | 2.5 | 2.5Gi |

**Applications total:** 2.1 cores / 4.176 GB (requests) | 10 cores / 14 GB (limits)

## Summary

### Minimum (requests only)

- **CPU:** 3.35 cores
- **Memory:** 6.676 GB
- **Storage:** 45 GB (PostgreSQL shared by app and Langfuse)

### Maximum (limits)

- **CPU:** 15.5 cores
- **Memory:** 25 GB
- **Storage:** 45 GB (PostgreSQL shared by app and Langfuse)

---

### LLM resource estimation

Example: Qwen2.5-7B (28 layers, GQA) with Q4_K_M, KV cache, and paged attention.

#### 1. Model weights (Q4_K_M)

Qwen2.5-7B-Instruct in Q4_K_M:

- **File size:** 4.4–4.7 GB
- **VRAM:** ~5 GB
- **Savings:** ~3× vs FP16 (~14 GB)

#### 2. KV cache + paged attention

| Parameter | Value | Notes |
|-----------|-------|-------|
| **KV cache per token** | ~56 KB (fp16) / ~28 KB (fp8) | Qwen2.5-7B |
| **1 request (4096 tokens)** | ~229 MB (fp16) / ~115 MB (fp8) | Prompt + generation |
| **10 concurrent requests** | ~2.3 GB (fp16) / ~1.2 GB (fp8) | With paged attention |
| **100 concurrent requests** | ~23 GB (fp16) / ~12 GB (fp8) | RTX 4090 24 GB |
| **Paged attention overhead** | +20–30% | Block reserve |

**Plan ~10–20 GB for KV cache** depending on concurrency and GPU size.

#### 3. Activations and vLLM overhead

- **Activations:** ~1–2 GB VRAM
- **Model memory overhead:** ~1 GB
- **Reserved buffer:** ~1–2 GB

#### 4. VRAM layout (RTX 4090 24 GB example)

```
├── Model weights (Q4_K_M):    4.6 GB (19%)
├── KV Cache Pool:           16.4 GB (68%)
├── activations + overhead:    1.0 GB (4%)
├── model memory overhead:     1.0 GB (4%)
└── Reserved (buffer):         1.0 GB (4%)
    ──────────────────────────────────────────────
    Total:                    24 GB (100%)
```

#### 5. GPU performance

| GPU | VRAM | Max parallel requests | Latency per chunk | Throughput |
|-----|------|----------------------|-------------------|------------|
| **RTX 3060 12GB** | 12GB | 120-180 | 1.5-3.0s | 60-100 audits/hour |
| **RTX 3070 8GB** | 8GB | 60-90 | 1.8-3.5s | 40-70 audits/hour |
| **RTX 4090 24GB** | 24GB | 180-250 | 1.0-1.6s | 200-300 audits/hour |
| **A100 40GB** | 40GB | 350-500 | 0.6-1.2s | 500-700 audits/hour |
| **H100 80GB** | 80GB | 800-1200 | 0.4-0.8s | 1200-1500 audits/hour |

**Optimizations:**

- **Q4 quantization:** 3–4× more parallelism on the same GPU
- **Prefix caching:** 4–6× speedup for shared prefixes (OWASP rules)
- **Paged attention:** 85–95% VRAM utilization vs 50–60% with FP16

**SecureRepo sizing:**

- **Minimum:** 1× RTX 3070 8 GB → 40–70 audits/hour
- **Recommended:** 2–4× RTX 4090 → 400–800 audits/hour
- **Enterprise:** 8× A100+ → 5000+ audits/hour
