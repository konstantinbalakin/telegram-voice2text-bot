# Implementation Plan: MVP Telegram Voice Bot with Hybrid Queue Architecture

**Date**: 2025-10-12
**Selected Option**: Option 3 - Hybrid Queue Approach
**Target**: Minimum Viable Product with extensible architecture

---

## Executive Summary

Building a Telegram bot that transcribes voice messages using local Whisper model with a hybrid queue architecture that balances simplicity and scalability.

### Key Decisions

- **Language**: Python 3.11+
- **Whisper**: `faster-whisper` (4x faster than openai-whisper, less memory)
- **Bot Framework**: `python-telegram-bot` v22.5
- **Architecture**: Monolithic with internal asyncio queue
- **Database**: SQLite for MVP → PostgreSQL for production
- **Deployment**: Polling locally → Webhook on VPS

---

## Technical Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram Bot API                         │
└───────────────────────┬─────────────────────────────────────┘
                        │ (Polling/Webhook)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Bot Handler Layer                          │
│  - Receive voice messages                                    │
│  - Check user quotas                                         │
│  - Add to processing queue                                   │
│  - Send status updates                                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              Asyncio Processing Queue                        │
│  - Bounded queue (max 100 tasks)                            │
│  - Background worker coroutines                              │
│  - Semaphore-controlled parallelism                          │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              Whisper Service (Thread Pool)                   │
│  - faster-whisper model (base, int8)                        │
│  - ThreadPoolExecutor (max 3 workers)                       │
│  - Audio download & transcription                           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer                             │
│  - User management                                           │
│  - Quota tracking                                            │
│  - Usage statistics                                          │
└─────────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. Bot Handler (`src/bot/`)
- **handlers.py**: Command and message handlers
- **bot.py**: Bot initialization and lifecycle
- **middleware.py**: Quota checking, rate limiting

#### 2. Processing Queue (`src/processing/`)
- **queue_manager.py**: Asyncio queue wrapper
- **worker_pool.py**: Background worker management
- **task_models.py**: Task data structures

#### 3. Transcription Service (`src/transcription/`)
- **whisper_service.py**: faster-whisper integration
- **audio_handler.py**: Download and preprocessing

#### 4. Storage Layer (`src/storage/`)
- **database.py**: SQLAlchemy async engine
- **models.py**: User, Usage, Transaction models
- **repositories.py**: Data access patterns

#### 5. Quota System (`src/quota/`)
- **quota_manager.py**: Quota checking and enforcement
- **billing.py**: Future billing integration (stub)

---

## Technology Stack (Final)

```toml
[tool.poetry.dependencies]
python = "^3.11"

# Core
python-telegram-bot = "^22.5"
faster-whisper = "^1.2.0"

# Database
sqlalchemy = {extras = ["asyncio"], version = "^2.0.44"}
aiosqlite = "^0.20.0"
alembic = "^1.13"

# Utils
python-dotenv = "^1.0.0"
pydantic = "^2.10"
pydantic-settings = "^2.6"

# Async
httpx = "^0.28"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"
pytest-cov = "^6.0"
black = "^24.10"
ruff = "^0.8"
mypy = "^1.13"
```

---

## Project Structure

```
telegram-voice-bot-v2/
├── src/
│   ├── __init__.py
│   ├── main.py                    # Application entry point
│   ├── config.py                  # Configuration management
│   │
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── bot.py                 # Bot initialization
│   │   ├── handlers.py            # Message/command handlers
│   │   └── middleware.py          # Quota/rate limit middleware
│   │
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── queue_manager.py       # Asyncio queue wrapper
│   │   ├── worker_pool.py         # Background workers
│   │   └── task_models.py         # Task data structures
│   │
│   ├── transcription/
│   │   ├── __init__.py
│   │   ├── whisper_service.py     # faster-whisper integration
│   │   └── audio_handler.py       # Audio download/prep
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py            # DB engine & session
│   │   ├── models.py              # SQLAlchemy models
│   │   └── repositories.py        # Data access layer
│   │
│   └── quota/
│       ├── __init__.py
│       ├── quota_manager.py       # Quota logic
│       └── billing.py             # Future billing (stub)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Pytest fixtures
│   ├── test_bot/
│   ├── test_transcription/
│   ├── test_quota/
│   └── integration/
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .dockerignore
│
├── alembic/
│   ├── versions/
│   └── env.py
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── poetry.lock
├── README.md
├── CLAUDE.md
└── memory-bank/
```

