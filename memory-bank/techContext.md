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

# Logging
python-json-logger = "^4.0.0"        # JSON log formatting

# Async HTTP & LLM Integration (NEW - 2025-11-20)
httpx = "^0.28"                      # Async HTTP client (for LLM APIs)
tenacity = "^9.0.0"                  # Retry logic for LLM API calls

# System Monitoring
psutil = "^6.1"                      # System monitoring

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"                      # Testing framework
pytest-asyncio = "^0.24"             # Async test support
pytest-cov = "^6.0"                  # Coverage reports
black = "^24.10"                     # Code formatter
ruff = "^0.8"                        # Linter/formatter
mypy = "^1.13"                       # Type checking
```

**Dependency Update Notes**:
- `tenacity ^9.0.0` added (2025-11-20): Provides exponential backoff retry logic for LLM API calls
  - Used in `DeepSeekProvider` for resilient API integration
  - Retry strategy: 3 attempts, exponential backoff (2-10s), retries on timeout/network errors
- `httpx ^0.28` now also used for LLM API communication (previously just for internal services)

## Project Structure (Updated 2025-10-29)

### Services Layer

**Location**: `src/services/`

**Purpose**: Business logic components for request management, user experience, and LLM integration

**Modules**:

1. **queue_manager.py** (296 lines)
   - `QueueManager`: FIFO queue with concurrency control
   - `TranscriptionRequest`: Request data structure
   - `TranscriptionResponse`: Response data structure
   - **Features**:
     - `asyncio.Queue` for FIFO request storage (max 50)
     - `asyncio.Semaphore` for concurrency limiting (max_concurrent=1)
     - Background worker with graceful error handling
     - Request/response tracking with timeout support
   - **Pattern**: Producer-Consumer with bounded queue

2. **progress_tracker.py** (201 lines)
   - `ProgressTracker`: Live progress updates for long-running operations
   - **Features**:
     - Background asyncio task updates Telegram message every 5s
     - Visual progress bar: `🔄 [████████░░░░] 40%`
     - RTF-based time estimation (processing_time = duration × 0.3)
     - Telegram rate limit handling (RetryAfter, TimedOut)
   - **Pattern**: Observer pattern - tracks progress without blocking

3. **llm_service.py** (263 lines) - NEW (2025-11-20)
   - `LLMProvider`: Abstract base class for LLM providers
   - `DeepSeekProvider`: DeepSeek V3 API integration
   - `LLMFactory`: Provider instantiation
   - `LLMService`: High-level LLM API
   - **Features**:
     - Async HTTP client (httpx) for API calls
     - Retry logic with exponential backoff (tenacity)
     - Text truncation (10,000 char limit)
     - Graceful error handling (timeout, API errors, network errors)
     - Automatic fallback to draft text on any failure
   - **Pattern**: Abstract provider pattern + Factory pattern + Service layer
   - **Integration**: Used for hybrid transcription refinement

4. **__init__.py**
   - Module exports: `QueueManager`, `TranscriptionRequest`, `TranscriptionResponse`, `ProgressTracker`, `LLMService`

**Usage**:
```python
# In main.py
queue_manager = QueueManager(
    max_queue_size=settings.max_queue_size,
    max_concurrent=settings.max_concurrent_workers,
)

# In handlers.py
request = TranscriptionRequest(
    id=str(uuid.uuid4()),
    user_id=user.id,
    file_path=file_path,
    duration_seconds=duration_seconds,
    context=transcription_context,
    status_message=status_msg,
    usage_id=usage.id,
)
position = await self.queue_manager.enqueue(request)

# Progress tracking
progress = ProgressTracker(
    message=request.status_message,
    duration_seconds=request.duration_seconds,
    rtf=settings.progress_rtf,
    update_interval=settings.progress_update_interval,
)
await progress.start()
# ... transcription ...
await progress.stop()
```

**Added**: 2025-10-29 (Phase 6: Queue-Based Concurrency Control)

### Storage Layer Updates (2025-10-29)

**Enhanced Repository Pattern**:
- `UsageRepository.create()`: Minimal create for staged writes (Stage 1)
- `UsageRepository.update()`: Update method for lifecycle stages (Stage 2, 3)
- `UsageRepository.get_by_id()`: Retrieve usage record by ID

**Database Model Changes**:
- `Usage.updated_at`: Added for lifecycle tracking
- `Usage.transcription_length`: Added (int) for privacy-friendly analytics
- `Usage.transcription_text`: Removed (privacy improvement)
- `Usage.voice_duration_seconds`: Now nullable for staged writes
- `Usage.model_size`: Now nullable for staged writes

**Migration**: `alembic/versions/a9f3b2c8d1e4_add_updated_at_and_transcription_length.py`

### Configuration Updates

**Queue & Progress Settings** (2025-10-29):
```python
# Queue Configuration
max_queue_size: int = 50  # Changed from 100
max_concurrent_workers: int = 1  # Changed from 3
transcription_timeout: int = 120

