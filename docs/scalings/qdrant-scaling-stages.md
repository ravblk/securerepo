# Qdrant scaling — primary and replica

Collection: **`internal_policies`** (corporate rules, 1024-dim BGE-m3).  
Code chunks are not stored in Qdrant today (Kafka + PostgreSQL `symbols`).

```mermaid
flowchart TB
    subgraph Apps["Applications"]
        direction LR
        IRI["Internal Rules Ingestion"]
        WRK["Audit Worker<br/>replicas: 1 → N"]
    end

    subgraph Cluster["Qdrant · internal_policies"]
        EP[["Endpoint<br/>qdrant:6333"]]

        MASTER[("Primary<br/>read / write")]
        REPLICA[("Replica<br/>read-only")]

        MASTER <-->|replication| REPLICA
        EP --> MASTER
        EP -.->|search offload| REPLICA
    end

    IRI -->|upsert| EP
    WRK -->|vector search| EP

    classDef app fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef lb fill:#c4b5fd,stroke:#6d28d9,stroke-width:2px,color:#fff
    classDef primary fill:#8b5cf6,stroke:#5b21b6,stroke-width:3px,color:#fff
    classDef replica fill:#e9d5ff,stroke:#7c3aed,stroke-width:2px,stroke-dasharray: 6 4,color:#5b21b6

    class IRI,WRK app
    class EP lb
    class MASTER primary
    class REPLICA replica
```

**Note:** target HA layout; MVP deploys a **single Qdrant pod** until search load requires a replica.