---

## Implementation Phases

### Phase 1: Project Setup (Day 1)

**Tasks**:
1. Initialize Poetry project
2. Setup project structure
3. Configure development environment
4. Create basic configuration system
5. Setup git repository

**Deliverables**:
- Working Python environment
- All directories created
- Poetry dependencies installed
- `.env.example` with configuration template

**Validation**:
- `poetry install` succeeds
- `python -m src.main --help` works
- Tests directory structure ready

---

### Phase 2: Database & Models (Day 1-2)

**Tasks**:
1. Design database schema
2. Implement SQLAlchemy models
3. Setup Alembic migrations
4. Create repository layer
5. Write database tests

**Models**:

```python
# User Model
class User(Base):
    id: int (PK)
    telegram_id: int (unique)
    username: str (nullable)
    daily_quota_seconds: int (default 60)
    is_unlimited: bool (default False)
    created_at: datetime
    last_reset_date: date

# Usage Model
class Usage(Base):
    id: int (PK)
    user_id: int (FK)
    voice_duration_seconds: int
    transcription_text: str
    created_at: datetime

# Future: Transaction Model (for billing)
class Transaction(Base):
    id: int (PK)
    user_id: int (FK)
    amount: decimal
    quota_added_seconds: int
    status: str
    created_at: datetime
```

**Validation**:
- Migrations run successfully
- CRUD operations work
- Tests pass (>80% coverage)

---

### Phase 3: Whisper Integration (Day 2)

**Tasks**:
1. Implement WhisperService class
2. Model initialization with faster-whisper
3. Audio download from Telegram
4. Transcription with timeout
5. Error handling and retry logic
6. Write transcription tests

**Key Implementation**:

```python
from faster_whisper import WhisperModel
import asyncio
from concurrent.futures import ThreadPoolExecutor

class WhisperService:
    def __init__(self, model_size="base", device="cpu"):
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="int8",
            num_workers=2
        )
        self.executor = ThreadPoolExecutor(max_workers=3)

    async def transcribe(self, audio_path: str, timeout: int = 120):
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor,
                    self._transcribe_sync,
                    audio_path
                ),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise TranscriptionTimeoutError()

    def _transcribe_sync(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(
            audio_path,
            language="ru",
            beam_size=5
        )
        return " ".join([segment.text for segment in segments])
```

**Validation**:
- Model loads successfully
- Test audio transcribes correctly
- Timeout mechanism works
- Russian language supported

---

### Phase 4: Processing Queue (Day 2-3)

**Tasks**:
1. Implement QueueManager
2. Create worker pool
3. Task model and lifecycle
4. Semaphore-based concurrency control
5. Graceful shutdown
6. Write queue tests

**Key Implementation**:

```python
class QueueManager:
    def __init__(self, max_size=100, max_workers=3):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.semaphore = asyncio.Semaphore(max_workers)
        self.workers = []

    async def add_task(self, task: TranscriptionTask):
        try:
            await asyncio.wait_for(
                self.queue.put(task),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            raise QueueFullError()

    async def start_workers(self, num_workers=3):
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)

    async def _worker(self, worker_id: int):
        while True:
            task = await self.queue.get()
            async with self.semaphore:
                await self._process_task(task)
            self.queue.task_done()
```

**Validation**:
- Tasks queued successfully
- Workers process concurrently (max 3)
- Queue full handling works
- Graceful shutdown completes all tasks

