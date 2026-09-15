FROM python:3.11-slim

LABEL maintainer="securerepo"
LABEL description="Audit Worker"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY audit/ ./audit/
COPY main.py .

EXPOSE 8003

CMD ["python", "main.py"]
