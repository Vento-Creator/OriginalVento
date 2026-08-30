FROM python:3.12-slim

# Railway build status check: gcc install step must appear in build log (commit 2026-08-30)
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app

# Build tools for C extensions (TgCrypto) — slim image ships without gcc
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/sessions /app/data/database

CMD ["python", "main.py"]