# Progress Tracking
progress_update_interval: int = 5
progress_rtf: float = 0.3

# Quotas
max_voice_duration_seconds: int = 120  # Changed from 300 (2 minutes)
```

**LLM & Hybrid Settings** (NEW - 2025-11-20):
```python
# LLM Refinement Configuration
llm_refinement_enabled: bool = Field(default=False)  # Disabled by default
llm_provider: str = Field(default="deepseek")
llm_api_key: str | None = Field(default=None)
llm_model: str = Field(default="deepseek-chat")
llm_base_url: str = Field(default="https://api.deepseek.com")
llm_refinement_prompt: str = Field(default="Улучши транскрипцию...")
llm_timeout: int = Field(default=30)

# Hybrid Strategy Configuration
hybrid_short_threshold: int = Field(default=20)  # seconds
hybrid_draft_provider: str = Field(default="faster-whisper")
hybrid_draft_model: str = Field(default="small")
hybrid_quality_provider: str = Field(default="faster-whisper")
hybrid_quality_model: str = Field(default="medium")

# Audio Preprocessing Configuration
audio_convert_to_mono: bool = Field(default=False)
audio_target_sample_rate: int = Field(default=16000)
audio_speed_multiplier: float = Field(default=1.0)
```

**Environment Variables**:
```bash
# Existing
MAX_VOICE_DURATION_SECONDS=120
MAX_QUEUE_SIZE=50
MAX_CONCURRENT_WORKERS=1
PROGRESS_UPDATE_INTERVAL=5
PROGRESS_RTF=0.3

# NEW - Hybrid Transcription (2025-11-20)
LLM_REFINEMENT_ENABLED=false
LLM_PROVIDER=deepseek
LLM_API_KEY=your_api_key_here
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com
LLM_TIMEOUT=30

HYBRID_SHORT_THRESHOLD=20
HYBRID_DRAFT_PROVIDER=faster-whisper
HYBRID_DRAFT_MODEL=small
HYBRID_QUALITY_PROVIDER=faster-whisper
HYBRID_QUALITY_MODEL=medium

AUDIO_CONVERT_TO_MONO=false
AUDIO_TARGET_SAMPLE_RATE=16000
AUDIO_SPEED_MULTIPLIER=1.0
```

### Logging Configuration (2025-11-03)

**New Module**: `src/utils/logging_config.py` (233 lines)

**Purpose**: Centralized logging with version tracking, structured JSON format, and size-based rotation

**Components**:
1. **VersionEnrichmentFilter**: Adds version and container_id to all log records
2. **CustomJsonFormatter**: JSON formatter with ISO timestamps and structured context
3. **setup_logging()**: Configures file handlers with rotation and optional remote syslog
4. **log_deployment_event()**: Records deployment lifecycle events

**Log Files** (in `/app/logs/` or `LOG_DIR`):
- `app.log`: All INFO+ logs, 10MB per file, 5 backups (60MB max)
- `errors.log`: ERROR/CRITICAL only, 5MB per file, 5 backups (30MB max)
- `deployments.jsonl`: Deployment events, never rotated (~1KB per deployment)

**Environment Variables**:
```bash
# Required
APP_VERSION=v0.1.0  # Set by CI/CD from git tag
LOG_DIR=/app/logs
LOG_LEVEL=INFO

# Optional (remote syslog)
SYSLOG_ENABLED=false
SYSLOG_HOST=logs.papertrailapp.com
SYSLOG_PORT=514
```

**Integration**:
- Called from `src/main.py` at startup
- Volume mount: `./logs:/app/logs` in docker-compose
- All log entries automatically include version (short form: 09f9af8)

**Log Format Example**:
```json
{
  "timestamp": "2025-11-03T15:00:05.123Z",
  "level": "INFO",
  "logger": "src.bot.handlers",
  "version": "09f9af8",
  "container_id": "e3f297d9fe90",
  "message": "Processing voice message",
  "context": {
    "user_id": 123456,
    "duration": 45.2,
    "file_size": 128000
  }
}
```

**Key Design Decision**: Size-based rotation ONLY (not time-based) per user request: "Если мало логов, то пусть хранятся долго". Logs persist longer when generation is low, predictable disk usage (~90MB max).

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
