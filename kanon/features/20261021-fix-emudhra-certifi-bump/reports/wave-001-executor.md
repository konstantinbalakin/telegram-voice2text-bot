# Wave 001 executor report — 20261021-fix-emudhra-certifi-bump

## Изменённые файлы

- `requirements.txt` строка 19: `certifi==2026.1.4` → `certifi==2026.10.19`
- `Dockerfile`:
  - apt-get install: добавлен пакет `ca-certificates` (первым в списке)
  - новый RUN-шаг (python3-heredoc) сразу после блока корпоративного CA (`COPY .corp-ca-cert.pem` + `RUN update-ca-certificates`) и непосредственно перед `ENV PIP_CERT=...`, до `COPY requirements.txt`

## Реализация шага вырезания (итоговый RUN)

```dockerfile
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
                if seq_n == 3:               # sigalg, issuer, subject
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
```

## Сборка (docker build)

_(заполняется по ходу)_

## RAW stdout тест-контейнера

_(заполняется по ходу)_

## Что НЕ сделано

- git commit/push — запрещено заданием (оркестратор коммитит сам)
- tasks/, kanon/ (кроме reports/wave-001-executor.md), прод-контейнер — не тронуты
