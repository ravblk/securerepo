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
- **OWASP Seeder** — сервис загрузки OWASP правил
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
kubectl apply -f k8s/secrets/
```

**Создаваемые секреты:**
- `postgres-secret` — учетные данные PostgreSQL `POSTGRES_PASSWORD` и `POSTGRES_URL`
- `frontend-secret` — Keycloak client secrets  `KEYCLOAK_CLIENT_SECRET`
- `embedding-secret` — HuggingFace token для модели эмбеддингов `HF_TOKEN`
- `fm-secret` - api key для дооступа к llm `FM_TOKEN`

### 3. Развертывание инфраструктуры

#### 3.1 PostgreSQL

```bash
kubectl apply -f k8s/01-postgres.yaml
```

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
##### 3.4.1 Keycloak создать клиента 

   - **Client ID**: `securerepo-api`
   - **Client Protocol**: `openid-connect`

#### 3.5 Ollama (LLM-сервер)

```bash
kubectl apply -f k8s/ollama.yaml
```

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

#### 5.4 OWASP Seeder

```bash
kubectl apply -f k8s/09-owasp-seeder.yaml
```

Этот сервис автоматически загружает OWASP правила в систему.

#### 5.5 Indexer Service

```bash
kubectl apply -f k8s/10-indexer-service.yaml
```

#### 5.6 Audit Worker

```bash
kubectl apply -f k8s/11-audit-worker.yaml
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