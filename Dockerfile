# ===== Stage 1: Builder =====
FROM python:3.11-slim AS builder

# --- Environment setup ---
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_NO_INTERACTION=1

# --- System dependencies for build ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

# --- Install Poetry + export plugin ---
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION" "poetry-plugin-export"

WORKDIR /app

# --- Copy dependency manifests first (for caching) ---
COPY pyproject.toml poetry.lock* ./

# --- Export prod dependencies to requirements.txt ---
RUN poetry export --without dev -f requirements.txt -o requirements.txt

# --- Copy source code (doesn’t affect cached dependency layers) ---
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# ===== Stage 2: Runtime =====
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- Runtime dependencies (minimal OS packages) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Copy exported requirements and install ---
COPY --from=builder /app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -rf /root/.cache/pip

# --- Copy application files from builder ---
COPY --from=builder /app /app

# --- Create non-root user and prepare dirs ---
RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /home/appuser
USER appuser

# --- Expose optional port for webhook deployments ---
EXPOSE 8080

# --- Healthcheck ---
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# --- Default command ---
CMD ["python", "-m", "src.main"]
