# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System deps for psycopg2, cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r temba && useradd -r -g temba temba

COPY --from=builder /install /usr/local
COPY . .

# Ensure correct ownership
RUN chown -R temba:temba /app

USER temba

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run Alembic migrations then start Uvicorn
CMD ["sh", "-c", "timeout 30 alembic upgrade head; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
