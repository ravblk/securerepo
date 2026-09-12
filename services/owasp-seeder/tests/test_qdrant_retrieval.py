"""
Тесты Retrieval правил безопасности для уязвимого кода

Проверка работы retrieval системы для поиска ПРАВИЛ БЕЗОПАСНОСТИ для уязвимого кода:

1) НЕ загружает данные в Qdrant (они уже там в general_best_practices)
2) Читает уязвимый код из fixtures/vulnerable_code/ (6 файлов: 4 Python + 2 Go)
3) Генерирует эмбеддинг для каждого файла уязвимого кода
4) Ищет АДЕКВАТНЫЕ ПРАВИЛА БЕЗОПАСНОСТИ в general_best_practices
5) Фильтрует результаты - только правила безопасности (не код уязвимостей)
6) Сохраняет входной код и найденные правила в отдельные файлы
7) Генерирует отчет о качестве поиска правил безопасности

ЦЕЛЬ: Проверить что система может найти правильные правила безопасности для каждой уязвимости
"""

import json
import os
import sys
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("qdrant_retrieval_tests")


@dataclass
class RetrievalTestConfig:
    """Конфигурация тестов retrieval."""
    qdrant_url: str
    collection_name: str
    embedding_url: str
    embedding_timeout: int
    results_dir: str