---

### Phase 5: Bot Handlers (Day 3-4)

**Tasks**:
1. Implement /start, /help commands
2. Voice message handler
3. Quota checking middleware
4. Status updates during processing
5. Error message handling
6. Write bot handler tests

**Key Handlers**:

```python
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    await update.message.reply_text(
        f"Привет! Отправь мне голосовое сообщение, "
        f"и я его расшифрую.\n\n"
        f"Доступно сегодня: {user.remaining_quota} сек"
    )

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    user = await get_or_create_user(update.effective_user.id)

    # Check quota
    if not await quota_manager.check_quota(user, voice.duration):
        await update.message.reply_text(
            "❌ Превышен дневной лимит. "
            "Попробуйте завтра или купите дополнительные минуты."
        )
        return

    # Queue task
    status_msg = await update.message.reply_text("⏳ Обрабатываю...")
    task = TranscriptionTask(
        user_id=user.id,
        voice_file_id=voice.file_id,
        duration=voice.duration,
        chat_id=update.effective_chat.id,
        message_id=status_msg.message_id
    )

    try:
        await queue_manager.add_task(task)
    except QueueFullError:
        await status_msg.edit_text(
            "⚠️ Сервис перегружен. Попробуйте через 30 секунд."
        )
```

**Validation**:
- Bot responds to /start
- Voice messages queued
- Quota enforced correctly
- Status updates work
- Error messages user-friendly

---

### Phase 6: Integration & Testing (Day 4-5)

**Tasks**:
1. End-to-end integration
2. Connect all components
3. Integration tests
4. Error scenario testing
5. Performance testing
6. Bug fixes

**Test Scenarios**:
- Happy path: voice → transcription → response
- Quota exceeded
- Queue full
- Transcription timeout
- Invalid audio
- Concurrent users
- Database failures

**Validation**:
- All integration tests pass
- No memory leaks
- Handles 10 concurrent requests
- Graceful degradation under load

---

### Phase 7: Docker & Local Deployment (Day 5-6)

**Tasks**:
1. Create Dockerfile
2. Create docker-compose.yml
3. Setup volumes for model cache
4. Environment configuration
5. Test local Docker deployment

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install Poetry
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

# Copy application
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Download Whisper model at build time
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

CMD ["python", "-m", "src.main"]
```

**docker-compose.yml**:

```yaml
version: '3.8'

services:
  bot:
    build: .
    env_file: .env
    volumes:
      - whisper-models:/root/.cache/huggingface
      - ./data:/app/data
    restart: unless-stopped
    environment:
      - DATABASE_URL=sqlite:////app/data/bot.db

volumes:
  whisper-models:
```

**Validation**:
- Docker build succeeds
- Container runs successfully
- Bot responds in Telegram
- Data persists across restarts

---

## Configuration Management

### Environment Variables

```bash
# .env.example

# Telegram
TELEGRAM_BOT_TOKEN=your_token_here
BOT_MODE=polling  # polling or webhook

# Whisper
WHISPER_MODEL_SIZE=base  # tiny, base, small, medium, large
WHISPER_DEVICE=cpu  # cpu or cuda
WHISPER_COMPUTE_TYPE=int8  # int8, float16, float32

# Database
DATABASE_URL=sqlite:///./data/bot.db
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname

# Processing
MAX_QUEUE_SIZE=100
MAX_CONCURRENT_WORKERS=3
TRANSCRIPTION_TIMEOUT=120

# Quotas
DEFAULT_DAILY_QUOTA_SECONDS=60
MAX_VOICE_DURATION_SECONDS=300

# Logging
LOG_LEVEL=INFO
```

### Config Class (Pydantic)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_bot_token: str
    bot_mode: str = "polling"

    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    database_url: str

    max_queue_size: int = 100
    max_concurrent_workers: int = 3
    transcription_timeout: int = 120

    default_daily_quota_seconds: int = 60
    max_voice_duration_seconds: int = 300

    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```

