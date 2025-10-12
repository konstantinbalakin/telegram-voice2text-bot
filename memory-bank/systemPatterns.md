# System Patterns: Telegram Voice Bot v2

## Architecture Overview

**Current Status**: ✅ Designed (2025-10-12) - Hybrid Queue Architecture

**Architecture Pattern**: Monolithic application with internal async queue system

This is a **transitional architecture** that balances MVP speed with future scalability. The system is built as a single Python application but structured to allow migration to microservices if needed.

## Core Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram Bot API                         │
└───────────────────────┬─────────────────────────────────────┘
                        │ (Polling initially, Webhook later)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Bot Handler Layer                          │
│  Components:                                                 │
│  - handlers.py: Message/command handlers                    │
│  - middleware.py: Quota check, rate limiting                │
│  - bot.py: Bot lifecycle management                         │
└───────────────────────┬─────────────────────────────────────┘
                        │ Enqueue Task
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              Asyncio Processing Queue                        │
│  Components:                                                 │
│  - queue_manager.py: Queue wrapper (max 100 tasks)         │
│  - worker_pool.py: Background worker coroutines            │
│  - task_models.py: Task data structures                    │
│                                                              │
│  Concurrency Control:                                        │
│  - Semaphore limits to 3 parallel workers                  │
│  - Graceful backpressure when queue full                   │
└───────────────────────┬─────────────────────────────────────┘
                        │ Process Task
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              Whisper Service (Thread Pool)                   │
│  Components:                                                 │
│  - whisper_service.py: faster-whisper wrapper              │
│  - audio_handler.py: Download & preprocessing              │
│                                                              │
│  Implementation:                                             │
│  - ThreadPoolExecutor (max 3 workers)                      │
│  - Model: faster-whisper "base" with int8                  │
│  - Timeout: 120 seconds                                     │
└───────────────────────┬─────────────────────────────────────┘
                        │ Store & Respond
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer                             │
│  Components:                                                 │
│  - database.py: SQLAlchemy async engine                    │
│  - models.py: User, Usage, Transaction models              │
│  - repositories.py: Data access patterns                   │
│                                                              │
│  Storage: SQLite (MVP) → PostgreSQL (production)           │
└─────────────────────────────────────────────────────────────┘
```

### System Components

#### 1. **Bot Handler Layer** (`src/bot/`)
**Responsibility**: Interface with Telegram, handle user interactions

- **handlers.py**:
  - `/start`, `/help` commands
  - Voice message handler
  - Error message formatting

- **middleware.py**:
  - Quota validation before processing
  - Rate limiting (1 request per 10 sec per user)
  - User creation/lookup

- **bot.py**:
  - Bot initialization
  - Polling/webhook setup
  - Graceful shutdown

**Pattern**: Handler-based routing with middleware chain

#### 2. **Processing Queue** (`src/processing/`)
**Responsibility**: Decouple message receipt from processing

- **queue_manager.py**:
  - Asyncio Queue wrapper
  - Max size: 100 tasks
  - Timeout handling on enqueue

- **worker_pool.py**:
  - Background coroutines (workers)
  - Fetch tasks from queue
  - Semaphore-controlled parallelism

- **task_models.py**:
  - `TranscriptionTask` data class
  - Task lifecycle states

**Pattern**: Producer-Consumer with bounded queue

#### 3. **Transcription Service** (`src/transcription/`)
**Responsibility**: Voice-to-text conversion

- **whisper_service.py**:
  - faster-whisper model management
  - Transcription with timeout
  - Thread pool execution
  - Model caching

- **audio_handler.py**:
  - Download from Telegram
  - Format validation
  - Temporary file cleanup

**Pattern**: Service layer with thread pool isolation

#### 4. **Storage Layer** (`src/storage/`)
**Responsibility**: Data persistence and retrieval

- **database.py**:
  - Async SQLAlchemy engine
  - Session management
  - Connection pooling

- **models.py**:
  - `User`: Telegram user data & quotas
  - `Usage`: Transcription history
  - `Transaction`: Future billing (stub)

- **repositories.py**:
  - Repository pattern for data access
  - Query abstraction

**Pattern**: Repository pattern with async ORM

#### 5. **Quota System** (`src/quota/`)
**Responsibility**: Usage limits and billing (future)

- **quota_manager.py**:
  - Check user quota before processing
  - Deduct quota after success
  - Daily reset logic

- **billing.py**:
  - Future payment integration (stub)
  - Transaction management

**Pattern**: Service layer with transactional guarantees

### Data Flow

#### Primary Flow: Voice Message → Transcription

```
1. User sends voice message
   ↓
