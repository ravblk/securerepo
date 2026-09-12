FROM proxies-docker.pkg.sbercloud.tech/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY seeder/ ./seeder/
COPY main.py .

ENV QDRANT_URL=http://qdrant:6333
ENV EMBEDDING_URL=http://embedding:8080

CMD ["python", "main.py"]