class QdrantRetrievalTester:
    """Тестер retrieval из существующей Qdrant коллекции."""

    def __init__(self, config: RetrievalTestConfig):
        self.config = config
        self.qdrant_client = None

        # Создаем директорию для результатов
        os.makedirs(self.config.results_dir, exist_ok=True)
        log.info(f"Директория для результатов: {self.config.results_dir}")

    def test_qdrant_connection(self) -> Tuple[bool, str]:
        """Проверяем подключение к Qdrant."""
        try:
            self.qdrant_client = QdrantClient(url=self.config.qdrant_url)

            # Проверяем что наша коллекция существует
            collections = self.qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.config.collection_name not in collection_names:
                return False, f"Коллекция {self.config.collection_name} не существует. Доступные: {collection_names}"

            # Получаем информацию о коллекции
            collection_info = self.qdrant_client.get_collection(self.config.collection_name)
            return True, f"Qdrant подключен, коллекция {self.config.collection_name} содержит {collection_info.points_count} точек"

        except Exception as e:
            return False, f"Не удалось подключиться к Qdrant: {str(e)}"

    def test_embedding_service(self) -> Tuple[bool, str]:
        """Проверяем embedding сервис."""
        try:
            test_text = "SQL injection security vulnerability test"

            response = requests.post(
                f"{self.config.embedding_url}/embed",
                json={"inputs": test_text},
                timeout=self.config.embedding_timeout,
            )
            response.raise_for_status()

            result = response.json()
            embeddings = result.get("embeddings", [])

            if embeddings and len(embeddings) > 0:
                embedding_length = len(embeddings[0])
                return True, f"Embedding сервис работает, длина вектора: {embedding_length}"
            else:
                return False, "Embedding сервис вернул пустой результат"

        except Exception as e:
            return False, f"Ошибка embedding сервиса: {str(e)}"

    def get_embedding(self, text: str) -> List[float]:
        """Получаем embedding для текста."""
        try:
            response = requests.post(
                f"{self.config.embedding_url}/embed",
                json={"inputs": text},
                timeout=self.config.embedding_timeout,
            )
            response.raise_for_status()

            result = response.json()
            embeddings = result.get("embeddings", [])

            # Embedding сервис возвращает [[...]], нам нужен первый элемент
            return embeddings[0] if embeddings and len(embeddings) > 0 else []

        except Exception as e:
            log.error(f"Ошибка получения embedding: {e}")
            return []

    def save_input_request(self, query_id: str, query_text: str) -> str:
        """Сохраняет входной запрос для тестирования в отдельный файл."""
        input_filename = f"{query_id}_input.txt"
        input_filepath = os.path.join(self.config.results_dir, input_filename)

        try:
            with open(input_filepath, "w", encoding="utf-8") as f:
                # Добавляем заголовок с информацией
                header = f"""
# Retrieval Request: {query_id}
# Query Text:
# Generated for Qdrant retrieval testing
# Timestamp: {datetime.now().isoformat()}

"""
                f.write(header + "\n" + query_text)

            log.info(f"Входной запрос сохранен: {input_filepath}")
            return input_filepath
        except Exception as e:
            log.error(f"Ошибка сохранения входного запроса: {e}")
            return ""

    def search_qdrant(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Выполняет retrieval поиск в существующей Qdrant коллекции."""
        if not self.qdrant_client:
            raise Exception("Qdrant клиент не инициализирован")

        try:
            log.info(f"Поиск в Qdrant коллекции: {self.config.collection_name}")

            # Получаем embedding для запроса
            query_embedding = self.get_embedding(query_text)

            if not query_embedding:
                return []

            # Выполняем retrieval через scroll + manual similarity
            points_data = self.qdrant_client.scroll(
                collection_name=self.config.collection_name,
                limit=200,  # Получаем 200 точек для поиска
                with_payload=True,
                with_vectors=True
            )

            # Вычисляем косинусное сходство для каждой точки
            scored_results = []

            # ФИЛЬТРУЕМ ТОЛЬКО ПРАВИЛА БЕЗОПАСНОСТИ (верска код уязвимостей)
            security_rules_points = []
            for point in points_data[0]:
                # Пропускаем точки с полями кода уязвимостей (vulnerability_type, sample_id, code)
                payload = point.payload
                if any(key in payload for key in ["vulnerability_type", "sample_id", "code"]):
                    continue
                # Пропускаем точки без базовых полей правил безопасности (title, source)
                if not all(key in payload for key in ["title", "source"]):
                    continue

                security_rules_points.append(point)

            log.info(f"Отфильтровано {len(points_data[0])} -> {len(security_rules_points)} правил безопасности")

            if security_rules_points:
                log.info(f"Структура payload первой точки: {security_rules_points[0].payload.keys()}")
                log.info(f"Пример правила: {str(security_rules_points[0].payload)[:500]}")

            for point in security_rules_points:
                try:
                    # Получаем вектор точки
                    point_vector = point.vector

                    # Вычисляем косинусное сходство
                    similarity = self.compute_cosine_similarity(query_embedding, point_vector)

                    # Получаем текст из разных полей
                    text_content = point.payload.get("text", "")
                    if not text_content:
                        text_content = point.payload.get("content", "")
                    if not text_content:
                        text_content = point.payload.get("description", "")

                    scored_results.append({
                        "score": similarity,
                        "title": point.payload.get("title", f"Point {point.id}"),
                        "text": text_content,
                        "url": point.payload.get("url", ""),
                        "language": point.payload.get("lang", ""),
                        "source": point.payload.get("source", ""),
                        "point_id": str(point.id),
                        "ingested_at": point.payload.get("ingested_at", ""),
                        "raw_payload": str(point.payload)
                    })
                except Exception as e:
                    # Пропускаем точки с ошибками
                    continue

            # Сортируем по score и берем top limit
            scored_results.sort(key=lambda x: x["score"], reverse=True)

            log.info(f"Отфильтровано {len(scored_results)} правил безопасности из {len(points_data[0])} точек")
            if scored_results:
                log.info(f"Топ-3 правила безопасности:")
                for i, result in enumerate(scored_results[:3]):
                    text_len = len(result.get("text", ""))
                    log.info(f"  #{i+1}: {result['title'][:50]}... (score={result['score']:.3f}, text_len={text_len}, source={result['source']})")
            else:
                log.warning("Не найдено правил безопасности!")

            # Форматируем результаты
            results = []
            for i, item in enumerate(scored_results[:limit]):
                results.append({
                    "rank": i + 1,
                    "score": item["score"],
                    "title": item["title"],
                    "text": item["text"],  # Полный текст
                    "text_preview": item["text"][:200] + "..." if len(item["text"]) > 200 else item["text"],  # Для превью
                    "url": item["url"],
                    "language": item["language"],
                    "source": item["source"],
                    "point_id": item["point_id"]
                })

            return results

        except Exception as e:
            log.error(f"Ошибка при retrieval в Qdrant: {e}")
            import traceback
            traceback.print_exc()
            return []

    def compute_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Вычисляет косинусное сходство между двумя векторами."""
        try:
            import math

            # Убеждаемся что векторы одной длины
            if len(vec1) != len(vec2):
                return 0.0

            # Dot product
            dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))

            # Magnitudes
            magnitude1 = math.sqrt(sum(v1 ** 2 for v1 in vec1))
            magnitude2 = math.sqrt(sum(v2 ** 2 for v2 in vec2))

            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0

            return dot_product / (magnitude1 * magnitude2)

        except Exception:
            return 0.0

    def save_retrieved_results(self, query_id: str, retrieved_results: List[Dict[str, Any]]) -> str:
        """Сохраняет результаты retrieval из базы данных в отдельный файл."""
        output_filename = f"{query_id}_retrieved.json"
        output_filepath = os.path.join(self.config.results_dir, output_filename)

        try:
            output_data = {
                "query_id": query_id,
                "timestamp": datetime.now().isoformat(),
                "retrieved_count": len(retrieved_results),
                "results": retrieved_results,
                "top_scores": [r["score"] for r in retrieved_results],
                "avg_score": sum(r["score"] for r in retrieved_results) / len(retrieved_results) if retrieved_results else 0.0
            }

            with open(output_filepath, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            log.info(f"Результаты retrieval сохранены: {output_filepath} ({len(retrieved_results)} результатов)")
            return output_filepath
        except Exception as e:
            log.error(f"Ошибка сохранения результатов retrieval: {e}")
            return ""

    def load_vulnerable_code(self, file_path: str) -> str:
        """Читает содержимое файла уязвимого кода."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            log.error(f"Ошибка чтения файла {file_path}: {e}")
            return ""

    def save_retrieved_rules_text(self, query_id: str, retrieved_results: List[Dict[str, Any]]) -> str:
        """Сохраняет текст найденных правил в отдельный файл для удобного чтения."""
        text_filename = f"{query_id}_rules.txt"
        text_filepath = os.path.join(self.config.results_dir, text_filename)

        try:
            text_content = f"""# Retrieved Rules for: {query_id}
# Generated at: {datetime.now().isoformat()}
# Total rules found: {len(retrieved_results)}

"""
            for i, result in enumerate(retrieved_results, 1):
                text_content += f"""
{'='*80}
# Rule #{i}: {result['title']}
{'='*80}

Score: {result['score']:.4f}
Rank: {result['rank']}
Language: {result['language']}
Source: {result['source']}
URL: {result['url']}
Point ID: {result['point_id']}

---

## Rule Content:

{result.get('text', '')}

---

"""

            with open(text_filepath, "w", encoding="utf-8") as f:
                f.write(text_content)

            log.info(f"Текст найденных правил сохранен: {text_filepath}")
            return text_filepath
        except Exception as e:
            log.error(f"Ошибка сохранения текста правил: {e}")
            return ""

    def save_retrieval_report(self, query_id: str, query_text: str, retrieved_results: List[Dict[str, Any]]) -> str:
        """Сохраняет детальный отчет retrieval."""
        report_filename = f"{query_id}_retrieval_report.md"
        report_filepath = os.path.join(self.config.results_dir, report_filename)

        try:
            report_content = f"""# Retrieval Report: {query_id}

**Timestamp:** {datetime.now().isoformat()}

## 🔍 Query Information
- **Query ID:** {query_id}
- **Query Text:** {query_text}
- **Results Retrieved:** {len(retrieved_results)}

## 📊 Results

"""

            if retrieved_results:
                # Добавляем найденные результаты
                for i, result in enumerate(retrieved_results, 1):
                    report_content += f"""
### #{i}. {result['title']}
- **Score:** {result['score']:.4f}
- **Rank:** {result['rank']}
- **Language:** {result['language']}
- **Source:** {result['source']}
- **URL:** {result['url']}
- **Text Preview:** {result['text_preview'][:100]}...
- **Point ID:** {result['point_id']}
"""
            else:
                report_content += "\n**No results retrieved**\n"

            report_content += f"""

## 📈 Metrics
- **Top Score:** {max([r['score'] for r in retrieved_results]) if retrieved_results else 0.0:.4f}
- **Average Score:** {sum([r['score'] for r in retrieved_results]) / len(retrieved_results) if retrieved_results else 0.0:.4f}
- **Results Count:** {len(retrieved_results)}
"""

            with open(report_filepath, "w", encoding="utf-8") as f:
                f.write(report_content)

            log.info(f"Отчет retrieval сохранен: {report_filepath}")
            return report_filepath
        except Exception as e:
            log.error(f"Ошибка сохранения отчета retrieval: {e}")
            return ""

    def test_retrieval(self) -> List[Dict[str, Any]]:
        """ проверяет retrieval для различных security запросов из уязвимого кода."""

        # Пути к файлам уязвимого кода
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "vulnerable_code")

        test_queries = [
            {
                "query_id": "python_sql_injection",
                "code_file": os.path.join(fixtures_dir, "python", "sql_injection.py"),
                "expected_keywords": ["SQL", "injection", "Python", "sqlite3", "string formatting", "parameterized"],
                "min_results": 2
            },
            {
                "query_id": "python_command_injection",
                "code_file": os.path.join(fixtures_dir, "python", "command_injection.py"),
                "expected_keywords": ["command", "injection", "subprocess", "shell", "os.system", "Python"],
                "min_results": 2
            },
            {
                "query_id": "python_xss",
                "code_file": os.path.join(fixtures_dir, "python", "xss_vulnerability.py"),
                "expected_keywords": ["XSS", "injection", "Flask", "escape", "template", "render", "Python"],
                "min_results": 2
            },
            {
                "query_id": "python_hardcoded_secrets",
                "code_file": os.path.join(fixtures_dir, "python", "hardcoded_secrets.py"),
                "expected_keywords": ["hardcoded", "secrets", "password", "API", "keys", "credentials", "environment variables", "Python"],
                "min_results": 2
            },
            {
                "query_id": "go_sql_injection",
                "code_file": os.path.join(fixtures_dir, "go", "sql_injection.go"),
                "expected_keywords": ["SQL", "injection", "Go", "fmt.Sprintf", "string interpolation", "database"],
                "min_results": 2
            },
            {
                "query_id": "go_command_injection",
                "code_file": os.path.join(fixtures_dir, "go", "command_injection.go"),
                "expected_keywords": ["command", "injection", "Go", "exec.Command", "shell", "os/exec"],
                "min_results": 2
            }
        ]

        retrieval_results = []

        for query in test_queries:
            log.info(f"Выполняем retrieval: {query['query_id']}: {query['code_file']}")

            try:
                # Читаем код из файла уязвимого кода
                code_content = self.load_vulnerable_code(query['code_file'])
                if not code_content:
                    log.error(f"Не удалось загрузить код из {query['code_file']}")
                    continue

                log.info(f"Загружено {len(code_content)} символов из кода")

                # Сохраняем входной запрос (код уязвимости)
                input_file = self.save_input_request(query['query_id'], code_content)

                # Выполняем retrieval из Qdrant, используя код уязвимости как запрос
                retrieved_results_local = self.search_qdrant(code_content, limit=5)

                # Сохраняем полученные результаты
                results_file = self.save_retrieved_results(query['query_id'], retrieved_results_local)

                # Сохраняем текст найденных правил для удобного чтения
                rules_text_file = self.save_retrieved_rules_text(query['query_id'], retrieved_results_local)

                # Сохраняем детальный отчет с контекстом code_content
                report_file = self.save_retrieval_report(query['query_id'], f"Код из файла: {query['code_file']}\n\n{code_content[:500]}...", retrieved_results_local)

                # Анализируем результаты
                best_score = max([r["score"] for r in retrieved_results_local]) if retrieved_results_local else 0.0
                avg_score = sum([r["score"] for r in retrieved_results_local]) / len(retrieved_results_local) if retrieved_results_local else 0.0

                # Проверяем наличие ожидаемых keywords
                keywords_found = []
                for result in retrieved_results_local:
                    result_text = (result["title"] + " " + result["text_preview"]).lower()
                    found_keywords = [kw for kw in query["expected_keywords"] if kw.lower() in result_text]
                    if found_keywords:
                        keywords_found.append({
                            "result_rank": result["rank"],
                            "found_keywords": found_keywords,
                            "title": result["title"][:50]
                        })

                passed_requirements = len(retrieved_results_local) >= query["min_results"] and best_score > 0.1

                retrieval_results.append({
                    "query_id": query["query_id"],
                    "code_file": query['code_file'],
                    "results_found": len(retrieved_results_local),
                    "min_required": query["min_results"],
                    "best_score": best_score,
                    "avg_score": avg_score,
                    "keywords_found": len(keywords_found),
                    "expected_keywords": query["expected_keywords"],
                    "input_file": input_file,
                    "results_file": results_file,
                    "rules_text_file": rules_text_file,
                    "report_file": report_file,
                    "pass_fail": passed_requirements
                })

                log.info(f"{query['query_id']}: найдено {len(retrieved_results_local)} результатов, лучший score: {best_score:.4f}, прошел: {passed_requirements}")

            except Exception as e:
                log.error(f"Ошибка при retrieval запросе {query['query_id']}: {e}")
                import traceback
                traceback.print_exc()
                retrieval_results.append({
                    "query_id": query["query_id"],
                    "code_file": query['code_file'],
                    "error": str(e),
                    "pass_fail": False
                })

        return retrieval_results


def load_test_config() -> RetrievalTestConfig:
    """Загружает конфигурацию для тестов."""
    # Попробуем найти .env файл
    env_locations = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
        Path.cwd() / ".env"
    ]

    for env_path in env_locations:
        if env_path.exists():
            load_dotenv(env_path)
            log.info(f"Загружаем конфигурацию из: {env_path}")
            break
    else:
        log.warning("Файл .env не найден, используем настройки по умолчанию")

    return RetrievalTestConfig(
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        collection_name=os.getenv("QDRANT_COLLECTION", "general_best_practices"),
        embedding_url=os.getenv("EMBEDDING_URL", "http://localhost:8080"),
        embedding_timeout=int(os.getenv("EMBEDDING_TIMEOUT", "120")),
        results_dir=os.path.join(os.path.dirname(__file__), "retrieval_results")
    )


def generate_retrieval_test_report(retrieval_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Генерирует отчет тестирования retrieval."""

    if not retrieval_results:
        return {
            "summary": {
                "total_queries": 0,
                "successful_queries": 0,
                "avg_score": 0.0,
                "overall_status": "no_results"
            },
            "detailed_results": {}
        }

    # Основная статистика
    total_queries = len(retrieval_results)
    successful_queries = len([r for r in retrieval_results if r.get("pass_fail")])
    queries_with_results = [r for r in retrieval_results if r.get("results_found", 0) > 0]

    avg_score = 0.0
    if queries_with_results:
        scores = [r["avg_score"] for r in queries_with_results]
        avg_score = sum(scores) / len(scores)

    # Quality gates
    quality_gates_results = {
        "successful_queries_rate": successful_queries / total_queries if total_queries > 0 else 0,
        "avg_retrieval_score": avg_score,
        "total_queries": total_queries,
        "successful_queries": successful_queries
    }

    overall_status = "passed" if successful_queries >= total_queries * 0.8 else "failed"

    # Добавляем информацию о файлах кода
    detailed_results = {}
    for r in retrieval_results:
        detailed_results[r["query_id"]] = {
            **r,
            "code_file_short": os.path.basename(r.get("code_file", "N/A")) if "code_file" in r else "N/A"
        }

    return {
        "summary": {
            "total_queries": total_queries,
            "successful_queries": successful_queries,
            "success_rate": successful_queries / total_queries if total_queries > 0 else 0,
            "avg_score": round(avg_score, 4),
            "overall_status": overall_status
        },
        "quality_gates": quality_gates_results,
        "detailed_results": detailed_results
    }


def print_retrieval_test_report(report: Dict[str, Any]):
    """Выводит отчет тестирования retrieval."""

    print("\n" + "="*70)
    print(f"🔍 QDRANT RETRIEVAL TESTING")
    print("="*70)

    summary = report["summary"]
    print(f"\n📊 ОБЩАЯ СТАТИСТИКА:")
    print(f"   Всего запросов: {summary['total_queries']}")
    print(f"   Успешных запросов: {summary['successful_queries']}")
    print(f"   Success Rate: {summary['success_rate']*100:.1f}%")
    print(f"   Средний score поиска: {summary['avg_score']:.4f}")
    print(f"   Статус теста: {'✅ PASSED' if summary['overall_status'] == 'passed' else '❌ FAILED'}")

    # Output file locations
    print(f"\n📁 ФАЙЛЫ РЕЗУЛЬТАТОВ:")
    if "detailed_results" in report:
        detailed = report["detailed_results"]
        for query_id, result in detailed.items():
            if "input_file" in result:
                print(f"   📄 {query_id}:")
                print(f"      Input (vulnerable code): {result['input_file']}")
            if "results_file" in result:
                print(f"      Retrieved (JSON): {result['results_file']}")
            if "rules_text_file" in result:
                print(f"      Rules (readable text): {result['rules_text_file']}")
            if "report_file" in result:
                print(f"      Report (Markdown): {result['report_file']}")

    print(f"\n📋 ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ ЗАПРОСОВ:")
    if "detailed_results" in report:
        detailed = report["detailed_results"]

        for query_id, result in detailed.items():
            if "error" in result:
                print(f"\n❌ [{query_id}] ОШИБКА:")
                print(f"   Code File: {result.get('code_file', 'N/A')}")
                print(f"   Error: {result['error']}")
            else:
                status_icon = "✅" if result.get("pass_fail") else "❌"
                print(f"\n{status_icon} [{query_id}] Result:")
                print(f"   Code File: {result.get('code_file', 'N/A')}")
                print(f"   Retrieved: {result.get('results_found', 0)} results (min: {result.get('min_required', 'N/A')})")
                print(f"   Best Score: {result.get('best_score', 0):.4f}")
                print(f"   Avg Score: {result.get('avg_score', 0):.4f}")
                print(f"   Keywords Found: {result.get('keywords_found', 0)}/{len(result.get('expected_keywords', []))}")
                print(f"   Pass/Fail: {'✅ PASSED' if result.get('pass_fail') else '❌ FAILED'}")


def main() -> int:
    """Основная функция тестирования retrieval из Qdrant."""

    print("🔍 QDRANT RETRIEVAL TESTING")
    print("="*70)

    # Загрузка конфигурации
    config = load_test_config()

    print(f"Конфигурация:")
    print(f"   Qdrant URL: {config.qdrant_url}")
    print(f"   Collection: {config.collection_name}")
    print(f"   Embedding URL: {config.embedding_url}")
    print(f"   Results Directory: {config.results_dir}")

    try:
        # Создаем тестер
        tester = QdrantRetrievalTester(config)

        # Тест 1: Проверка подключения к Qdrant
        print(f"\n📡 Проверка подключения к Qdrant...")
        connected, message = tester.test_qdrant_connection()
        print(f"   {message}")

        if not connected:
            return 1

        # Тест 2: Проверка embedding сервиса
        print(f"\n🧠 Проверка embedding сервиса...")
        embedding_ok, embedding_msg = tester.test_embedding_service()
        print(f"   {embedding_msg}")

        if not embedding_ok:
            print(f"   ⚠️  Embedding сервис недоступен, но продолжаем тесты...")

        # Тест 3: Проверка retrieval запросов
        print(f"\n🔍 Тестирование retrieval запросов...")
        retrieval_results = tester.test_retrieval()

        # Генерация отчета
        print(f"\n📊 Генерация отчета...")
        report = generate_retrieval_test_report(retrieval_results)

        # Вывод отчета
        print_retrieval_test_report(report)

        # Сохранение основных результатов
        result_json_path = os.path.join(config.results_dir, "retrieval_test_summary.json")
        with open(result_json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n📄 Итоговые результаты сохранены в: {result_json_path}")

        # Проверка quality gates
        success_rate = report["summary"]["success_rate"]

        if success_rate >= 0.8:  # 80% success rate threshold
            print(f"\n🎉 RETRIEVAL TESTING PASSED! Success rate: {success_rate*100:.1f}%")
            return 0
        else:
            print(f"\n❌ RETRIEVAL TESTING FAILED! Success rate: {success_rate*100:.1f}% (требуется ≥80%)")
            return 1

    except Exception as e:
        log.error(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())