2. Bot receives update (polling/webhook)
   ↓
3. Voice handler invoked
   ↓
4. Middleware checks quota
   ├─ Exceeded → Error message
   └─ OK → Continue
   ↓
5. Create TranscriptionTask
   ↓
6. Enqueue task
   ├─ Queue full → Backpressure message
   └─ OK → Send "Processing..." status
   ↓
7. Worker picks up task (async)
   ↓
8. Download audio file (async)
   ↓
9. Transcribe in thread pool (blocking, with timeout)
   ├─ Timeout → Error
   ├─ Exception → Error
   └─ Success → Continue
   ↓
10. Save usage to DB (transaction)
    ↓
11. Send result to user
    ↓
12. Mark task complete
```

**Asynchronous**: Steps 1-6, 7-8, 10-12
**Synchronous (thread pool)**: Step 9 (Whisper)

## Key Technical Decisions

### Decision Log

| Date | Decision | Rationale | Confidence |
|------|----------|-----------|-----------|
| 2025-10-12 | Hybrid Queue Architecture | Balance MVP speed with scalability | 85% |
| 2025-10-12 | Asyncio queue (in-process) | Simple for MVP, easy to migrate to Redis later | 80% |
| 2025-10-12 | ThreadPoolExecutor for Whisper | Whisper is CPU-bound, avoid blocking event loop | 95% |
| 2025-10-12 | Semaphore (max 3 workers) | Limit memory usage, prevent OOM | 90% |
| 2025-10-12 | SQLite → PostgreSQL path | Fast MVP start, clear upgrade path | 85% |
| 2025-10-12 | Repository pattern | Abstracts DB access, testable | 80% |

## Design Patterns in Use

### 1. **Producer-Consumer Pattern**
- **Where**: Bot handlers (producer) → Queue → Workers (consumer)
- **Why**: Decouple receiving messages from processing them
- **Benefit**: Bot never blocks, handles backpressure gracefully

### 2. **Repository Pattern**
- **Where**: `repositories.py` for database access
- **Why**: Abstract SQLAlchemy queries, easier testing
- **Benefit**: Can swap DB implementation without changing business logic

### 3. **Service Layer Pattern**
- **Where**: `WhisperService`, `QuotaManager`
- **Why**: Encapsulate business logic separate from handlers
- **Benefit**: Reusable, testable, clear responsibilities

### 4. **Thread Pool Pattern**
- **Where**: Whisper transcription execution
- **Why**: Isolate blocking CPU-intensive work from async event loop
- **Benefit**: Async code remains responsive

### 5. **Middleware Pattern**
- **Where**: Quota checking before handler execution
- **Why**: Cross-cutting concerns (quota, rate limit)
- **Benefit**: Keep handlers focused on core logic

### 6. **Configuration Object Pattern**
- **Where**: `Settings` class with Pydantic
- **Why**: Centralized, validated configuration
- **Benefit**: Type-safe, environment-aware

## Component Relationships

```
handlers.py
    ├─> middleware.py (quota check)
    ├─> queue_manager.py (enqueue task)
    └─> database.py (user lookup)

worker_pool.py
    ├─> queue_manager.py (dequeue task)
    ├─> audio_handler.py (download)
    ├─> whisper_service.py (transcribe)
    ├─> database.py (save usage)
    └─> bot.py (send result)

whisper_service.py
    └─> ThreadPoolExecutor (run blocking code)

quota_manager.py
    └─> database.py (check/update quotas)
```

**Key Dependencies**:
- All components depend on `config.py` (Settings)
- Database layer is independent (no upward dependencies)
- Bot layer doesn't know about Worker internals (queue abstraction)

## Critical Implementation Paths

### Hot Path 1: Voice Message Processing
**Performance Target**: <30 seconds for 1-minute audio

```python
# Critical path pseudocode
async def voice_handler(update):
    user = await get_user()  # DB query ~50ms
    if not await check_quota(user):  # DB query ~50ms
        return error()

    task = create_task()
    await queue.put(task)  # Instant (bounded queue)
    await send_status()  # Telegram API ~200ms

async def worker():
    task = await queue.get()  # Wait for task
    audio = await download_audio()  # Telegram API ~1-2s

    # Thread pool (blocking, but isolated)
    text = await run_in_executor(whisper.transcribe, audio)  # 10-30s

    await save_usage()  # DB query ~50ms
    await send_result()  # Telegram API ~200ms
