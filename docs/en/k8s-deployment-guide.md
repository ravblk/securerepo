# SecureRepo — Kubernetes deployment guide

> 🇷🇺 [Russian version](../ru/k8s-deployment-guide.md)

## Architecture overview

SecureRepo Auditor is a semantic search and code auditing system driven by security rules. Components:

### Infrastructure

- **PostgreSQL** — relational metadata
- **Qdrant** — vector store for rules and code embeddings
- **Kafka** — async message queue
- **Keycloak** — authentication and authorization
- **Ollama** — LLM server for code analysis (Qwen2.5-Coder-7B-Instruct)

### Core services

- **Embedding Service** — embeddings (BAAI/bge-m3)

### Application services

- **API Service** — REST API
- **Frontend Service** — web UI
- **Internal Rules Ingestion** — import internal rules
- **Indexer Service** — repository indexing
- **Audit Worker** — code audit worker (depends on Ollama)

## Prerequisites

### Software

- `kubectl` — Kubernetes CLI
- `docker` or access to a container registry

### Cluster

- Kubernetes 1.24+
- At least 4 CPU cores and 16 GB RAM for a minimal install
- GPU with 6 GB+ VRAM recommended for Ollama with Qwen2.5-Coder-7B-Instruct

### Setup

- Configure `kubectl` for your target cluster
- Ensure images are available in the registry (`securerepo/*:latest`)

## Step-by-step deployment

### 1. Create namespace

Create the `securerepo` namespace:

```bash
kubectl apply -f k8s/00-namespace.yaml
# or
kubectl apply -f k8s/secrets/00-namespace.yaml
```

Verify:

```bash
kubectl get namespaces | grep securerepo
```

### 2. Create secrets

Apply secrets with sensitive configuration:

```bash
kubectl apply -f k8s/secrets-example/
```

**Secrets created:**

- `postgres-secret` — PostgreSQL credentials `POSTGRES_PASSWORD`, `POSTGRES_URL`
- `keycloak-secret` — Keycloak client secret `KEYCLOAK_CLIENT_SECRET`
- `embedding-secret` — Hugging Face token `HF_TOKEN`
- `OAPI-Secret` — LLM API access `OAPI_TOKEN`, `OAPI_MODELS_URL`

### 3. Deploy infrastructure

#### 3.1 PostgreSQL

```bash
kubectl apply -f k8s/01-postgres.yaml
```

On first start PostgreSQL only creates the `securerepo` database (`POSTGRES_DB`). Create databases for Keycloak and Langfuse on the same instance before starting those services:

```bash
kubectl -n securerepo exec deploy/postgres -- \
  psql -U securerepo -d securerepo -c "CREATE DATABASE keycloak;"

kubectl -n securerepo exec deploy/postgres -- \
  psql -U securerepo -d securerepo -c "CREATE DATABASE langfuse;"
```

- Keycloak uses database `keycloak` as user `securerepo` (password from `postgres-secret`).
- Langfuse uses database `langfuse`. In `langfuse-secrets`, `DATABASE_URL` must be `postgresql://securerepo:<password>@postgres:5432/langfuse`.

#### 3.2 Qdrant

```bash
kubectl apply -f k8s/03-qdrant.yaml
```

#### 3.3 Kafka

```bash
kubectl apply -f k8s/04-kafka.yaml
```

#### 3.4 Keycloak

```bash
kubectl apply -f k8s/02-keycloak.yaml
```

##### 3.4.2 Create realm `securerepo` (if needed) and client

- **Client ID**: `securerepo-api`
- **Client protocol**: `openid-connect`

Update secrets: `kubectl apply -f k8s/secrets/kc-secrets.yaml`

#### 3.5 Ollama (LLM server)

**Ollama notes:**

- Model: Qwen2.5-Coder-7B-Instruct (GGUF)
- Requires GPU with 6 GB+ VRAM
- OpenAI-compatible API

### 4. Deploy core services

#### 4.1 Embedding Service

Uses BAAI/bge-m3 for embeddings.

```bash
kubectl apply -f k8s/05-embedding-service.yaml
```

- ConfigMap with model settings
- Uses `HF_SECRET` for the Hugging Face token
- Up to 8 GB RAM for the model

**Note:** Embedding Service has a long startup (240s) while loading the model.

### 5. Deploy application services

#### 5.1 API Service

```bash
kubectl apply -f k8s/06-api-service.yaml
```

#### 5.2 Frontend Service

```bash
kubectl apply -f k8s/07-frontend-service.yaml
```

#### 5.3 Internal Rules Ingestion

```bash
kubectl apply -f k8s/08-internal-rules-ingestion.yaml
```

#### 5.4 Indexer Service

```bash
kubectl apply -f k8s/10-indexer-service.yaml
```

#### 5.5 Langfuse

```bash
kubectl apply -f k8s/11-langfuse.yaml
```

Database `langfuse` is created in step 3.1. `DATABASE_URL` in `langfuse-secrets` must point to it.

Create a Langfuse project and API keys for Audit Worker. Set in secrets:

`SECUREREPO_PUBLIC_KEY` (`pk-lf-...`), `SECUREREPO_SECRET_KEY` (`sk-lf-...`).

In `12-audit-worker.yaml` they map to `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` unchanged.

```bash
kubectl apply -f k8s/secrets/langfuse-secrets.yaml
```

#### 5.6 Audit Worker

```bash
kubectl apply -f k8s/12-audit-worker.yaml
```

**Note:** Audit Worker depends on Ollama for code analysis.

### 6. Final status check

```bash
kubectl -n securerepo get pods
```

## Monitoring and logs

### Service logs

```bash
# API Service
kubectl -n securerepo logs -f deployment/api-service

# Embedding Service
kubectl -n securerepo logs -f deployment/embedding

# Audit Worker
kubectl -n securerepo logs -f deployment/audit-worker

# Ollama
kubectl -n securerepo logs -f deployment/ollama
```

### Resource usage

```bash
kubectl -n securerepo top pods
kubectl -n securerepo top nodes
```

## Teardown

Remove all manifests:

```bash
kubectl delete -f k8s/
```

Remove the namespace and all resources:

```bash
kubectl delete namespace securerepo
```

## Running the model on vLLM

vLLM supports **GGUF** from 0.4.x+ via the `llamafile` engine, but is **faster and more stable** with `AWQ`, `GPTQ`, or native `fp16/bf16`.

To use GGUF explicitly:

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct-GGUF \
  --tokenizer Qwen/Qwen2.5-Coder-7B-Instruct \
  --quantization gguf \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.8 \
  --enable-prefix-caching \
  --host 0.0.0.0 --port 8000
```
