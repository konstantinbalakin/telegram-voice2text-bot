# Technical Context: Telegram Voice Bot v2

## Technology Stack

**Current Status**: ✅ Selected and approved (2025-10-12)

## Core Technologies (DECIDED)

### Programming Language: **Python 3.11+**

**Decision Rationale**:
- ✅ Excellent Whisper integration (native Python library)
- ✅ Mature Telegram bot ecosystem
- ✅ Strong async support (asyncio)
- ✅ Rich testing and tooling ecosystem
- ✅ Best choice for AI/ML workloads

**Version**: Python 3.11 or 3.12 (3.13+ compatible)

### Telegram Bot Framework: **python-telegram-bot v22.5**

**Selected**: `python-telegram-bot` v22.5 (latest, September 2025)

**Decision Rationale**:
- ✅ Most mature Python Telegram library
- ✅ Excellent async support
- ✅ Active maintenance
- ✅ Comprehensive documentation
- ✅ Supports both polling and webhook modes

**Alternatives Considered**:
- aiogram: Good, but python-telegram-bot more established
- pytelegrambotapi: Synchronous, not suitable for our async architecture

### Voice Processing: **faster-whisper v1.2.0**

**Selected**: `faster-whisper` v1.2.0 (August 2025)

**Critical Decision**:
- ✅ **4x faster** than openai-whisper
- ✅ **75% less memory** usage (int8 quantization)
- ✅ Same accuracy as original Whisper
- ✅ No ffmpeg dependency (uses PyAV)
- ✅ CPU-optimized with CTranslate2
- ✅ GPU support available

**Model Choice for MVP**: `base` with `int8` compute type
- Good balance of speed/quality
- ~500MB RAM usage
- Excellent Russian language support

**Why NOT openai-whisper**:
- ❌ Slower (1x baseline)
- ❌ More memory (2-4GB for base model)
- ❌ Requires ffmpeg installation
- ❌ Less optimized for CPU

## Complete Dependency Stack

```toml
[tool.poetry.dependencies]
python = "^3.11"

# Core
python-telegram-bot = "^22.5"       # Telegram Bot API
faster-whisper = "^1.2.0"            # Speech transcription

# Database
sqlalchemy = {extras = ["asyncio"], version = "^2.0.44"}
aiosqlite = "^0.20.0"                # SQLite async driver (MVP)
asyncpg = "^0.30"                    # PostgreSQL async driver (production)
alembic = "^1.13"                    # Database migrations

# Configuration & Utilities
python-dotenv = "^1.0.0"             # Environment variables
pydantic = "^2.10"                   # Data validation
pydantic-settings = "^2.6"           # Settings management

# Async HTTP (if needed)
httpx = "^0.28"                      # Async HTTP client

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"                      # Testing framework
pytest-asyncio = "^0.24"             # Async test support
pytest-cov = "^6.0"                  # Coverage reports
black = "^24.10"                     # Code formatter
ruff = "^0.8"                        # Linter/formatter
mypy = "^1.13"                       # Type checking
```

## Development Environment

### Setup Requirements

✅ **Python 3.11+**
```bash
# Check version
python3 --version

# Recommended: pyenv for version management
pyenv install 3.11.9
pyenv local 3.11.9
```

✅ **Poetry** (dependency management)
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

✅ **Git**
```bash
git init
git config user.name "Your Name"
git config user.email "pass@localhost"
```

✅ **Environment Variables**
```bash
cp .env.example .env
# Edit .env with your Telegram Bot Token
```

### Development Tools

**IDE/Editor**: VS Code recommended
- Extensions: Python, Pylance, Ruff, GitLens

**Code Quality**:
- `black` - auto-formatting
- `ruff` - fast linting
- `mypy` - type checking

**Testing**:
- `pytest` - test runner
- `pytest-asyncio` - async tests
- `pytest-cov` - coverage reports

## Infrastructure

### Development Environment (Current Phase)

**Mode**: Local development with polling

**Requirements**:
- Python 3.11+ installed
- Telegram Bot Token from @BotFather
- 4GB+ RAM (for Whisper model)
- ~2GB disk space (for model cache)

**Data Storage**: SQLite database (`./data/bot.db`)

### Production/Deployment (Future)

**Selected Approach**: Docker + VPS

