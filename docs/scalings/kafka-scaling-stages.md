# Kafka scaling — partitions and Audit Workers

**Rule:** parallel audits ≈ **`audit.tasks` partition count**.  
**Message key:** `audit_id` — one audit stays on one partition (ordering per audit).

```mermaid
flowchart TB
    subgraph Flow["Audit pipeline"]
        API["API Service"]
        IDX["Indexer Service"]
    end

    subgraph Kafka["Kafka"]
        K(("Broker"))

        subgraph Parsed["repo.parsed · N partitions"]
            direction LR
            RP["P0 … P(N−1)"]
        end

        subgraph Tasks["audit.tasks · N partitions"]
            direction LR
            P0["P0"]
            P1["P1"]
            P2["P2"]
            PD["…"]
            PN["P(N−1)"]
        end

        STATUS["audit.status · 1 partition"]

        K --- Parsed
        K --- Tasks
        K --- STATUS
    end

    subgraph Workers["Audit Worker · consumer group audit-worker"]
        direction LR
        W0["Worker 1"]
        W1["Worker 2"]
        W2["Worker 3"]
        WD["…"]
        WN["Worker N"]
    end

    API -->|produce key=audit_id| Parsed
    IDX -->|consume| Parsed
    IDX -->|produce key=audit_id| Tasks

    P0 --> W0
    P1 --> W1
    P2 --> W2
    PN --> WN

    Workers -->|status updates| STATUS

    SCALE["Scale together:<br/>N workers ⇒ N partitions<br/>on repo.parsed & audit.tasks"]

    SCALE -.-> Tasks
    SCALE -.-> Workers

    classDef app fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef broker fill:#fbbf24,stroke:#b45309,stroke-width:3px,color:#78350f
    classDef part fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f
    classDef worker fill:#93c5fd,stroke:#2563eb,stroke-width:2px,color:#fff
    classDef hint fill:#ecfdf5,stroke:#059669,stroke-width:2px,color:#065f46

    class API,IDX app
    class K broker
    class P0,P1,P2,PN,RP,STATUS part
    class W0,W1,W2,WN worker
    class SCALE hint
```

**MVP today:** N = **5** on `repo.parsed` and `audit.tasks` → up to **5 workers** processing different audits in parallel. Need more throughput → raise **N** (partitions) and worker **replicas** together.