---

## Risk Mitigation Strategies

### R1: Whisper Performance
**Mitigation**:
- Use faster-whisper with int8 quantization
- Thread pool isolation
- Timeout mechanism (120s)
- Model: "base" for MVP (good speed/quality balance)

### R2: Resource Consumption
**Mitigation**:
- Semaphore limits concurrent transcriptions (max 3)
- Queue size bounded (max 100)
- VPS requirement: 4GB RAM minimum
- Model cached in Docker volume

### R3: Quota System Complexity
**Mitigation**:
- Simple daily counter for MVP
- Database transaction for quota deduction
- Reset mechanism on date change
- No payment integration in MVP

### R4: Audio Format Conversion
**Mitigation**:
- faster-whisper handles OGG/Opus directly
- No ffmpeg needed (uses PyAV internally)
- Fallback error handling if format unsupported

### R5: Long Voice Messages
**Mitigation**:
- Hard limit: 5 minutes (300 seconds)
- Check before queueing
- Clear error message to user

### R6: Polling → Webhook Migration
**Mitigation**:
- Abstract update handler interface
- Config switch: BOT_MODE=polling|webhook
- No code changes to handlers needed

---

## Success Criteria (MVP)

### Functional Requirements
- ✅ Bot accepts voice messages via Telegram
- ✅ Transcription via local faster-whisper
- ✅ Text response sent back to user
- ✅ Daily quota system (60 seconds/day)
- ✅ Unlimited access flag for specific users
- ✅ Graceful error handling

### Performance Requirements
- ✅ Transcription: <30 seconds for 1-minute audio
- ✅ Queue: Handles 100 pending tasks
- ✅ Concurrent: Processes 3 tasks simultaneously
- ✅ Memory: <2GB RAM usage

### Quality Requirements
- ✅ Test coverage: >70%
- ✅ Type hints throughout codebase
- ✅ Formatted with black/ruff
- ✅ No critical linter warnings

### Operational Requirements
- ✅ Runs locally with polling
- ✅ Dockerized deployment
- ✅ Graceful shutdown
- ✅ Basic logging

---

## Future Enhancements (Post-MVP)

### Phase 2 Features
1. **Text Processing Pipeline**
   - Summary generation
   - Key points extraction
   - Sentiment analysis
   - Extensible processor interface

2. **Advanced Quota System**
   - Purchase packages via Telegram Payments
   - Payment gateway integration (Stripe/YooKassa)
   - Transaction history
   - Invoice generation

3. **Performance Improvements**
   - Redis-based queue (distribute across machines)
   - Separate worker service
   - GPU support
   - Model warm-up optimization

### Phase 3 Features
1. **VPS Deployment**
   - Webhook mode
   - SSL certificate setup
   - Nginx reverse proxy
   - systemd service

2. **CI/CD Pipeline**
   - GitHub Actions
   - Automated tests
   - Docker build & push
   - Auto-deploy to VPS on merge

3. **Monitoring & Observability**
   - Prometheus metrics
   - Grafana dashboards
   - Error tracking (Sentry)
   - Usage analytics

---

## Timeline Estimate

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Project Setup | 0.5 day | Working environment |
| 2. Database & Models | 1 day | DB schema, migrations |
| 3. Whisper Integration | 0.5 day | Transcription works |
| 4. Processing Queue | 1 day | Queue system functional |
| 5. Bot Handlers | 1 day | Bot responds to messages |
| 6. Integration & Testing | 1 day | End-to-end working |
| 7. Docker & Deployment | 1 day | Containerized app |
| **Total MVP** | **6 days** | Production-ready MVP |

---

## Next Immediate Steps

1. ✅ Approve this plan
2. Initialize project structure
3. Setup Poetry and dependencies
4. Start Phase 1: Project Setup

**Ready to execute with `/workflow:execute`**
