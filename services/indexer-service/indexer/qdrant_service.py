import logging
import uuid
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .config import settings
from .models import CodeChunk, RepoMessage

logger = logging.getLogger(__name__)


class QdrantService:
    def __init__(self, url: str = settings.qdrant_url) -> None:
        self._client = QdrantClient(url=url)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                existing = {c.name for c in self._client.get_collections().collections}
                if settings.collection_name not in existing:
                    self._client.create_collection(
                        collection_name=settings.collection_name,
                        vectors_config=VectorParams(
                            size=settings.embedding_size,
                            distance=Distance.COSINE,
                        ),
                    )
                    logger.info("Created Qdrant collection '%s'", settings.collection_name)
                else:
                    logger.info("Qdrant collection '%s' already exists", settings.collection_name)

                logger.info("Qdrant connection verified successfully")
                return  # Success, exit the retry loop

            except Exception as e:
                connection_error = "Connection refused" in str(e) or "111" in str(e)

                if attempt < max_retries - 1 and connection_error:
                    logger.warning(
                        f"Qdrant connection attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    import time
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to connect to Qdrant after {max_retries} attempts: {e}")
                    logger.warning("Service will continue but Qdrant operations may fail.")
                    return  # Don't raise exception, service will continue

    def upsert_chunks(
        self,
        chunks: Iterable[tuple[CodeChunk, list[float]]],
        message: RepoMessage,
    ) -> list[PointStruct]:
        points: list[PointStruct] = []
        for chunk, embedding in chunks:
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "chunk_id": chunk.id,
                    "file_path": chunk.file_path,
                    "function_name": chunk.function_name,
                    "class_name": chunk.class_name,
                    "code": chunk.code,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "audit_id": message.audit_id,
                    "lang": message.lang,
                },
            ))
        if points:
            self._client.upsert(
                collection_name=settings.collection_name,
                points=points,
            )
        return points
