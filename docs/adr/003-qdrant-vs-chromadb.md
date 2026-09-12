# ADR: Qdrant vs ChromaDB для векторного поиска

## Status
Accepted

## Context

SecureRepo Batch Auditor использует RAG для поиска политик и кода. Нужна векторная БД.

*Qdrant*
- Тип: Векторная БД (dedicated)
- Language: Rust
- Deployment: Docker, Kubernetes
- Filtering: Нативная поддержка (payload)
- Hybrid Search: Да (dense + sparse)
- Performance: Очень высокая (HNSW)
- Cloud: Qdrant Cloud (опционально)
- Интеграции: LangChain, LlamaIndex, Reranking
- Open Source: Полностью open source

*ChromaDB*
- Тип: Векторное хранилище (embedded)
- Language: Python
- Deployment: Python library, Docker
- Filtering: Ограниченная
- Hybrid Search: Нет
- Performance: Средняя
- Cloud: Нет
- Интеграции: LangChain, LlamaIndex

## Decision

Выбран **Qdrant**.

Обоснование:
1. **Production-ready**: зрелый продукт с мониторингом, репликацией
2. **Payload filtering**: фильтрация по языку, severity без векторного поиска
3. **Kubernetes**: простое развёртывание в K8s
4. **Hybrid Search**: поддержка sparse-векторов (BM25) в будущем
5. **Performance**: HNSW с оптимизациями (quantization, memmap)
6. **Schema**: строгая схема коллекций с валидацией
7. **Экспертиза**: Растущая экспертиза и популярность в России и мире
8. **Open Source**: Полностью open source, поддержка в облаках

## Consequences

**Pros:**
- Высокая производительность (миллионы векторов)
- Гибкая фильтрация (payload + vector)
- Production-grade (репликация, шардирование)
- REST API + gRPC
- Dashboard для мониторинга
- Интеграция с LangChain/LlamaIndex
- Open Source — поддержка в большинстве облаков
- Растущая экспертиза и community

**Cons:**
- Дополнительная БД в стеке
- Требует ресурсов (Rust, но не lightweight)
- Нет embedded mode

**Mitigations:**
- Один контейнер в docker-compose
- Мониторинг через Qdrant dashboard
- Точечное масштабирование при росте

## Почему не ChromaDB

| Фактор | Qdrant | ChromaDB |
|--------|--------|----------|
| Production-ready | + | - |
| Payload filtering | + | Ограниченно |
| Kubernetes | + | - |
| Hybrid Search | + | - |
| Performance | Высокая | Средняя |
| Embedded | - | + |
| Cloud | + | - |
| Open Source | + | + |
| Экспертиза | Растущая | Ограниченная |

## Альтернативы (рассмотрены)

| БД | Причина отклонения |
|----|-------------------|
| Pinecone | Cloud-only, не Air-gapped |
| Weaviate | Сложнее в настройке |
| Milvus | Тяжелее, больше ресурсов |
| pgvector | Не специализированная векторная БД |
