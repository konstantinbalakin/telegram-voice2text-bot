# Tech Stack

## Languages

| Language | Version | Purpose |
| -------- | ------- | ------- |
| Python   | >= 3.11 | Primary language |

## Frameworks & Libraries

### Core

| Library | Version | Purpose |
| ------- | ------- | ------- |
| python-telegram-bot | >= 22.5 | Telegram Bot API |
| SQLAlchemy[asyncio] | >= 2.0.44 | Async ORM |
| aiosqlite | >= 0.20.0 | SQLite async driver |
| Alembic | >= 1.13 | Database migrations |
| Pydantic | >= 2.10 | Data validation |
| Pydantic Settings | >= 2.6 | Configuration management |
| httpx | >= 0.28 | Async HTTP client |
| Telethon | >= 1.42.0 | Large file downloads (up to 2 GB) |
| WeasyPrint | >= 62.3 | PDF generation |
| pydub | >= 0.25.1 | Audio processing |
| tenacity | >= 9.0.0 | Retry logic |

### Optional

| Library | Version | Purpose |
| ------- | ------- | ------- |
| openai | >= 1.50.0 | OpenAI Whisper API |
| faster-whisper | >= 1.2.1 | Local Whisper transcription |
| cryptg | >= 0.4.0 | Telethon speedup |

### Dev Dependencies

| Tool | Version | Purpose |
| ---- | ------- | ------- |
| pytest | >= 8.3 | Testing framework |
| pytest-asyncio | >= 0.24 | Async test support |
| pytest-cov | >= 6.0 | Coverage reporting |
| black | >= 24.10 | Code formatting |
| ruff | >= 0.8 | Linting |
| mypy | >= 1.13 | Static type checking |
| bandit | >= 1.9.2 | Security linting |
| pre-commit | >= 4.0 | Git hooks |

## Database

| Database | Driver | ORM | Migrations |
| -------- | ------ | --- | ---------- |
| SQLite | aiosqlite | SQLAlchemy 2.0 (async) | Alembic |

## Infrastructure

| Component | Technology |
| --------- | ---------- |
| Containerization | Docker + docker-compose |
| Deployment | VPS (self-hosted) |
| CI/CD | GitHub Actions |
| Package Manager | uv |

## External APIs

| Service | Purpose |
| ------- | ------- |
| OpenAI Whisper API | Speech-to-text transcription |
| DeepSeek V3 | Text processing (structuring, summarization) |
| Telegram Bot API | User interaction |