```

**Bottleneck**: Whisper transcription (10-30s)
**Mitigation**: faster-whisper, int8 quantization, limited parallelism

### Hot Path 2: Quota Check
**Performance Target**: <100ms

```python
async def check_quota(user):
    if user.is_unlimited:
        return True

    if user.last_reset_date < today:
        await reset_quota(user)  # One-time per day

    return user.today_usage < user.daily_quota
```

**Optimization**: In-memory cache for unlimited users (future)

## Integration Points

### Telegram Bot API
**Mode**: Polling (MVP) → Webhook (production)

**Key Methods**:
- `get_updates()`: Polling for new messages
- `send_message()`: Send text responses
- `edit_message_text()`: Update status messages
- `get_file()`: Get voice file metadata
- `download_file()`: Download voice data

**Rate Limits**:
- 30 messages/second (global)
- 20 messages/minute per chat

### faster-whisper
**Integration**: Thread pool executor

```python
model = WhisperModel("base", device="cpu", compute_type="int8")

# In thread pool:
segments, info = model.transcribe(
    audio_path,
    language="ru",
    beam_size=5
)
```

**Model Loading**: Once at startup, cached in memory

### SQLite/PostgreSQL
**Integration**: SQLAlchemy async

```python
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession)
```

**Migrations**: Alembic for schema versioning

## Scalability Considerations

### Current Limits (MVP)
- **Concurrent transcriptions**: 3
- **Queue size**: 100 tasks
- **Memory**: ~2GB (3 models + overhead)
- **Expected load**: 10-50 users

### Scaling Strategy

**Phase 1 (Current)**: Single process
- Vertical scaling (bigger VPS)
- Optimize model size (base → tiny if needed)

**Phase 2**: Add Redis queue
- Replace asyncio.Queue with Redis
- Enables multiple bot processes
- Horizontal scaling begins

**Phase 3**: Separate worker service
- Bot service (stateless, many instances)
- Worker service (stateful, GPU-enabled)
- True microservices

### Bottleneck Analysis
1. **Whisper processing**: Solved by limiting parallelism
2. **Memory**: Solved by int8 quantization
3. **Database**: SQLite limits, migrate to PostgreSQL
4. **Queue**: In-memory limits, migrate to Redis

## Security Considerations

### API Token Management
- ✅ Token in `.env` file (gitignored)
- ✅ Never logged or exposed
- ✅ Pydantic validation ensures presence

### User Data
- Voice files: Downloaded to `/tmp`, deleted after processing
- Transcriptions: Stored in DB (consider retention policy)
- User IDs: Telegram user_id only (no PII)

### Input Validation
- Voice duration: Max 5 minutes (300 seconds)
- File size: Telegram limits (20MB max)
- Rate limiting: 1 request per 10 seconds per user

### Future Considerations
- Encrypt transcriptions at rest
- GDPR compliance (data deletion)
- Audit logging for unlimited users

## Performance Characteristics

### Expected Performance (MVP)

| Metric | Target | Measured |
|--------|--------|----------|
| Transcription (1 min audio) | <30s | TBD |
| Quota check latency | <100ms | TBD |
| End-to-end (receive → respond) | <35s | TBD |
| Concurrent users | 10-50 | TBD |
| Memory usage | <2GB | TBD |

### Monitoring Points
- Queue length (alert if >80% full)
- Worker processing time
- Database query duration
- Whisper model load time
- Telegram API response time

## Migration Path

### From MVP to Production

**Current Architecture** (MVP):
```
Single Process
├─ Bot (asyncio)
├─ Queue (asyncio.Queue)
└─ Workers (asyncio + ThreadPool)
```

**Future Architecture** (Scalable):
```
Bot Service (N instances)
    ↓ Redis Queue
Worker Service (M instances)
    ├─ CPU workers
    └─ GPU workers (optional)
```

**Migration Steps**:
1. Add Redis adapter to QueueManager
2. Extract worker logic to separate main.py
3. Deploy as separate containers
4. Scale independently

**Key Insight**: Architecture is designed for this migration to be straightforward.

## Notes

This architecture prioritizes:
1. **Speed to MVP**: Single codebase, simple deployment
2. **Maintainability**: Clear separation of concerns
3. **Extensibility**: Easy to add text processing pipeline
4. **Scalability path**: Can migrate to microservices when needed

The hybrid approach means we don't over-engineer for scale we don't have yet, but we also don't paint ourselves into a corner.
