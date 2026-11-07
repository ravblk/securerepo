# vLLM scaling — three stages

**Stack:** vLLM · **Qwen2.5-Coder-7B-Instruct** (Q4_K_M / AWQ) · OpenAI-compatible API · **Audit Worker** client.

Throughput figures from [LLM resource estimation](../en/RESOURCES.md#llm-resource-estimation). Product limit: **5 parallel audits** (FR-1.2 / FR-1.3) unless Kafka partitions and workers scale with GPU capacity.

---

## Stage 1 · MVP · one consumer GPU

```mermaid
flowchart TB
    subgraph Clients["Audit Worker · replicas 1 → 5"]
        direction LR
        W1["Worker"]
        W2["Worker"]
        W5["Worker"]
    end

    subgraph S1["Stage 1 · 1× vLLM · 1× GPU"]
        API[["OpenAI API :8000/v1"]]
        VLLM(("vLLM"))

        subgraph VRAM["VRAM · RTX 4090 24 GB example"]
            MW["Weights Q4 ~4.6 GB"]
            KV["KV cache ~16.4 GB"]
            OH["Overhead ~3 GB"]
        end

        API --> VLLM
        VLLM --- VRAM
    end

    W1 --> API
    W2 --> API
    W5 --> API

    classDef worker fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef api fill:#14b8a6,stroke:#0f766e,stroke-width:2px,color:#fff
    classDef engine fill:#f472b6,stroke:#be185d,stroke-width:3px,color:#fff
    classDef vram fill:#334155,stroke:#94a3b8,stroke-width:1px,color:#f1f5f9
    classDef kv fill:#7c3aed,stroke:#5b21b6,stroke-width:2px,color:#fff

    class W1,W2,W5 worker
    class API api
    class VLLM engine
    class MW,OH vram
    class KV kv
```

**Hardware:** 1× **RTX 3070 8 GB** (min) or **RTX 4090 24 GB** (reference).  
**Throughput:** ~**40–300 audits/hour**.

---

## Stage 2 · growth · one datacenter GPU (H100)

Still **one vLLM pod** — more KV headroom and batch capacity; **not** enough alone for enterprise SLA.

```mermaid
flowchart TB
    subgraph Clients2["Audit Worker"]
        WRK["Workers · same 5-audit cap or raise partitions"]
    end

    subgraph S2["Stage 2 · 1× vLLM · H100 80 GB"]
        API2[["OpenAI API :8000/v1<br/>prefix caching"]]
        V2(("vLLM"))

        subgraph VRAM2["VRAM · 80 GB"]
            MW2["Weights Q4 ~5 GB"]
            KV2["KV cache pool ~70 GB<br/>PagedAttention"]
            OH2["Overhead ~5 GB"]
        end

        API2 --> V2
        V2 --- VRAM2
    end

    WRK --> API2

    T2["~1200–1500 audits/hour<br/>single node — insufficient for 5000+"]

    T2 -.-> S2

    classDef worker fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef api fill:#14b8a6,stroke:#0f766e,stroke-width:2px,color:#fff
    classDef engine fill:#f472b6,stroke:#be185d,stroke-width:3px,color:#fff
    classDef vram fill:#334155,stroke:#94a3b8,stroke-width:1px,color:#f1f5f9
    classDef kv fill:#7c3aed,stroke:#5b21b6,stroke-width:2px,color:#fff
    classDef hint fill:#ecfdf5,stroke:#059669,stroke-width:2px,color:#065f46

    class WRK worker
    class API2 api
    class V2 engine
    class MW2,OH2 vram
    class KV2 kv
    class T2 hint
```

**Hardware:** 1× **H100 80 GB**.  
**Throughput:** ~**1200–1500 audits/hour** — next step is **horizontal** GPU replicas (Stage 3).

---

## Stage 3 · enterprise · multi-GPU fleet

```mermaid
flowchart TB
    subgraph Clients3["Audit Worker · scale with Kafka N"]
        WRK3["Workers"]
    end

    subgraph S3["Stage 3 · 2–8× vLLM replicas"]
        SVC[["Service vllm:8000"]]

        subgraph N1["GPU 1"]
            V1(("vLLM"))
            H1[("H100 80 GB")]
            V1 --- H1
        end

        subgraph N2["GPU 2"]
            V2b(("vLLM"))
            H2[("H100 80 GB")]
            V2b --- H2
        end

        subgraph N3["GPU … 8"]
            V3(("vLLM"))
            H3[("A100 / H100")]
            V3 --- H3
        end

        SVC --> V1
        SVC --> V2b
        SVC --> V3
    end

    WRK3 --> SVC

    T3["~5000+ audits/hour<br/>data-parallel · full model per GPU"]

    T3 -.-> S3

    classDef worker fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef svc fill:#14b8a6,stroke:#0f766e,stroke-width:2px,color:#fff
    classDef engine fill:#f472b6,stroke:#be185d,stroke-width:3px,color:#fff
    classDef gpu fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#fff
    classDef hint fill:#ecfdf5,stroke:#059669,stroke-width:2px,color:#065f46

    class WRK3 worker
    class SVC svc
    class V1,V2b,V3 engine
    class H1,H2,H3 gpu
    class T3 hint
```

**Hardware:** **2–8× H100 80 GB** or **8× A100+** (RESOURCES enterprise).  
**Throughput:** **5000+ audits/hour** aggregate.

---

| Stage | GPUs | vLLM pods | Throughput (indicative) |
|-------|------|-----------|-------------------------|
| 1 | 1× RTX 3070 / 4090 | 1 | 40–300 /h |
| 2 | 1× H100 80 GB | 1 | 1200–1500 /h |
| 3 | 2–8× H100 or 8× A100+ | N | 5000+ /h |

Use **`--enable-prefix-caching`** from Stage 2 onward when internal-rule prefixes repeat across chunks.
