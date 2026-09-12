# ADR: Apache Kafka vs RabbitMQ для очереди задач аудита

## Status
Accepted

## Context

SecureRepo Batch Auditor обрабатывает тысячи чанков кода. Нужно выбрать брокер сообщений.

*Apache Kafka*
- Архитектура: Log-based, immutable
- Throughput: Очень высокий (миллионы msg/sec)
- Ordering: Гарантировано в рамках partition
- Persistence: Дисковая (долгосрочное хранение)
- Scaling: Horizontal (partition rebalancing)
- Consumer Groups: Нативная поддержка
- Сложность: Высокая (ZooKeeper/KRaft, мониторинг)
- Open Source: Полностью open source

*RabbitMQ*
- Архитектура: Message queue (FIFO)
- Throughput: Высокий (десятки тыс. msg/sec)
- Ordering: Гарантировано в рамках queue
- Persistence: Опционально
- Scaling: Horizontal (sharding)
- Consumer Groups: Через competing consumers
- Сложность: Средняя

## Decision

Выбран **Apache Kafka**.

Обоснование:
1. **Batch Processing**: обработка 100k+ строк кода — Kafka выдерживает миллионы сообщений
2. **Replay**: возможность перечитать сообщения из offset при сбоях
3. **DLQ**: нативная поддержка dead letter queue через отдельный топик
4. **Consumer Groups**: автоматическое перераспределение нагрузки между воркерами
5. **Partitioning**: параллельная обработка чанков на разных партициях
6. **Open Source**: Полностью open source, поддерживается в большинстве облаков
7. **Экспертиза**: Широкая экспертиза в команде и на рынке

## Consequences

**Pros:**
- Высокий throughput для batch-обработки
- Гарантия доставки и порядка сообщений
- Возможность replay при сбоях
- Встроенный мониторинг (Kafka Exporter)
- Интеграция с Schema Registry (Avro)
- Open Source — поддержка во всех облаках (AWS MSK, GCP, Yandex Cloud)
- Большое community и экспертиза

**Cons:**
- Сложность настройки (KRaft mode)
- Задержки при acks=all
- Требуется мониторинг дискового пространства
- Не подходит для low-latency (<10ms)

**Mitigations:**
- acks=1 для баланса скорости/надёжности
- Компактные топики для старых сообщений
- Мониторинг lag consumer groups

## Почему не RabbitMQ

| Фактор | Kafka | RabbitMQ |
|--------|-------|----------|
| Batch processing | + | - |
| Replay | + | - |
| Schema Registry | + | - |
| DLQ | + (топик) | + (dead letter exchange) |
| Open Source | + | + |
| Экспертиза в облаках | Широкая | Ограниченная |
| Сложность | Высокая | Средняя |
| Persistence | Всегда | Опционально |
