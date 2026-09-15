FROM python:3.11-slim

LABEL maintainer="securerepo"
LABEL description="API Service"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY main.py migrations.py .

ENV KAFKA_BROKER=kafka:9092
ENV QDRANT_URL=http://qdrant:6333
ENV POSTGRES_URL=postgresql://securerepo:securerepo_pass@postgres:5432/securerepo

EXPOSE 8000

CMD ["python", "main.py"]
