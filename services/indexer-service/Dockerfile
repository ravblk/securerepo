FROM proxies-docker.pkg.sbercloud.tech/python:3.11-slim

LABEL maintainer="securerepo"
LABEL description="Indexer Service"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY indexer/ ./indexer/
COPY main.py .

ENV QDRANT_URL=http://qdrant:6333
ENV EMBEDDING_URL=http://embedding:8080
ENV KAFKA_BROKER=kafka:9092

EXPOSE 8002

CMD ["python", "main.py"]
