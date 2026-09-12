FROM proxies-docker.pkg.sbercloud.tech/python:3.11-slim

LABEL maintainer="securerepo"
LABEL description="Confluence Ingestion Service"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingestion/ ./ingestion/
COPY main.py .

ENV QDRANT_URL=http://qdrant:6333
ENV EMBEDDING_URL=http://embedding:8080

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
