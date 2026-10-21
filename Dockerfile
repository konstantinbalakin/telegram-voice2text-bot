FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
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

# eMudhra CA compromise (Oct 2026): drop the compromised emSign ECC Root CA - G3
# Runs AFTER update-ca-certificates (which regenerates the bundle) and BEFORE the
# PIP_CERT/SSL_CERT_FILE ENV + requirements COPY, so the pip layer stays cached.
# python3 (stdlib only) mini ASN.1/TLV walk: match the certificate SUBJECT field,
# not the whole DER. No-op when the root is absent.
RUN <<'PYEOF'
#!/usr/bin/env python3
import base64
import pathlib
import re

BUNDLE = pathlib.Path("/etc/ssl/certs/ca-certificates.crt")
NEEDLE = "emSign ECC Root CA - G3"
PEM_RE = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)
STR_TAGS = (0x0C, 0x13, 0x14, 0x16, 0x1A, 0x1B, 0x1E)


def tlv(buf, off):
    tag = buf[off]
    off += 1
    ln = buf[off]
    off += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[off:off + n], "big")
        off += n
    return tag, off, off + ln


def collect_strings(buf, s, e, out):
    while s < e:
        tag, cs, ce = tlv(buf, s)
        if tag & 0x20:
            collect_strings(buf, cs, ce, out)
        elif tag in STR_TAGS:
            out.append(buf[cs:ce].decode("utf-8", "replace"))
        s = ce


def subject_matches(der):
    try:
        _, cs, _ = tlv(der, 0)          # Certificate SEQUENCE
        _, s2, e2 = tlv(der, cs)        # TBSCertificate SEQUENCE
        s = s2
        seq_n = 0
        while s < e2:
            tag, cs3, ce3 = tlv(der, s)
            if tag == 0xA0 or tag == 0x02:   # version [0] / serialNumber
                s = ce3
                continue
            if tag == 0x30:
                seq_n += 1
                if seq_n == 4:               # sigalg(1), issuer(2), validity(3), subject(4)
                    out = []
                    collect_strings(der, cs3, ce3, out)
                    return NEEDLE in " ".join(out)
            s = ce3
    except (IndexError, ValueError):
        pass
    return False


data = BUNDLE.read_text() if BUNDLE.exists() else ""
removed = 0
kept = []
for m in PEM_RE.finditer(data):
    block = m.group(0)
    body = "".join(block.strip().splitlines()[1:-1])
    if subject_matches(base64.b64decode(body)):
        removed += 1
    else:
        kept.append(block + "\n")

if removed:
    BUNDLE.write_text("".join(kept))
print(f"emSign ECC Root CA - G3 blocks removed: {removed}")
PYEOF

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
