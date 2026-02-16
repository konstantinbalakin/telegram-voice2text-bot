FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Optional: corporate CA certificate for SSL proxy environments
# File is empty by default (no-op). Populated by Makefile when CORP_CA_CERT_PATH is set.
COPY .corp-ca-cert.pem /tmp/.corp-ca-cert.pem
RUN if [ -s /tmp/.corp-ca-cert.pem ]; then \
      cp /tmp/.corp-ca-cert.pem /usr/local/share/ca-certificates/corp-ca.crt && \
      update-ca-certificates && \
      echo "Corporate CA certificate installed"; \
    fi && rm -f /tmp/.corp-ca-cert.pem
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Copy requirements for Docker (base + faster-whisper)
COPY requirements.txt requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt \
 && find /usr/local/lib/python3.11 -type d -name "__pycache__" -exec rm -rf {} + \
 && find /usr/local/lib/python3.11 -type d -name "tests" -exec rm -rf {} +

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY prompts/ ./prompts/

RUN useradd -m appuser && \
    mkdir -p /app/data /app/logs /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /home/appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-m", "src.health_check"]

CMD ["python", "-m", "src.main"]
