# ADR: Apache Kafka vs RabbitMQ for audit task queue

> 🇷🇺 [Russian version](../../ru/adr/002-kafka-vs-rabbitmq.md)

## Status

Accepted

## Context

Thousands of code chunks per audit batch; need durable, ordered, replayable messaging.

## Decision

**Apache Kafka** for high throughput, partition ordering, replay, consumer groups, and DLQ via dedicated topics.

## Consequences

**Pros:** batch scale, delivery guarantees, replay, cloud-native ops experience.

**Cons:** operational complexity, disk monitoring, not for sub-10 ms latency.

**Mitigations:** tune `acks`, compact old topics, monitor consumer lag.

## Why not RabbitMQ

Weaker fit for large batch replay and schema-registry patterns; Kafka matches 100k+ LOC pipeline better.
