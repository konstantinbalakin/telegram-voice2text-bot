FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements for Docker (base + faster-whisper)
COPY requirements-docker.txt requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt \
 && find /usr/local/lib/python3.11 -type d -name "__pycache__" -exec rm -rf {} + \
 && find /usr/local/lib/python3.11 -type d -name "tests" -exec rm -rf {} +

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /home/appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "-m", "src.main"]
