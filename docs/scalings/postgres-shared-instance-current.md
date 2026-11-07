# PostgreSQL in SecureRepo — three scaling stages

## Stage 1 · single PostgreSQL, three databases

```mermaid
flowchart TB
    subgraph Apps["Applications"]
        direction LR
        SR["SecureRepo<br/>API · Indexer · Audit Worker"]
        KC["Keycloak"]
        LF["Langfuse"]
    end

    subgraph S1["Stage 1"]
        PG(("PostgreSQL"))
        D1[("securerepo")]
        D2[("keycloak")]
        D3[("langfuse")]
        PG --- D1
        PG --- D2
        PG --- D3
    end

    SR --> D1
    KC --> D2
    LF --> D3

    classDef app fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef engine fill:#0ea5e9,stroke:#0369a1,stroke-width:3px,color:#fff
    classDef db fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f

    class SR,KC,LF app
    class PG engine
    class D1,D2,D3 db
```

---

## Stage 2 · dedicated PostgreSQL per service + read replicas

```mermaid
flowchart TB
    subgraph Apps2["Applications"]
        direction LR
        SR2["SecureRepo<br/>API · Indexer · Audit Worker"]
        KC2["Keycloak"]
        LF2["Langfuse"]
    end

    subgraph S2SR["Stage 2 · SecureRepo"]
        direction TB
        P1P[("Primary<br/>securerepo")]
        P1R[("Replica<br/>read-only")]
        P1P <-->|streaming replication| P1R
    end

    subgraph S2KC["Stage 2 · Keycloak"]
        direction TB
        P2P[("Primary<br/>keycloak")]
        P2R[("Replica<br/>read-only")]
        P2P <-->|streaming replication| P2R
    end

    subgraph S2LF["Stage 2 · Langfuse"]
        direction TB
        P3P[("Primary<br/>langfuse")]
        P3R[("Replica<br/>read-only")]
        P3P <-->|streaming replication| P3R
    end

    SR2 -->|read / write| P1P
    SR2 -.->|reports| P1R
    KC2 -->|read / write| P2P
    LF2 -->|read / write| P3P
    LF2 -.->|analytics| P3R

    classDef app fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef primary fill:#0ea5e9,stroke:#0369a1,stroke-width:2px,color:#fff
    classDef replica fill:#bae6fd,stroke:#0284c7,stroke-width:2px,stroke-dasharray: 6 4,color:#0c4a6e

    class SR2,KC2,LF2 app
    class P1P,P2P,P3P primary
    class P1R,P2R,P3R replica
```

---

## Stage 3 · PgDog sharding, ClickHouse for Langfuse, replicas retained

```mermaid
flowchart TB
    subgraph Apps3["Applications"]
        direction LR
        SR3["SecureRepo<br/>API · Indexer · Audit Worker"]
        KC3["Keycloak"]
        LF3["Langfuse"]
    end

    subgraph S3SR["Stage 3 · SecureRepo"]
        DOG{{"PgDog"}}
        subgraph SH1G["Shard 1"]
            S1P[("Primary")]
            S1R[("Replica")]
            S1P --- S1R
        end
        subgraph SH2G["Shard 2"]
            S2P[("Primary")]
            S2R[("Replica")]
            S2P --- S2R
        end
        subgraph SH3G["Shard 3"]
            S3P[("Primary")]
            S3R[("Replica")]
            S3P --- S3R
        end
        DOG --> S1P
        DOG --> S2P
        DOG --> S3P
        DOG -.->|read balance| S1R
        DOG -.->|read balance| S2R
        DOG -.->|read balance| S3R
    end

    subgraph S3KC["Stage 3 · Keycloak"]
        KCP[("Primary<br/>keycloak")]
        KCR[("Replica")]
        KCP --- KCR
    end

    subgraph S3LF["Stage 3 · Langfuse"]
        CH1[("ClickHouse<br/>node 1")]
        CH2[("ClickHouse<br/>node 2")]
        CH1 <-->|replicated merge tree| CH2
    end

    SR3 --> DOG
    KC3 --> KCP
    LF3 --> CH1
    LF3 --> CH2

    classDef app fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff
    classDef proxy fill:#14b8a6,stroke:#0f766e,stroke-width:3px,color:#fff
    classDef primary fill:#0ea5e9,stroke:#0369a1,stroke-width:2px,color:#fff
    classDef replica fill:#bae6fd,stroke:#0284c7,stroke-width:2px,stroke-dasharray: 6 4,color:#0c4a6e
    classDef ch fill:#fb923c,stroke:#c2410c,stroke-width:2px,color:#fff

    class SR3,KC3,LF3 app
    class DOG proxy
    class S1P,S2P,S3P,KCP primary
    class S1R,S2R,S3R,KCR replica
    class CH1,CH2 ch
```
