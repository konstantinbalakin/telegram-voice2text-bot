# ===== Stage 1: Builder =====
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# --- Build deps ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# --- Install Poetry ---
RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app

# --- Copy dependency manifests first for cache efficiency ---
COPY pyproject.toml poetry.lock* ./

# --- Install production dependencies (Poetry 2.x syntax) ---
RUN poetry install --no-root --without dev

# --- Copy application code ---
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# ===== Stage 2: Runtime =====
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- Runtime deps only ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Copy from builder ---
COPY --from=builder /app /app

# --- Non-root user ---
RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "-m", "src.main"]
