# ===== Stage 1: Builder =====
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_NO_INTERACTION=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

# Только манифесты — чтобы кэшировать резолв
COPY pyproject.toml poetry.lock* ./

# Экспорт prod-зависимостей (Poetry 2.x)
RUN poetry export --without dev -f requirements.txt -o requirements.txt

# Код уже не влияет на слой зависимостей
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# ===== Stage 2: Runtime =====
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Только рантайм-пакеты ОС
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ставим Python-зависимости в финальном образе
COPY --from=builder /app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -rf /root/.cache/pip

# Копируем приложение
COPY --from=builder /app /app

# Non-root и права на тома/кэш
RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /home/appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "-m", "src.main"]
