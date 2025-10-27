# Technical Context: Telegram Voice2Text Bot

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

**Production Configuration** (finalized 2025-10-24): `medium / int8 / beam1`
- **Performance**: RTF ~0.3x (3x faster than audio duration)
  - 7s audio → ~2s, 30s audio → ~10s, 60s audio → ~20s
- **Memory**: ~2GB RAM peak (tested in production, not ~3.5GB as initially estimated)
- **Quality**: Excellent for Russian language, good for long informal speech
- **Rationale**: Prioritized quality over speed after comprehensive benchmarking

**Alternative Configurations**:
- `tiny/int8`: Fast but poor quality (22-78% similarity in tests)
- `small/int8`: Faster (~2s for 7s audio) but lower accuracy
- `medium/int8/beam5`: Better quality but 2x slower
- OpenAI API: Best quality but costs $0.006/minute

📄 Benchmark results: `memory-bank/benchmarks/final-decision.md`

**Provider Architecture**:
- **Active Providers**: faster-whisper (local), OpenAI API (optional)
- **Removed**: openai-whisper (original Whisper) - larger, slower, removed 2025-10-24
- **Routing**: Single provider, fallback, or benchmark mode
- **Configuration**: ENV-driven for flexibility

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

### Production/Deployment (Current Status)

**Deployment Approach**: Docker + docker-compose ✅ IMPLEMENTED (2025-10-16)

**Current Phase**: Local Docker deployment complete, ready for VPS

**Docker Implementation**:
- **Dockerfile**: Single-stage python:3.11-slim-bookworm
  - ffmpeg for audio processing
  - Build cache mounting for faster rebuilds
  - Non-root user (appuser) for security
  - Health checks (30s interval)
  - Image size: ~1GB (acceptable for ML workload)
  - Build time: ~4 minutes (with cache)

- **docker-compose.yml**: Production-ready orchestration
  - Service: telegram-voice2text-bot
  - Restart policy: unless-stopped
  - Environment: .env file support
  - Volumes:
    - ./data:/app/data (SQLite persistence)
    - ./logs:/app/logs (log persistence)
    - whisper-models (named volume for model cache)
  - Resource limits: 2 CPUs, 2GB RAM
  - PostgreSQL service ready (commented out)

- **Makefile**: Workflow automation
  - `make deps` - Export Poetry dependencies
  - `make build` - Build Docker image
  - `make up` - Start container
  - `make down` - Stop container
  - `make logs` - View logs
  - `make rebuild` - Full rebuild
  - `make clean` - Docker cleanup

**Phase Progression**:
- ✅ **Phase 1 (Current)**: Local Docker with polling
- ⏳ **Phase 2**: VPS deployment (polling mode)
- ⏳ **Phase 3**: Webhook mode with SSL
- ⏳ **Phase 4**: PostgreSQL migration
- ⏳ **Phase 5**: CI/CD pipeline

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

### CI/CD (Future - Phase 4) ✅ IMPLEMENTED (2025-10-19)

**Platform**: GitHub Actions ✅

**Workflows Operational**:

1. **CI Workflow** (`.github/workflows/ci.yml`) ✅
   - **Trigger**: Pull requests to main branch
   - **Quality Gates**:
     - pytest with coverage reporting
     - mypy type checking (strict mode)
     - ruff linting
     - black formatting verification
   - **Caching**: Poetry dependencies cached by poetry.lock hash
   - **Coverage**: Reports uploaded to Codecov

2. **Build & Deploy Workflow** (`.github/workflows/build-and-deploy.yml`) ✅
   - **Trigger**: Push to main branch (after PR merge)
   - **Build Stage**:
     - Export Poetry dependencies
     - Build Docker image with Docker Buildx
     - Push to Docker Hub with dual tags (latest + SHA)
     - GitHub Actions cache for Docker layers
   - **Deploy Stage** (ready, awaiting VPS):
     - SSH to VPS server
     - Pull latest code
     - Create .env from GitHub Secrets
     - Pull and deploy new Docker image
     - Rolling update with health checks
     - Automatic image cleanup

**Protection**:
- ✅ Main branch protected on GitHub
- ✅ Requires PR for all changes
- ✅ CI checks must pass before merge

**Secrets Configured**:
- ✅ TELEGRAM_BOT_TOKEN
- ✅ DOCKER_USERNAME
- ✅ DOCKER_PASSWORD
- ⏳ VPS_HOST (pending VPS purchase)
- ⏳ VPS_USER (pending VPS purchase)
- ⏳ VPS_SSH_KEY (pending VPS purchase)

**Status**: ✅ Fully operational, awaiting VPS infrastructure only

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
| 2025-10-16 | Docker Base Image | python:3.11-slim-bookworm | Alpine, full Python image | Good balance of size and compatibility |
| 2025-10-16 | Dockerfile Strategy | Single-stage | Multi-stage build | Simpler, adequate optimization for use case |
| 2025-10-16 | Build Optimization | Build cache mounting | No cache | Significantly faster rebuilds (minutes vs tens of minutes) |
| 2025-10-19 | CI/CD Platform | GitHub Actions | GitLab CI, Jenkins, CircleCI | Free for public repos, native GitHub integration, excellent caching |
| 2025-10-19 | Branch Protection | Protected main branch | Open main branch | Enforces code review, prevents direct commits |
| 2025-10-19 | Deployment Strategy | Automated via SSH | Manual deployment, Kubernetes | Simple, reliable, zero-downtime rolling updates |
| 2025-10-19 | Docker Registry | Docker Hub | GitHub Container Registry, private registry | Free for public images, widely used, reliable |

## Learning Resources

(Document useful resources discovered during development)

- Telegram Bot API Documentation
- Chosen framework documentation
- Voice processing service docs
- Relevant tutorials/guides

## Notes

This document should be updated as technology decisions are made and technical patterns emerge. It's especially important to document the "why" behind technology choices for future reference.