**Phase 1 (MVP)**: Local polling
- Run locally via `python -m src.main`
- Polling mode (no SSL needed)
- SQLite database

**Phase 2**: Docker containerization
- Dockerfile with multi-stage build
- docker-compose.yml for orchestration
- Volumes for model cache and database
- Still polling mode

**Phase 3**: VPS deployment
- Deploy to VPS (minimum 4GB RAM)
- Switch to webhook mode
- SSL certificate (Let's Encrypt)
- PostgreSQL database
- Nginx reverse proxy

**Phase 4**: CI/CD
- GitHub Actions pipeline
- Automated tests on PR
- Auto-deploy to VPS on merge to main

## Technical Constraints

### Known Constraints

- Must work with Telegram Bot API
- Voice message format: OGG/Opus (Telegram standard)
- Rate limiting: Telegram API limits to consider
- (Others to be identified)

### Performance Requirements

(To be defined based on use case)
- Response time expectations
- Concurrent user handling
- Message processing throughput

### Resource Constraints

- Budget considerations (if using paid APIs)
- Server/compute resources
- Storage requirements

## Configuration Management

**Approach**: Environment variables + Pydantic Settings

### Configuration Structure

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    bot_mode: str = "polling"  # polling or webhook

    # Whisper
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    # Processing
    max_queue_size: int = 100
    max_concurrent_workers: int = 3
    transcription_timeout: int = 120

    # Quotas
    default_daily_quota_seconds: int = 60
    max_voice_duration_seconds: int = 300

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```

### Environment Files

**.env.example** (template):
```bash
TELEGRAM_BOT_TOKEN=your_token_here
BOT_MODE=polling
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
LOG_LEVEL=INFO
```

**.env** (actual, gitignored):
- Contains real bot token
- Environment-specific overrides

## Development Workflow

### Version Control

**Setup**: Git repository
**Branching**: trunk-based (main branch)
**Commit Style**: Conventional Commits preferred

### Testing Strategy

**Framework**: pytest + pytest-asyncio

**Coverage Goals**:
- Unit tests: >70% coverage
- Integration tests for critical paths
- End-to-end tests for main user flows

**Test Structure**:
```
tests/
├── unit/
│   ├── test_whisper_service.py
│   ├── test_quota_manager.py
│   └── test_queue_manager.py
├── integration/
│   ├── test_bot_workflow.py
│   └── test_database.py
└── conftest.py  # Fixtures
```

### CI/CD (Future - Phase 4)

**Platform**: GitHub Actions

**Pipeline**:
1. Run tests on PR
2. Check code formatting (black/ruff)
3. Type checking (mypy)
4. Build Docker image
5. Deploy to VPS on merge to main

## Tool Usage Patterns

### Telegram Bot API

Key APIs to use:
- `getUpdates` or webhook?
- `sendMessage`
- `getFile` (for voice messages)
- Others as needed

### Voice Processing

(Integration patterns to be documented once approach is chosen)

## Technical Decisions Log

| Date | Area | Decision | Alternatives Considered | Rationale |
|------|------|----------|------------------------|-----------|
| 2025-10-12 | Language | Python 3.11+ | Node.js, Go, Rust | Best Whisper integration, mature ecosystem |
| 2025-10-12 | Bot Framework | python-telegram-bot 22.5 | aiogram, pytelegrambotapi | Most mature, async support, both polling/webhook |
| 2025-10-12 | Voice Processing | faster-whisper 1.2.0 | openai-whisper, cloud APIs | 4x faster, less memory, no API costs |
| 2025-10-12 | Architecture | Hybrid Queue (Option 3) | Monolith, Microservices | Balance simplicity/scalability |
| 2025-10-12 | Database | SQLAlchemy + SQLite/PostgreSQL | MongoDB, raw SQL | Async ORM, migration support |
| 2025-10-12 | Deployment | Docker + VPS | Serverless, PaaS | Full control, cost-effective |

## Learning Resources

(Document useful resources discovered during development)

- Telegram Bot API Documentation
- Chosen framework documentation
- Voice processing service docs
- Relevant tutorials/guides

## Notes

This document should be updated as technology decisions are made and technical patterns emerge. It's especially important to document the "why" behind technology choices for future reference.
