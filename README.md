# SecureRepo 🛡️

SecureRepo Batch Auditor — корпоративная система массового аудита безопасности кодовых баз (SaaS, Private Cloud / On-Premise).

Проект построен по микросервисной архитектуре с использованием:
- **PostgreSQL** — реляционная база данных
- **Qdrant** — векторная база данных для эмбеддингов
- **Kafka** — асинхронная обработка задач
- **Keycloak** — аутентификация и авторизация
- **Langfuse** — мониторинг LLM операций

Сервисы: API Service, Frontend Service, Indexer Service, Embedding Service, Internal Rules Ingestion, OWASP Seeder, Audit Worker.

## 📚 Документация

### Развертывание
- [Руководство по развертыванию в Kubernetes](docs/k8s-deployment-guide.md)
-Конфигурация секретов в Kubernetes](k8s/secrets-example/)

### Архитектура и дизайн
- [Архитектура системы](docs/architecture/ARCHITECTURE.md)
- [Deployment Diagram](docs/architecture/DEPLOYMENT_DIAGRAM.md)
- [API Documentation](docs/architecture/API.md)
- [Kafka Topics](docs/architecture/KAFKA_TOPICS.md)

### Развитие и тестирование
- [Требования к ресурсам](docs/RESOURCES.md)
- [Тестирование уязвимостей](tests/test_vulnerability_detection.py)

**⚠️ Важно**: Проект находится в активной разработке. Перед продакшн использованием ознакомьтесь с актуальной документацией.
