workspace {

    !identifiers hierarchical

    model {
        // ===== Внешние системы =====
        user = person "Пользователь" "Сотрудник, запускающий аудит безопасности"

        internalRules = softwareSystem "Internal Rules" "Источник корпоративных политик безопасности" {
            tags "external"
        }

        owasp = softwareSystem "OWASP" "База знаний уязвимостей" {
            tags "external"
        }

        keycloak = softwareSystem "Keycloak" "Система идентификации и авторизации (OAuth2/OIDC)" {
            tags "external"
        }

        securerepo = softwareSystem "SecureRepo" "Система массового аудита безопасности" {

            // ===== Knowledge & Data Layer =====
            qdrant = container "Qdrant" "Векторная БД для RAG" {
                internalPolicies = component "internal_policies" "Корпоративные политики (Internal Rules)"
                generalPractices = component "general_best_practices" "OWASP/CWE база знаний"
                codeRepo = component "code_repo" "AST-чанки кода репозитория"
            }

            kafka = container "Apache Kafka" "Асинхронная обработка (KRaft)" {
                repoParsed = component "repo.parsed" "URL репозитория"
                auditTasks = component "audit.tasks" "Задачи для воркеров"
                auditStatus = component "audit.status" "Статусы (indexed, auditing, completed)"
                auditDlq = component "audit.dlq" "Dead Letter Queue"
            }

            postgres = container "PostgreSQL" "Пользователи, RBAC, статусы аудитов, результаты" {
                users = component "users" "Таблица пользователей"
                audits = component "audits" "Статусы аудитов (pending → indexing → indexed → auditing → completed)"
                auditLogs = component "audit_logs" "Логи запусков"
                auditResults = component "audit_results" "Результаты анализа чанков (JSONB)"
            }

            // ===== Application Layer =====
            owaspSeeder = container "OWASP Seeder" "Seed OWASP/CWE базы знаний" {
                seedScript = component "Seed Script" "Загрузка правил в Qdrant"
                htmlParser = component "HTML Parser" "Извлечение текста из OWASP"
            }

            internalRulesIngestion = container "Internal Rules Ingestion" "Синхронизация политик из Internal Rules" {
                rulesClient = component "Rules Client" "Загрузка правил"
                htmlParser = component "HTML Parser" "Извлечение текста из страниц"
                qdrantIndexer = component "Qdrant Indexer" "Заливка в векторную БД"
            }

            apiService = container "API Service" "Эндпоинты: запуск аудита, статус, отчёт" {
                startAudit = component "POST /audit/start" "Запуск аудита репозитория"
                getStatus = component "GET /audit/{id}/status" "Статус аудита"
                getReport = component "GET /audit/{id}/report" "Скачать отчёт"
                listAudits = component "GET /audit" "Список аудитов"
            }

            frontendService = container "Frontend Service" "Web UI: дашборд, запуск аудитов" {
                login = component "Login Page" "Редирект на Keycloak"
                dashboard = component "Dashboard" "Список и запуск аудитов"
                oauthCallback = component "OAuth Callback" "Обмен кода на токен"
            }

            indexerService = container "Indexer Service" "Tree-sitter парсер + индексация" {
                gitClone = component "Git Clone" "Клонирование репозитория"
                treeSitter = component "Tree-sitter Parser" "AST-парсинг Python и Go"
                codeChunker = component "Code Chunker" "Разбиение на чанки"
                qdrantIndexer = component "Qdrant Indexer" "Заливка чанков в Qdrant"
            }

            embeddingService = container "Embedding Service" "Генерация эмбеддингов (BAAI/bge-m3)" {
                bgeM3 = component "BAAI/bge-m3 (8080)" "Универсальная модель: код + текст + мультиязычный (1024 dim)"
            }

            auditWorker = container "Audit Worker" "Обработка задач аудита" {
                kafkaConsumer = component "Kafka Consumer" "Чтение из audit.tasks"
                langGraph = component "LangGraph Engine" "DAG из 3 узлов"
                dlqProducer = component "DLQ Producer" "Отправка в audit.dlq"
                generalRetriever = component "General Retriever" "Поиск в OWASP (Qdrant)"
                internalRetriever = component "Internal Retriever" "Поиск в корпоративных политиках"
                analyzer = component "Analyzer" "LLM: сравнение кода с правилами"
                formatter = component "Formatter" "Форматирование в JSON"
                resultWriter = component "Result Writer" "Сохранение результатов в PostgreSQL"
            }

            // ===== AI Inference Layer (Air-gapped) =====
            vllm = container "vLLM Server" "Inference Server с PagedAttention" {
                continuousBatching = component "Continuous Batching" "Оптимизация throughput"
                pagedAttention = component "PagedAttention" "Эффективная работа с KV-кешем"
            }

            qwen7b = container "qwen-coder-7b-instruct" "Анализ кода (4-bit AWQ)" {
                analyze = component "Analyze" "Однопроходный аудит кода"
                structuredOutput = component "Structured Output" "JSON Schema вывод"
            }

            guardrails = container "Guardrails" "Классификатор токсичности/инъекций" {
                toxicityCheck = component "Toxicity Classifier" "Проверка на токсичность"
                injectionCheck = component "Injection Detector" "Обнаружение Prompt Injection"
            }
        }

        // ===== СВЯЗИ =====

        // OWASP → Seeder → Embedding → Qdrant
        owasp -> securerepo.owaspSeeder.seedScript "Правила уязвимостей"
        securerepo.owaspSeeder.htmlParser -> securerepo.owaspSeeder.seedScript "Текст правил"
        securerepo.owaspSeeder.seedScript -> securerepo.embeddingService.bgeM3 "Текст OWASP"
        securerepo.owaspSeeder.seedScript -> securerepo.qdrant.generalPractices "Вектора OWASP"

        // Internal Rules → Ingestion → Embedding → Qdrant
        internalRules -> securerepo.internalRulesIngestion.rulesClient "Страницы политик"
        securerepo.internalRulesIngestion.htmlParser -> securerepo.internalRulesIngestion.qdrantIndexer "Текст политик"
        securerepo.internalRulesIngestion.qdrantIndexer -> securerepo.embeddingService.bgeM3 "Текст политик"
        securerepo.internalRulesIngestion.qdrantIndexer -> securerepo.qdrant.internalPolicies "Вектора политик"

        // Keycloak → API (авторизация)
        keycloak -> securerepo.frontendService.oauthCallback "JWT токены"
        keycloak -> securerepo.frontendService.oauthCallback "OAuth code"

        // User → Frontend
        user -> securerepo.frontendService.login "Вход"
        user -> securerepo.frontendService.dashboard "Просмотр аудитов"
        User -> securerepo.frontendService.dashboard "Запуск аудита"
        user -> securerepo.frontendService.dashboard "Проверка статуса"
        user -> securerepo.frontendService.dashboard "Скачивание отчёта"

        // Frontend → API
        securerepo.frontendService.dashboard -> securerepo.apiService.listAudits "Список аудитов"
        securerepo.frontendService.dashboard -> securerepo.apiService.startAudit "Запуск аудита"
        securerepo.frontendService.dashboard -> securerepo.apiService.getStatus "Статус"
        securerepo.frontendService.dashboard -> securerepo.apiService.getReport "Отчёт"


        // User → API (напрямую)
        // user -> securerepo.apiService.startAudit "Запуск аудита"
        // user -> securerepo.apiService.getStatus "Проверка статуса"
        // user -> securerepo.apiService.getReport "Скачивание отчёта"

        // API → Kafka → Indexer
        securerepo.apiService.startAudit -> securerepo.postgres.audits "Создание записи аудита (status: pending)"
        securerepo.apiService.startAudit -> securerepo.kafka.repoParsed "URL репозитория"

        // Indexer → Kafka (статус indexed)
        securerepo.indexerService.qdrantIndexer -> securerepo.kafka.auditStatus "status: indexed"

        // Kafka → API (обновление статуса в PostgreSQL)
        securerepo.kafka.auditStatus -> securerepo.apiService.getStatus "Чтение статуса"

        // Indexer читает из Kafka, после индексации отправляет задачи на аудит
        securerepo.kafka.repoParsed -> securerepo.indexerService.gitClone "Код для парсинга"
        securerepo.indexerService.qdrantIndexer -> securerepo.kafka.auditTasks "Задачи на аудит"

        // Indexer → Embedding → Qdrant
        securerepo.indexerService.codeChunker -> securerepo.embeddingService.bgeM3 "Чанки кода"
        securerepo.indexerService.qdrantIndexer -> securerepo.embeddingService.bgeM3 "Чанки кода"
        securerepo.indexerService.qdrantIndexer -> securerepo.qdrant.codeRepo "Вектора кода"

        // Kafka → Audit Worker
        securerepo.kafka.auditTasks -> securerepo.auditWorker.kafkaConsumer "Поток задач"
        securerepo.auditWorker.dlqProducer -> securerepo.kafka.auditDlq "Ошибки обработки"

        // Audit Worker → AI Layer
        securerepo.auditWorker.generalRetriever -> securerepo.qdrant.generalPractices "Поиск OWASP"
        securerepo.auditWorker.internalRetriever -> securerepo.qdrant.internalPolicies "Поиск политик"
        securerepo.auditWorker.analyzer -> securerepo.guardrails.toxicityCheck "Проверка входа"
        securerepo.guardrails.toxicityCheck -> securerepo.qwen7b.analyze "Анализ кода"
        securerepo.auditWorker.resultWriter -> securerepo.postgres.auditResults "Сохранение результатов в PostgreSQL"
        securerepo.auditWorker.resultWriter -> securerepo.kafka.auditStatus "status: completed"

        // vLLM → LLM
        securerepo.vllm.continuousBatching -> securerepo.qwen7b.analyze "Инференс"

        // Report → User (через API)
        securerepo.postgres.auditResults -> securerepo.apiService.getReport "Финальный отчёт"
    }

    views {
        systemLandscape "c1_landscape" {
            description "C1 - System Landscape"
            include *
            autoLayout
        }

        container securerepo "c2_containers" {
            description "C2 - Контейнеры SecureRepo"
            include *
            autoLayout
        }

        component securerepo.auditWorker "c3_audit_worker" {
            description "C3 - Audit Worker"
            include *
            autoLayout
        }

        component securerepo.internalRulesIngestion "c3_internal_rules_ingestion" {
            description "C3 - Internal Rules Ingestion"
            include *
            autoLayout
        }

        component securerepo.owaspSeeder "c3_owasp_seeder" {
            description "C3 - OWASP Seeder"
            include *
            autoLayout
        }

        component securerepo.vllm "c3_vllm" {
            description "C3 - vLLM Server"
            include *
            autoLayout
        }

        component securerepo.frontendService "c3_frontend" {
            description "C3 - Frontend Service"
            include *
            autoLayout
        }

        component securerepo.indexerService "c3_indexer" {
            description "C3 - Indexer Service"
            include *
            autoLayout
        }

        styles {
            element "external" {
                background #cccccc
                color #000000
                shape RoundedBox
            }
        }

        theme default
    }
}
