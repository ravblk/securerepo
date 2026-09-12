# OWASP Seeder Service

Загрузка OWASP/CWE базы знаний в Qdrant с возможностью сканирования вложенных страниц.

## Архитектура

Сервис организован как модуль `seeder/` с чётким разделением ответственности:
- `config.py` — настройки (через `dataclass(frozen=True)`)
- `models.py` — Pydantic API модели
- `exceptions.py` — кастомные исключения и обработчики
- `web_scraper.py` — веб-скрапер с обнаружением вложенных ссылок
- `embedding_service.py` — сервис для эмбеддингов
- `qdrant_service.py` — сервис для Qdrant
- `seed_controller.py` — бизнес-логика сидинга
- `main.py` — FastAPI приложение

## Функции

- Загрузка OWASP Top 10 в Qdrant (коллекция `general_best_practices`)
- 🔍 **Открытие и обработка вложенных страниц**
- Seed при запуске системы
- Использует **intfloat/multilingual-e5-large** (порт 8080)

## Сканирование вложенных страниц

### Как работает

1. **Базовые страницы**: Загружает указанные URL из `PAGES_JSON`
2. **Открытие ссылок**: Находит все ссылки на каждой странице
3. **Фильтрация**:
   - Только разрешённые домены (owasp.org по умолчанию)
   - Избегает дубликатов
   - Ограничивает глубину сканирования
4. **Обработка**: Рекурсивно обрабатывает найденные вложенные страницы
5. **Индексация**: Сохраняет все страницы в Qdrant

### Конфигурация

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `ENABLE_NESTED_SCANNING` | Включить/выключить сканирование вложенных страниц | `true` |
| `MAX_DEPTH` | Максимальная глубина сканирования | `2` |
| `MAX_PAGES_PER_DOMAIN` | Максимум страниц на домен (защита от DoS) | `50` |
| `FOLLOW_EXTERNAL_LINKS` | Переходить по внешним ссылкам | `false` |

### Пример конфигурации

```bash
# Включить сканирование вложенных страниц с глубиной 2
ENABLE_NESTED_SCANNING=true
MAX_DEPTH=2
MAX_PAGES_PER_DOMAIN=100

# Базовые страницы OWASP Top 10 + все найденные вложенные
PAGES_JSON=["https://owasp.org/www-project-top-ten/","https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control"]
```

## Источник данных

**OWASP Top 10** и статистические меры, чаще сглаживающие верхние 2-3 позиции.

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `QDRANT_URL` | URL Qdrant | `http://qdrant:6333` |
| `EMBEDDING_URL` | URL Embedding Service | `http://embedding:8080` |
| `PAGES_JSON` | Список страниц в формате JSON | `[]` |
| `ENABLE_NESTED_SCANNING` | Сканировать вложенные страницы | `true` |
| `MAX_DEPTH` | Максимальная глубина сканирования | `2` |
| `MAX_PAGES_PER_DOMAIN` | Максимум страниц на домен | `50` |

## Запуск

### Healthcare
```bash
curl http://localhost:8004/health
```

### Запуск сидинга
```bash
curl -X POST http://localhost:8004/seed/start -H "Content-Type: application/json" -d '{}'
```

### Запуск с глубиной 3
```bash
curl -X POST http://localhost:8004/seed/start -H "Content-Type: application/json" -d '{"max_depth": 3}'
```

### Проверка статуса
```bash
curl http://localhost:8004/seed/{seed_id}/status
```

### История операций
```bash
curl http://localhost:8004/seed/history
```

## Мониторинг

Логи содержат информацию о:
- Обнаруженных вложенных ссылках
- Обработанных страницах
- Ошибках парсинга
- Прогрессе процесса

```
INFO: Found 15 nested links at depth 1 from https://owasp.org/www-project-top-ten/
INFO: Total URLs to process: 25 (including nested pages)
INFO: Successfully processed: Broken Access Control
```

## Безопасность

### Защита от DoS
- `MAX_PAGES_PER_DOMAIN`: Ограничение на количество страниц
- Обнаружение только разрешённых доменов по умолчанию
- Тайм-ауты для HTTP запросов

### Валидация URL
- Только HTTPS/HTTP протоколы
- Фильтрация недопустимых схем
- Избегание дубликатов через visited URLs

## Пример использования

### Базовое сидирование (только указанные страницы)
```bash
export ENABLE_NESTED_SCANNING=false
curl -X POST http://localhost:8004/seed/start
```

### Полное сканирование (включая вложенные страницы)
```bash
export ENABLE_NESTED_SCANNING=true
export MAX_DEPTH=2
curl -X POST http://localhost:8004/seed/start
```

### Кастомный набор страниц
```bash
export PAGES_JSON='["https://owasp.org/Top10/2025/A07_2025-Authentication_Failures","https://owasp.org/www-project-cwe/"]'
curl -X POST http://localhost:8004/seed/start
```

## Когда запускать

Один раз при развёртывании системы для инициализации базы знаний о безопасности.

## Архитектурные преимущества

1. **Гибкость**: Настройка глубины сканирования через переменные окружения
2. **Безопасность**: Защита от DoS и контроль разрешённых доменов
3. **Масштабируемость**: Возможность ограничения ресурсов
4. **Поддерживаемость**: Модульная архитектура с чётким разделением ответственности
