# ADR: Выбор Qwen-Coder-Next для LLM-анализа кода

## Status
Accepted

## Context

SecureRepo Batch Auditor использует LLM для анализа кода и поиска уязвимостей.

Требования:
- Понимание кода (Python, Java, Go, JS, и др.)
- Контекст: достаточно для анализа чанков кода
- Russian language support
- Open Source
- Доступ в российских облаках

*Qwen-Coder-Next (Qwen/Qwen3-Coder-Next)*
- Тип: Code LLM (open weights)
- License: Apache 2.0 (open source)
- Parameters: 14B (Coder-Next)
- Context: 128K токенов
- Languages: 92+ языков программирования
- Training: Обучён на коде из GitHub, Stack Exchange
- Deployment: SberCloud, Yandex Cloud Foundation Models API
- Популярность: Высокая в России (Alibaba, китайские модели)

*Claude (Anthropic)*
- Тип: General LLM
- License: Proprietary
- Context: 200K токенов (Claude 3.5)
- Code: Отличное понимание кода
- Cloud: Нет в российских облаках

*GPT-4 (OpenAI)*
- Тип: General LLM
- License: Proprietary
- Context: 128K токенов
- Code: Отличное понимание кода
- Cloud: Нет в российских облаках

*CodeLlama (Meta)*
- Тип: Code LLM
- License: Llama 3.1 Community License (open source)
- Parameters: 7B-70B
- Context: 128K
- Cloud: Ограниченная поддержка в облаках

*DeepSeek-Coder*
- Тип: Code LLM
- License: MIT (open source)
- Parameters: 6.7B-33B
- Context: 128K
- Cloud: Ограниченная поддержка

## Decision

Выбран **Qwen-Coder-Next (Qwen/Qwen3-Coder-Next)**.

Обоснование:
1. **Специализация на коде**: обучен на 92+ языках программирования
2. **Open Source**: Apache 2.0, доступны веса модели
3. **Контекст 128K**: достаточно для анализа чанков кода
4. **Российские облака**: SberCloud Foundation, Yandex Cloud Foundation Models API
5. **Цена**: дешевле Claude/GPT при сопоставимом качестве для кода
6. **Популярность**: растёт в России и мире

## Consequences

**Pros:**
- Open Source: Apache 2.0, можно развернуть на своих серверах
- Специализация на коде: лучше понимает программирование
- Российские облака: SberCloud, Yandex Cloud — быстрый доступ
- Context 128K: помещается большой чанк кода
- Cost-effective: дешевле проприетарных моделей
- Сообщество: активное развитие от Alibaba

**Cons:**
- Менее развит reasoning по сравнению с Claude
- Требует мониторинга обновлений модели
- Зависимость от облака (Foundation Models API)

**Mitigations:**
- Fallback: возможность переключения на Qwen3-32B или другую модель
- Мониторинг качества: A/B тестирование с другими моделями
- Self-hosted: можно развернуть в своём кластере при необходимости

## Почему не Claude/GPT

| Фактор | Qwen-Coder-Next | Claude | GPT-4 |
|--------|-----------------|--------|-------|
| Open Source | + | - | - |
| Российские облака | + | - | - |
| Cost | Низкий | Высокий | Высокий |
| Code specialization | + | + | + |
| Context | 128K | 200K | 128K |

## Почему не CodeLlama/DeepSeek

| Фактор | Qwen-Coder-Next | CodeLlama | DeepSeek-Coder |
|--------|-----------------|-----------|----------------|
| Российские облака | + | - | - |
| Популярность в России | Высокая | Средняя | Растущая |
| Performance | Высокая | Средняя | Высокая |
| Community | Активная | Большая | Растущая |

## Альтернативы (рассмотрены)

| Модель | Причина отклонения |
|--------|-------------------|
| Claude/GPT | Proprietary, нет в российских облаках |
| CodeLlama | Менее эффективен для русского, ограниченная поддержка в облаках |
| DeepSeek-Coder | Альтернатива, но меньше облачная поддержка |
| Yi-Coder | Менее популярен |
