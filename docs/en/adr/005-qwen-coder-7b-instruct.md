# ADR: Qwen2.5-Coder-7B (GGUF) for code LLM analysis

> 🇷🇺 [Russian version](../../ru/adr/005-qwen-coder-7b-instruct.md)

## Status

Accepted

## Context

Audit worker needs local code LLM: strict JSON, CWE/OWASP mapping, Russian explanations, ~6 GB VRAM, Apache 2.0.

## Decision

**Qwen2.5-Coder-7B-Instruct in GGUF** via Ollama (OpenAI-compatible API).

## Rationale

Code-specialized 7B model; RAG supplies rules so 7B is enough; GGUF + Ollama simplifies deployment; strong Russian output.

## Consequences

**Pros:** data stays on-prem, low API cost, fast tokens for Kafka pipeline.

**Cons:** weaker reasoning than frontier models; occasional JSON defects.

**Mitigations:** `json-repair`, grounding checks, few-shot JSON examples in prompts.

## Rejected alternatives

Qwen 3B (too small), Llama 3.1 8B (general-purpose), DeepSeek V2 Lite 16B (heavier), GPTQ (tooling friction).
