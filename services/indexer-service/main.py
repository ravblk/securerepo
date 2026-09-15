import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from indexer.config import settings
from indexer.embedding_service import get_embedding
from indexer.kafka_service import KafkaService
from indexer.models import RepoMessage
from indexer.qdrant_service import QdrantService
from indexer.repo_service import clone_repo, collect_chunks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("indexer")

kafka_service = KafkaService()
qdrant_service: Optional[QdrantService] = None


def process_repo(message: RepoMessage) -> None:
    logger.info("Processing repo: %s (%s)", message.repo_url, message.lang)

    try:
        logger.info(f"Cloning repo: {message.repo_url}")
        repo_path = clone_repo(message.repo_url, message.branch, message.token)
        logger.info(f"Repo cloned successfully to: {repo_path}")
    except Exception:
        logger.exception("Error cloning repo")
        kafka_service.send_status(message.audit_id, "failed", error="clone failed")
        return

    logger.info(f"Collecting code chunks from {repo_path}")
    chunks = collect_chunks(repo_path)
    logger.info("Found %d code chunks", len(chunks))

    if not chunks:
        logger.warning("No code chunks found, skipping embedding")
        kafka_service.send_status(message.audit_id, "indexed", total_chunks=0)
        return

    logger.info(f"Starting embedding process for {len(chunks)} chunks")
    embedded: list[tuple] = []
    for idx, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {idx + 1}/{len(chunks)}: {chunk.file_path}")
        embedding = get_embedding(chunk.code)
        if embedding:
            embedded.append((chunk, embedding))
            logger.info(f"✓ Got embedding for chunk {idx + 1}")
        else:
            logger.warning(f"✗ Failed to get embedding for chunk {idx + 1}")

    logger.info(f"Embedding complete: {len(embedded)}/{len(chunks)} chunks embedded")

    points = []
    if embedded:
        try:
            logger.info(f"Upserting {len(embedded)} points to Qdrant")
            points = qdrant_service.upsert_chunks(embedded, message)
            logger.info("Indexed %d chunks to Qdrant", len(points))
        except Exception:
            logger.exception("Error upserting to Qdrant")
    else:
        logger.warning("No chunks were successfully embedded")

    logger.info(f"Sending audit status for {message.audit_id}")
    kafka_service.send_status(
        message.audit_id, "indexed", total_chunks=len(points),
    )
    kafka_service.send_audit_tasks(message.audit_id, points)
    logger.info(f"Completed processing for {message.audit_id}")


def on_kafka_message(kafka_message) -> None:
    logger.info(
        "Received message: topic=%s, partition=%s, offset=%s",
        kafka_message.topic, kafka_message.partition, kafka_message.offset,
    )
    try:
        repo_message = RepoMessage(**kafka_message.value)
        logger.info(
            "Processing message for repo: %s, audit_id: %s",
            repo_message.repo_url, repo_message.audit_id,
        )

        import time
        start_time = time.time()

        process_repo(repo_message)

        duration = time.time() - start_time
        logger.info(f"Completed indexing for audit %s in {duration:.2f}s", repo_message.audit_id)
    except Exception:
        logger.exception("Error processing repo message")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global qdrant_service
    qdrant_service = QdrantService()
    kafka_service.init_producer()

    consumer_thread = threading.Thread(
        target=kafka_service.consume,
        args=(settings.repo_parsed_topic, on_kafka_message),
        daemon=True,
    )
    consumer_thread.start()
    logger.info("Indexer started")
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/")
def root():
    return {
        "service": "indexer",
        "kafka_topic": settings.repo_parsed_topic,
        "storage": f"Qdrant ({settings.collection_name})",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")
