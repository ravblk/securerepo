# SecureRepo — Руководство по развертыванию в Kubernetes

## Обзор архитектуры

SecureRepo Auditor — система семантического поиска и аудита кода на основе правил безопасности. Система состоит из следующих компонентов:

### Инфраструктурные сервисы:
- **PostgreSQL** — реляционная база данных для хранения метаданных
- **Qdrant** — векторная база данных для эмбеддингов правил и кода
- **Kafka** — очередь сообщений для асинхронной обработки
- **Keycloak** — система аутентификации и авторизации
- **Ollama** — LLM-сервер для анализа кода (Qwen2.5-Coder-7B-Instruct)

### Core сервисы:
- **Embedding Service** — сервис создания эмбеддингов (модель BAAI/bge-m3)

### Бизнес сервисы:
- **API Service** — REST API для взаимодействия с системой
- **Frontend Service** — веб-интерфейс
- **Internal Rules Ingestion** — сервис импорта внутренних правил
- **Indexer Service** — сервис индексации репозиториев
- **Audit Worker** — воркер аудита кода (зависит от Ollama)

## Предварительные требования

### Программное обеспечение:
- `kubectl` — CLI для взаимодействия с Kubernetes
- `docker` или доступ к container registry

### Требования к кластеру:
- Kubernetes версии 1.24+
- Минимум 4 CPU cores и 16GB RAM для базовой инсталляции
- GPU ресурсы (推荐 6GB+ VRAM) для Ollama с моделью Qwen2.5-Coder-7B-Instruct

### Предварительная настройка:
- Убедитесь, что kubectl настроен и может подключаться к нужному кластеру
- Все Docker образы должны быть доступны в registry (`securerepo/*:latest`)

## Пошаговый процесс деплоя

### 1. Создание namespace

Создаем namespace `securerepo` для изоляции всех сервисов:

```bash
kubectl apply -f k8s/00-namespace.yaml
# или
kubectl apply -f k8s/secrets/00-namespace.yaml
```

Проверка:
```bash
kubectl get namespaces | grep securerepo
```

### 2. Создание секретов

Создаем секреты с конфиденциальными данными:

```bash
kubectl apply -f k8s/secrets-example/
```

**Создаваемые секреты:**
- `postgres-secret` — учетные данные PostgreSQL `POSTGRES_PASSWORD` и `POSTGRES_URL`
- `keycloak-secret` — Keycloak client secrets  `KEYCLOAK_CLIENT_SECRET`
- `embedding-secret` — HuggingFace token для модели эмбеддингов `HF_TOKEN`
- `OAPI-Secret` - api key для дооступа к llm `OAPI_TOKEN` , `OAPI_MODELS_URL`

### 3. Развертывание инфраструктуры

#### 3.1 PostgreSQL

```bash
kubectl apply -f k8s/01-postgres.yaml
```

При старте PostgreSQL создаёт только базу `securerepo` (`POSTGRES_DB`). Базы для Keycloak и Langfuse в этом же инстансе нужно создать до запуска этих сервисов:

```bash
kubectl -n securerepo exec deploy/postgres -- \
  psql -U securerepo -d securerepo -c "CREATE DATABASE keycloak;"

kubectl -n securerepo exec deploy/postgres -- \
  psql -U securerepo -d securerepo -c "CREATE DATABASE langfuse;"
```

- Keycloak подключается к базе `keycloak` пользователем `securerepo` (пароль из `postgres-secret`).
- Langfuse подключается к базе `langfuse`. В секрете `langfuse-secrets` ключ `DATABASE_URL` должен быть вида `postgresql://securerepo:<пароль>@postgres:5432/langfuse`.

#### 3.2 Qdrant (Векторная база)

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

##### 3.4.2 Keycloak создать realm `securerepo`(при необходимости) и клиента

   - **Client ID**: `securerepo-api`
   - **Client Protocol**: `openid-connect`

Нужно обновить секреты kubectl apply -f k8s/secrets/kc-secrets.yaml

#### 3.5 Ollama (LLM-сервер)

**Особенности Ollama:**
- Модель: Qwen2.5-Coder-7B-Instruct (GGUF формат)
- Требует GPU с 6GB+ VRAM
- Предоставляет OpenAI-совместимый API

### 4. Развертывание core сервисов

#### 4.1 Embedding Service

Этот сервис использует модель BAAI/bge-m3 для создания эмбеддингов.

```bash
kubectl apply -f k8s/05-embedding-service.yaml
```

- Создает ConfigMap с настройками модели
- использует HF_SECRET для HuggingFace токена
- Требует до 8GB RAM для работы модели


**Важно:** Embedding Service имеет extended startup time (240s), так как загружает модель в память.

### 5. Развертывание бизнес сервисов

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

База `langfuse` создаётся на шаге 3.1. `DATABASE_URL` в `langfuse-secrets` должен указывать на неё.

Создать клиента который будет подключаться к Langfuse из Audit Worker

Нужно создать проект и ключи доступа к нему и прописать их в секрете
`SECUREREPO_PUBLIC_KEY` (значение `pk-lf-...`), `SECUREREPO_SECRET_KEY` (значение `sk-lf-...`).
В `12-audit-worker.yaml` они мапятся в `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` без перестановки.

```bash
kubectl apply -f k8s/secrets/langfuse-secrets.yaml
```

#### 5.6 Audit Worker

```bash
kubectl apply -f k8s/12-audit-worker.yaml
```

**Важно:** Audit Worker зависит от Ollama для анализа кода.

### 6. Финальная проверка статуса

Проверьте статус всех подов:

```bash
kubectl -n securerepo get pods
```


## Мониторинг и логи

### Просмотр логов конкретного сервиса:

```bash
# API Service
kubectl -n securerepo logs -f deployment/api-service

# Embedding Service
kubectl -n securerepo logs -f deployment/embedding

# Audit Worker (LLM аудита)
kubectl -n securerepo logs -f deployment/audit-worker

# Ollama
kubectl -n securerepo logs -f deployment/ollama
```

### Мониторинг ресурсов:

```bash
kubectl -n securerepo top pods
kubectl -n securerepo top nodes
```

## Удаление развертывания

Для удаления всех сервисов:

```bash
kubectl delete -f k8s/
```

Для удаления namespace со всеми ресурсами:

```bash
kubectl delete namespace securerepo
```

## Как запустить модель на vLLM

Важный нюанс: **vLLM официально поддерживает GGUF** начиная с версий 0.4.x+ и 0.5.x+, но делает это через движок `llamafile`. Однако vLLM работает **гораздо быстрее и стабильнее** с форматами `AWQ` или `GPTQ`, а также с нативным `fp16/bf16`.

Если вы принципиально хотите использовать именно GGUF, команда будет такой:

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