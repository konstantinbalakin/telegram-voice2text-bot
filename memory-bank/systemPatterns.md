# System Patterns: Telegram Voice2Text Bot

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
**Responsibility**: Voice-to-text conversion with flexible provider architecture

**Provider Architecture** (implemented 2025-10-20, finalized 2025-10-24):
- **factory.py**:
  - Provider factory pattern
  - ENV-driven provider initialization
  - Supports multiple providers simultaneously
  - Graceful handling of unavailable providers

- **providers/**:
  - `base.py`: Abstract base class for all providers
  - `faster_whisper_provider.py`: Local faster-whisper integration (production default)
  - `openai_provider.py`: OpenAI API integration (optional fallback)
  - Provider lifecycle: initialize() → transcribe() → shutdown()

- **routing/router.py**:
  - Strategy-based provider selection
  - Single provider, fallback, or benchmark mode
  - Benchmark mode for empirical testing (used for model selection)

- **whisper_service.py**:
  - Legacy service wrapper (maintained for backward compatibility)
  - Thread pool execution for blocking operations
  - Model caching

- **audio_handler.py**:
  - Download from Telegram
  - Format validation
  - Temporary file cleanup

**Pattern**: Strategy pattern + Factory pattern + Service layer with thread pool isolation

**Key Design Decision (2025-10-24)**: Provider architecture designed for flexibility but simplified after benchmarking. Initially supported 3 providers; removed openai-whisper after proving faster-whisper medium was superior in both speed and quality. Architecture allows easy addition of new providers if needed (e.g., Azure, Google Cloud).

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
| 2025-10-20 | Provider architecture (Strategy pattern) | Enable flexible provider switching and benchmarking | 90% |
| 2025-10-24 | Production model: medium/int8/beam1 | Comprehensive benchmarking showed best quality/speed balance | 95% |
| 2025-10-24 | Remove openai-whisper provider | faster-whisper medium superior in all metrics, -2-3GB Docker image | 90% |
| 2025-10-28 | Documentation reorganization | Hierarchical docs/ structure improves navigation and scalability | 90% |
| 2025-10-29 | CI/CD must include optional deps | Poetry optional dependencies require explicit --extras in export | 95% |
| 2025-10-29 | Queue-based concurrency control | Prevent crashes on 1 GB RAM / 1 vCPU VPS, sequential processing with live progress | 95% |
| 2025-10-29 | Duration limit 120s (2 min) | Balance resource protection with user needs (solves 4-min crash) | 90% |
| 2025-10-29 | Privacy: transcription_length only | Store analytics without sensitive text data | 85% |
| 2025-10-29 | Sequential processing (max_concurrent=1) | Conservative approach for resource-constrained deployment | 90% |
| 2025-10-29 | Automated database migrations | Test migrations in CI, apply before deploy, rollback on failure | 95% |
| 2025-10-29 | Health check with schema verification | Prevent bot startup with outdated schema, docker health checks | 90% |
| 2025-10-29 | Queue size optimization (10 max) | Conservative limit for 1GB VPS, adequate buffering with progress feedback | 85% |
| 2025-11-03 | Centralized logging with version tracking | Essential for production observability, size-based rotation per user request | 95% |
| 2025-11-03 | Separate build and deploy workflows | Enables testing between stages, automatic versioning without manual overhead | 90% |
| 2025-11-03 | Size-based log rotation only | User request: "Если мало логов, то пусть хранятся долго" - predictable disk usage | 90% |
| 2025-11-19 | Atomic counter for queue position | `qsize()` unreliable due to worker immediately pulling items; dedicated counter provides accurate position | 95% |
| 2025-11-19 | UUID suffix for file downloads | Prevent filename collisions when multiple users process same file_id | 95% |
| 2025-11-19 | Dual list tracking for queue | Separate _pending_requests and _processing_requests lists for accurate wait time calculation | 95% |
| 2025-11-19 | Callback pattern for queue updates | Notify handlers when queue changes to enable dynamic UI updates | 90% |
| 2025-11-19 | Time calculation with parallel processing | Wait time = (processing + pending ahead) × RTF / max_concurrent | 95% |
| 2025-11-20 | Hybrid transcription strategy | Duration-based routing: <20s = quality, ≥20s = draft + LLM refinement | 95% |
| 2025-11-20 | LLM post-processing pattern | Use fast draft model + LLM refinement for long audio instead of slow quality model | 90% |
| 2025-11-20 | Staged UI updates for refinement | Show draft immediately, then refinement in progress, then final - keeps user informed | 95% |
| 2025-11-20 | Audio preprocessing pipeline | Optional mono conversion and speed adjustment before transcription | 85% |
| 2025-11-20 | Abstract LLM provider pattern | Enable multiple LLM providers (DeepSeek, OpenAI, etc.) via factory + abstract base class | 90% |
| 2025-11-20 | Graceful degradation for LLM | Always fall back to draft text on any LLM error (timeout, API, network) | 95% |
| 2025-11-20 | Feature flags for production safety | Disable new features by default (llm_refinement_enabled=false), gradual rollout | 95% |

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

### 7. **Strategy Pattern** (added 2025-10-20)
- **Where**: Provider routing in `TranscriptionRouter`
- **Why**: Enable switching between different transcription providers at runtime
- **Benefit**: Support benchmark mode, fallback strategies, easy provider testing
- **Implementation**:
  - `SingleProviderStrategy`: Use one provider
  - `FallbackStrategy`: Try primary, fall back to secondary
  - `BenchmarkStrategy`: Test all providers, compare results

### 8. **Factory Pattern** (added 2025-10-20)
- **Where**: `ProviderFactory` in `factory.py`
- **Why**: Centralized provider instantiation based on configuration
- **Benefit**: Hide provider initialization complexity, graceful degradation if provider unavailable
- **Usage**: ENV-driven provider selection (`WHISPER_PROVIDERS=["faster-whisper", "openai"]`)

### 9. **Queue-Based Request Management Pattern** (added 2025-10-29)
- **Where**: `QueueManager` in `src/services/queue_manager.py`
- **Why**: Prevent resource exhaustion under concurrent load, ensure FIFO processing
- **Benefit**: Crash prevention, predictable processing order, backpressure handling
- **Implementation**:
  - `asyncio.Queue` for FIFO request storage (max 50 requests)
  - `asyncio.Semaphore` for concurrency control (max_concurrent=1)
  - Background worker with graceful error handling
  - Request/response tracking with timeout support
- **Usage**: Bot handlers enqueue `TranscriptionRequest`, worker processes sequentially
- **Key Characteristic**: Sequential processing (max_concurrent=1) on resource-constrained VPS prevents crashes while maintaining acceptable UX

### 10. **Progress Tracking Pattern** (added 2025-10-29)
- **Where**: `ProgressTracker` in `src/services/progress_tracker.py`
- **Why**: Provide live feedback during long-running operations (10-40s transcriptions)
- **Benefit**: Improved UX, reduces perceived wait time, shows system is working
- **Implementation**:
  - Background asyncio task updates Telegram message every 5 seconds
  - Visual progress bar: `🔄 [████████░░░░] 40%`
  - RTF-based time estimation (processing_time = duration × 0.3)
  - Telegram rate limit handling (RetryAfter, TimedOut)
- **Usage**: Created at transcription start, updates automatically, stopped on completion
- **Pattern**: Observer pattern - tracks progress without blocking main operation

### 11. **Staged Database Writes Pattern** (added 2025-10-29)
- **Where**: `UsageRepository` in `src/storage/repositories.py`
- **Why**: Track request lifecycle for analytics, handle partial failures
- **Benefit**: Detailed analytics, failure point identification, privacy-friendly data collection
- **Implementation**:
  - **Stage 1** (download start): Create record with `user_id`, `voice_file_id`, `created_at`
  - **Stage 2** (download complete): Update with `voice_duration_seconds`, `updated_at`
  - **Stage 3** (transcription complete): Update with `model_size`, `processing_time_seconds`, `transcription_length`, `updated_at`
- **Privacy Feature**: Stores `transcription_length` (int) instead of `transcription_text` (string)
- **Usage**: Enables tracking failed downloads, failed transcriptions, and full lifecycle timing
- **Pattern**: State pattern - records progress through lifecycle stages

### 12. **Graceful Degradation Pattern** (added 2025-10-29)
- **Where**: Handler duration validation and queue capacity checks
- **Why**: Provide clear feedback when system cannot process request
- **Benefit**: Better UX than silent failures or crashes, guides users to acceptable behavior
- **Implementation**:
  - **Duration validation**: Reject files > 120s with clear message showing user's duration vs limit
  - **Queue capacity**: Reject when queue full, show current queue depth
  - **Clear error messages**: Use emoji and Russian language for user-friendly communication
- **Examples**:
  ```
  ⚠️ Максимальная длительность: 120с (2 мин)
  Ваш файл: 150с (2 мин 30с)

  ⚠️ Очередь переполнена. Пожалуйста, попробуйте через несколько минут.
  В очереди сейчас: 50 запросов
  ```
- **Pattern**: Fail-fast with informative feedback

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
- Provider layer is pluggable (factory + strategy pattern)

## Benchmark Methodology (implemented 2025-10-20, completed 2025-10-24)

### Purpose
Empirical testing framework to select optimal transcription configuration based on real-world performance metrics.

### Architecture
**Benchmark Mode**: Special routing strategy that processes same audio through multiple providers/configurations simultaneously for comparison.

**Implementation**:
```python
# In config.py
BENCHMARK_MODE=true
BENCHMARK_CONFIGS=[
  {"provider_name": "faster-whisper", "model_size": "medium", "compute_type": "int8", "beam_size": 1},
  {"provider_name": "openai"}  # Reference quality
]
```

**Workflow**:
1. Bot receives voice message (when BENCHMARK_MODE=true)
2. Router creates multiple provider instances on-demand (per config)
3. Processes audio through all providers in parallel
4. Collects results: transcribed text, processing time, memory usage
5. Saves all results to separate files for manual analysis
6. Returns OpenAI result to user (reference quality)

### Testing Protocol (2025-10-22 to 2025-10-24)

**Test Suite**:
- 3 representative audio samples (7s short, 24s medium, 163s long)
- Russian language, informal speech
- Real Telegram voice messages

**Configurations Tested**: 30+
- faster-whisper: tiny/small/medium with various beam sizes (1, 3, 5, 7, 10)
- Compute types: int8, float32
- openai-whisper: tiny/base/small/medium (later removed)
- OpenAI API: whisper-1 (reference)

**Metrics Collected**:
- **RTF (Real-Time Factor)**: processing_time / audio_duration
- **Memory**: Peak RAM usage during transcription
- **Quality**: Manual comparison against OpenAI API reference
- **Similarity**: Automated text similarity percentage

**Results Storage**: `docs/quality_compare/YYYY-MM-DD_*.md`

### Key Findings

**Performance vs Quality Trade-off**:
- tiny/int8: RTF 0.05x (extremely fast), 22-78% quality (unacceptable)
- small/int8/beam1: RTF 0.2x (fast), ~90% quality (acceptable)
- medium/int8/beam1: RTF 0.3x (balanced), ~95-100% quality (excellent)
- medium/int8/beam5: RTF 0.6x (slower), marginally better quality

**Memory Characteristics**:
- tiny: <1GB
- small: ~2.4GB
- medium: ~3.5GB peak
- Memory scales with model size, not beam size

**Decision**: medium/int8/beam1 selected as production default (quality prioritized, still 3x faster than audio).

### Lessons Learned

1. **Automated metrics insufficient**: Text similarity % missed nuances; manual transcript review essential
2. **Beam size impact minimal for Russian**: beam1 (greedy) vs beam5 showed little quality difference, but 2x speed difference
3. **Long audio challenges**: All local models showed quality degradation on 163s sample vs short clips
4. **Provider comparison value**: Testing openai-whisper proved faster-whisper medium superior, enabled confident removal
5. **Benchmark mode invaluable**: Parallel testing saved days of manual configuration switching

**Artifacts**:
- `memory-bank/benchmarks/fast-whisper.md`: Rollup summary
- `memory-bank/benchmarks/final-decision.md`: Decision rationale
- `docs/quality_compare/`: Raw benchmark results

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

### 13. **Version-Enriched Logging Pattern** (added 2025-11-03)
- **Where**: `VersionEnrichmentFilter` in `src/utils/logging_config.py`
- **Why**: Correlate logs with specific deployments for debugging and post-mortem analysis
- **Benefit**: Every log entry knows its version, enabling filtering by deployment
- **Implementation**:
  - Custom logging filter adds version and container_id to all log records
  - Version from `APP_VERSION` environment variable (set by CI/CD)
  - Short form (7 chars) for readability: 09f9af8
  - JSON formatter includes version in every log entry
- **Usage**: All logs automatically include version, no code changes needed
- **Pattern**: Cross-cutting concern handled at logging infrastructure level

### 14. **Size-Based Log Rotation Pattern** (added 2025-11-03)
- **Where**: `RotatingFileHandler` configuration in `src/utils/logging_config.py`
- **Why**: Predictable disk usage, logs kept longer when generation is low
- **Benefit**: No data loss from time-based rotation, clear disk usage ceiling
- **Implementation**:
  - app.log: 10MB per file, 5 backups (60MB max)
  - errors.log: 5MB per file, 5 backups (30MB max)
  - deployments.jsonl: Never rotated (minimal size growth)
- **User Requirement**: "Если мало логов, то пусть хранятся долго"
- **Pattern**: Resource management with user-friendly behavior

### 15. **Deployment Event Tracking Pattern** (added 2025-11-03)
- **Where**: `log_deployment_event()` in `src/utils/logging_config.py`
- **Why**: Track application lifecycle across deployments
- **Benefit**: JSONL format enables time-series analysis of deployments
- **Implementation**:
  - Separate file: `deployments.jsonl`
  - Events: startup (with config), ready, shutdown
  - One JSON object per line for easy streaming analysis
  - Includes full version, timestamp, container_id
- **Usage**: Called from `src/main.py` at lifecycle events
- **Pattern**: Append-only event log for audit trail

### 16. **Automatic Semantic Versioning Pattern** (added 2025-11-03)
- **Where**: `.github/workflows/build-and-tag.yml`
- **Why**: Remove manual version management overhead, user-friendly version numbers
- **Benefit**: Every merge to main gets readable version (v0.1.1), automatic GitHub releases
- **Implementation**:
  - Parse last tag: `git describe --tags --abbrev=0`
  - Increment patch version automatically
  - Create annotated git tag
  - Push tag to trigger deploy workflow
- **Version Format**: v{major}.{minor}.{patch}
- **Manual Override**: Create tag manually for minor/major bumps
- **Pattern**: Convention-based automation with escape hatch

### 17. **Separated Build and Deploy Workflow Pattern** (added 2025-11-03)
- **Where**: `.github/workflows/build-and-tag.yml` + `.github/workflows/deploy.yml`
- **Why**: Enable testing and verification between build and deploy stages
- **Benefit**: Deploy specific versions, rollback capability, safer releases
- **Implementation**:
  - **Build workflow**: Triggered by push to main
    - Test migrations
    - Build Docker image
    - Create version tag
    - Push image with version tag
  - **Deploy workflow**: Triggered by tag creation
    - Run migrations on VPS
    - Deploy specific version
    - Health checks
- **Rollback**: Redeploy previous tag or create new tag pointing to old commit
- **Pattern**: Two-phase deployment with artifact versioning

### 18. **Atomic Counter for Queue Position Pattern** (added 2025-11-19)
- **Where**: `QueueManager._total_pending` in `src/services/queue_manager.py`
- **Why**: `asyncio.Queue.qsize()` is unreliable because background worker immediately pulls items
- **Benefit**: Accurate queue position tracking regardless of worker timing
- **Implementation**:
  - Add `_total_pending: int = 0` counter in `__init__`
  - Increment BEFORE `put()`: `self._total_pending += 1; position = self._total_pending`
  - Decrement in `finally` block: `self._total_pending -= 1`
  - Return position from `enqueue()` for immediate use by caller
- **Problem Solved**: Race condition where position was recalculated after worker already consumed items
- **Key Insight**: Counter operations are atomic within same coroutine (no await between increment and assignment)
- **Pattern**: Atomic counter for tracking logical position vs physical queue state

### 19. **Unique File Naming with UUID Pattern** (added 2025-11-19)
- **Where**: `AudioHandler.download_voice_message()` and `download_from_url()` in `src/transcription/audio_handler.py`
- **Why**: Multiple users may forward same voice message (same file_id), causing filename collision
- **Benefit**: Each download creates unique file, preventing concurrent access conflicts
- **Implementation**:
  ```python
  unique_suffix = uuid.uuid4().hex[:8]  # 8 hex chars = 4 billion combinations
  audio_file = self.temp_dir / f"{file_id}_{unique_suffix}{extension}"
  ```
- **Problem Solved**: First request deletes file after processing, second request fails with FileNotFoundError
- **Key Insight**: file_id is unique per file in Telegram, but multiple users can access same file
- **Usage Pattern**: Always add UUID suffix when temporary files may be accessed concurrently by multiple requests for same resource
- **Pattern**: Resource isolation through unique naming

### 20. **Callback Pattern for Queue State Changes** (added 2025-11-19)
- **Where**: `QueueManager._on_queue_changed` callback in `src/services/queue_manager.py`
- **Why**: Need to update all users' messages when queue state changes (request starts processing)
- **Benefit**: Dynamic UI updates without polling, decoupled notification logic
- **Implementation**:
  - `set_on_queue_changed(callback)`: Register async callback
  - Callback called in `_process_request()` after moving request from pending to processing
  - Handler implements callback to iterate and update all pending messages
- **Usage**: `queue_manager.set_on_queue_changed(self._update_queue_messages)`
- **Pattern**: Observer pattern for queue state changes

### 21. **Dual List Tracking Pattern** (added 2025-11-19)
- **Where**: `_pending_requests` and `_processing_requests` in `src/services/queue_manager.py`
- **Why**: Need to calculate accurate wait times based on both queued and processing items
- **Benefit**: Accurate time estimation, proper accounting for all work in progress
- **Implementation**:
  ```python
  # In enqueue():
  self._pending_requests.append(request)

  # In _process_request():
  self._pending_requests.remove(request)
  self._processing_requests.append(request)

  # After completion:
  self._processing_requests.remove(request)
  ```
- **Time Calculation**:
  ```python
  processing_duration = sum(r.duration_seconds for r in self._processing_requests)
  pending_duration = sum(r.duration_seconds for r in pending_ahead)
  wait_time = (processing_duration + pending_duration) * rtf / max_concurrent
  ```
- **Pattern**: State tracking with separate collections for different lifecycle stages

### 22. **Dynamic Message Update Pattern** (added 2025-11-19)
- **Where**: `_update_queue_messages()` in `src/bot/handlers.py`
- **Why**: Keep users informed of queue progress without requiring them to check
- **Benefit**: Better UX, transparency about wait times
- **Implementation**:
  - Called when any request starts processing
  - Iterates through all pending requests
  - Calculates new position and times for each
  - Updates Telegram message via `edit_text()`
  - Handles errors gracefully (message deleted, etc.)
- **Message Format**:
  ```
  📋 В очереди: позиция {position}
  ⏱️ Ожидание в очереди: {wait_time}
  🎯 Обработка вашего сообщения: {processing_time}
  ```
- **Pattern**: Proactive notification with error tolerance

### 23. **Time Formatting with Appropriate Units** (added 2025-11-19)
- **Where**: Queue notification messages in `src/bot/handlers.py`
- **Why**: Times displayed should be easy to read at a glance
- **Benefit**: Better readability for users
- **Implementation**:
  ```python
  if time < 60:
      time_str = f"~{int(time)}с"
  else:
      minutes = int(time // 60)
      seconds = int(time % 60)
      time_str = f"~{minutes}м {seconds}с"
  ```
- **Usage**: Applied to both wait time and processing time displays
- **Pattern**: User-friendly formatting based on magnitude

### 24. **Hybrid Transcription Strategy Pattern** (added 2025-11-20)
- **Where**: `HybridStrategy` in `src/transcription/routing/strategies.py`
- **Why**: Balance speed and quality based on audio duration - long audio needs fast processing
- **Benefit**: 6x performance improvement for long audio while maintaining quality
- **Implementation**:
  - Short audio (<20s): Use quality model directly (medium/int8)
  - Long audio (≥20s): Use fast draft model (small/beam1) + LLM refinement
  - Methods: `select_provider()`, `get_model_for_duration()`, `requires_refinement()`
- **Performance**: 60s audio from 36s → ~6s (3s draft + 3s LLM)
- **Pattern**: Strategy pattern with duration-based routing

### 25. **LLM Post-Processing Pattern** (added 2025-11-20)
- **Where**: `LLMService` in `src/services/llm_service.py`, integrated in `handlers.py`
- **Why**: Improve quality of fast draft transcriptions without slow model inference
- **Benefit**: Better quality than draft alone, faster than quality model, cost-effective
- **Implementation**:
  - Draft transcription from fast model (small/beam1)
  - Send to LLM API (DeepSeek V3) for refinement
  - Retry logic with exponential backoff (3 attempts)
  - Graceful fallback to draft on any error
- **Cost**: ~$0.0002 per 60s audio (30x cheaper than OpenAI Whisper API)
- **Pattern**: Service layer with retry logic and graceful degradation

### 26. **Staged UI Updates Pattern** (added 2025-11-20)
- **Where**: Handler integration in `src/bot/handlers.py`
- **Why**: Keep users informed during multi-stage processing (draft → refinement)
- **Benefit**: Immediate feedback, transparency about what's happening
- **Implementation**:
  1. **Stage 1**: Show draft transcription immediately
     ```
     ✅ Черновик готов:
     [draft text]
     🔄 Улучшаю текст...
     ```
  2. **Stage 2**: Show final refined transcription
     ```
     ✨ Готово!
     [refined text]
     ```
- **Pattern**: Progressive disclosure - show partial results immediately, refine later

### 27. **Audio Preprocessing Pipeline Pattern** (added 2025-11-20)
- **Where**: `AudioHandler.preprocess_audio()` in `src/transcription/audio_handler.py`
- **Why**: Optimize audio for transcription (mono, speed adjustment) to improve quality or speed
- **Benefit**: Optional optimizations without blocking main flow, graceful fallback on errors
- **Implementation**:
  - Pipeline: Original → Mono conversion (optional) → Speed adjustment (optional)
  - Each step wrapped in try-except with fallback to previous file
  - ffmpeg-based transformations with validation
  - Cleanup of intermediate files
- **Configuration**: Disabled by default, opt-in via environment variables
- **Pattern**: Pipeline pattern with graceful degradation

### 28. **Abstract LLM Provider Pattern** (added 2025-11-20)
- **Where**: `LLMProvider` base class in `src/services/llm_service.py`
- **Why**: Support multiple LLM providers (DeepSeek, OpenAI, Anthropic) with same interface
- **Benefit**: Easy to add new providers, switch providers via configuration
- **Implementation**:
  ```python
  class LLMProvider(ABC):
      @abstractmethod
      async def refine_text(self, text: str, prompt: str) -> str:
          pass

      @abstractmethod
      async def close(self) -> None:
          pass

  class DeepSeekProvider(LLMProvider):
      # Implementation with httpx, tenacity retry logic
  ```
- **Factory**: `LLMFactory.create_provider()` instantiates based on configuration
- **Pattern**: Abstract base class + Factory pattern for pluggable providers

### 29. **Graceful Degradation for LLM Pattern** (added 2025-11-20)
- **Where**: `LLMService.refine_transcription()` and handler integration
- **Why**: LLM APIs can fail (timeout, rate limits, network errors) - must not block users
- **Benefit**: Always deliver transcription even if LLM fails, better UX than errors
- **Implementation**:
  - All LLM errors caught (timeout, HTTP errors, network errors, unexpected errors)
  - Automatic fallback to draft text on any error
  - Retry logic (3 attempts) before giving up
  - User sees draft immediately, refinement is bonus
- **Error Types Handled**: `LLMTimeoutError`, `LLMAPIError`, generic `Exception`
- **Pattern**: Fail-safe with automatic fallback

### 30. **Feature Flags for Production Safety Pattern** (added 2025-11-20)
- **Where**: `llm_refinement_enabled` setting in `src/config.py`
- **Why**: New features should be disabled by default for safe production rollout
- **Benefit**: Deploy code without activating feature, gradual rollout, easy rollback
- **Implementation**:
  - Feature disabled by default: `llm_refinement_enabled: bool = Field(default=False)`
  - Check at runtime: `if settings.llm_refinement_enabled: ...`
  - Enable for specific test users first
  - Monitor metrics before full rollout
- **Rollout Plan**: Deploy → Enable for test users → Monitor → Gradual rollout
- **Pattern**: Feature toggle for risk mitigation

## Development Workflow

### Git Strategy
**Workflow**: Feature Branch Workflow with Protected Main Branch (documented in `.github/WORKFLOW.md`)

**Branch Protection** (implemented 2025-10-19):
- Main branch is protected on GitHub
- All changes must go through Pull Requests
- CI checks must pass before merge allowed
- Prevents accidental direct commits to main

**Branch Structure**:
```
main (protected, PR-only)
  ├── feature/database-models ✅ merged
  ├── feature/whisper-service ✅ merged
  ├── feature/bot-handlers ✅ merged
  ├── feature/test-cicd ✅ merged
  └── feature/your-next-feature
```

**Commit Convention**: Conventional Commits format
- `feat:` - New functionality
- `fix:` - Bug fixes
- `refactor:` - Code refactoring
- `docs:` - Documentation
- `test:` - Tests
- `chore:` - Maintenance tasks

**PR Process**:
1. Create feature branch from `main`
2. Implement feature with regular commits
3. Push to GitHub for backup
4. Create PR when complete
5. Review and merge via GitHub
6. Delete feature branch

**Phase-Based Branching**:
- Phase 2: `feature/database-models`, `feature/whisper-service`
- Phase 3: `feature/queue-system`
- Phase 4: `feature/bot-handlers`
- Phase 5: `feature/integration`
- Phase 6: `feature/docker-deployment`

**Integration with Tools**:
- `/commit` slash command for git commits
- `gh pr create` for pull request creation
- Conventional commit messages for clear history

**Repository**: `konstantinbalakin/telegram-voice2text-bot`

### Development Cycle Pattern
```
1. Start: Review Memory Bank → Understand context
2. Plan: Break down task → Create todos
3. Branch: Create feature branch
4. Code: Implement → Test → Commit
5. Push: Regular pushes to GitHub (backup)
6. Document: Update Memory Bank, README, .env.example
7. PR: Create pull request with comprehensive summary
8. Auto-merge: Merge via gh pr merge (solo development)
9. Sync: git checkout main && git pull origin main
10. Update: Memory Bank reflects final state
```

**Key Principles**:
- Work in feature branches, never directly in `main`
- Regular commits with conventional format
- Push often for backup and visibility
- **Document before PR** - ensure Memory Bank is current
- PR-based code review (even solo development)
- **Auto-merge for speed** - `gh pr merge <PR> --merge --delete-branch`
- Memory Bank updates at significant milestones

**Documentation Commit Pattern** (NEW):
```bash
# After code + tests, before PR:
git add .claude/memory-bank/activeContext.md .claude/memory-bank/progress.md
git add README.md .env.example  # if changed
git commit -m "docs: update documentation after Phase X completion"
git push
```

**Why Document Before PR**:
- PR contains complete picture: code + tests + docs
- Documentation synchronized with code
- Future developers see current state
- Memory Bank ready for next Claude Code session

### CI/CD Pipeline (implemented 2025-10-19, optimized 2025-10-28)

**Platform**: GitHub Actions

**Architecture**: Two separate workflows for separation of concerns

#### CI Workflow (`.github/workflows/ci.yml`)
**Trigger**: On pull requests to `main` branch
**Purpose**: Quality gates before code merge

**Optimization** (2025-10-28): Conditional execution for docs-only changes
- Uses `tj-actions/changed-files@v45` to detect file changes
- Ignores: `memory-bank/**`, `*.md`, `docs/**`, `.claude/**`, `CLAUDE.md`
- Workflows always run (creates required status checks) but skip expensive steps when only docs changed
- Prevents PR merge blocking while saving CI minutes

**Steps**:
1. **Change Detection** (always runs)
   - Checkout code with full history
   - Run `changed-files` action to detect non-docs changes
   - Set output `any_changed` for conditional steps

2. **Environment Setup** (conditional: `if any_changed == 'true'`)
   - Ubuntu latest runner
   - Python 3.11
   - Poetry installation
   - Dependency caching (.venv cached by poetry.lock hash)

3. **Testing** (conditional)
   - `pytest` with coverage reporting
   - Coverage uploaded to Codecov
   - Dummy TELEGRAM_BOT_TOKEN for tests

4. **Code Quality Checks** (conditional, all must pass):
   - `mypy src/` - Type checking (strict mode)
   - `ruff check src/` - Linting
   - `black --check src/` - Formatting verification

**Fail Fast**: If any check fails, PR cannot be merged

**Smart Skipping**: Docs-only PRs complete successfully without running expensive operations

#### Build & Deploy Workflow (`.github/workflows/build-and-deploy.yml`)
**Trigger**: On push to `main` branch (after PR merge)
**Purpose**: Automated build and deployment

**Optimization** (2025-10-28): Conditional execution for docs-only merges
- Same `changed-files` detection as CI workflow
- Build job runs always but skips expensive steps when only docs changed
- Deploy job conditionally runs only if code changes detected
- Saves Docker Hub bandwidth and VPS resources for docs-only merges

**Build Stage** (conditional steps):
1. **Change Detection** (always runs)
   - Checkout code with full history
   - Run `changed-files` action
   - Export `any_changed` output for deploy job

2. **Build Steps** (conditional: `if any_changed == 'true'`)
   - Export Poetry dependencies → requirements.txt
   - Set up Docker Buildx
   - Login to Docker Hub (secrets: DOCKER_USERNAME, DOCKER_PASSWORD)
   - Build Docker image with cache
   - Push with two tags:
     - `{username}/telegram-voice2text-bot:latest` (stable)
     - `{username}/telegram-voice2text-bot:{commit-sha}` (versioned)
   - Use GitHub Actions cache for Docker layers

**Deploy Stage** (conditional: `if needs.build.outputs.any_changed == 'true'`):
1. SSH to VPS server (secrets: VPS_HOST, VPS_USER, VPS_SSH_KEY)
2. Pull latest code (for docker-compose.yml updates)
3. Create .env file with secrets from GitHub
4. Pull new Docker image by commit SHA
5. Tag as latest locally
6. Rolling update: `docker compose up -d --no-deps bot`
7. Health check verification (15s wait)
8. Cleanup old images (keep last 3)

**Skip Logic**: If only documentation changed, deploy stage doesn't run at all

**Zero Downtime Strategy**:
- Use `--no-deps` flag for isolated bot service update
- Health checks verify container is healthy before considering deployment successful
- Automatic rollback if health check fails

**Environment**: Uses GitHub "production" environment for secret management

### CI/CD Patterns

**Pattern 0: Optional Dependencies in CI/CD** (added 2025-10-29)
- **Issue**: Poetry optional dependencies not automatically included in exports
- **Symptom**: Docker images built without optional packages, causing runtime failures
- **Solution**: Explicitly include extras in all CI/CD poetry export commands
- **Example**: `poetry export -f requirements.txt -o requirements.txt --extras "faster-whisper"`
- **Critical**: Local scripts and CI/CD must use identical export commands
- **Detection**: Compare Docker image sizes - missing deps result in significantly smaller images

**Pattern 1: Fail Fast**
- Tests run first, before code quality checks
- Any failure stops the pipeline immediately
- Prevents wasted time on bad builds

**Pattern 2: Immutable Versioning**
- Every commit gets unique SHA-tagged Docker image
- Enables rollback to any previous version
- `latest` tag always points to most recent successful build

**Pattern 3: Secrets Management**
- All sensitive data in GitHub Secrets
- Never committed to repository
- Injected at runtime via environment variables

**Pattern 4: Caching Strategy**
- Poetry dependencies cached by poetry.lock hash
- Docker build layers cached in GitHub Actions
- Significantly faster builds (minutes vs tens of minutes)

**Pattern 5: Quality Gates**
- Protected branch enforces PR workflow
- CI checks must pass before merge
- No manual merge to main possible

**Pattern 6: Conditional Execution** (added 2025-10-28)
- Workflows always run to create required status checks
- Expensive operations skip when only docs changed
- Uses `tj-actions/changed-files` for smart detection
- Saves CI minutes and resources while maintaining merge requirements

### Deployment Automation Benefits

1. **Consistency**: Same process every time, no manual steps
2. **Speed**: Merge to main → production in ~10 minutes
3. **Safety**: Health checks catch failures, automatic rollback
4. **Traceability**: Every deployment tracked by commit SHA
5. **Reliability**: Tested process, no human error

## Logging and Observability Patterns (added 2025-11-03)

### Pattern 1: Version-Enriched Logging
**Problem**: Need to correlate logs with specific deployments for post-mortem analysis.

**Solution**: Custom logging filter that adds version and container_id to every log entry.

**Implementation**:
```python
class VersionEnrichmentFilter(logging.Filter):
    def filter(self, record):
        record.version = get_version()
        record.container_id = socket.gethostname()
        return True
```

**Benefits**:
- Every log entry knows its deployment version
- Can filter logs by specific version: `jq 'select(.version=="v0.1.1")' app.log`
- Enables multi-version debugging in staging/production
- Container ID helps with multi-instance deployments

**Example Log Entry**:
```json
{
  "timestamp": "2025-11-03T20:10:13.628064+00:00",
  "level": "INFO",
  "logger": "root",
  "version": "v0.0.1",
  "container_id": "3f33660445f8",
  "message": "Logging configured..."
}
```

### Pattern 2: Size-Based Log Rotation
**Problem**: Time-based rotation deletes logs even when generation is low.

**Decision**: Use size-based rotation ONLY (per user request: "Если мало логов, то пусть хранятся долго")

**Configuration**:
- `app.log`: 10MB per file, 5 backups → ~60MB max
- `errors.log`: 5MB per file, 5 backups → ~30MB max
- `deployments.jsonl`: Never rotated → ~365KB/year

**Benefits**:
- Logs persist longer when generation is low
- Predictable disk usage (~90MB max)
- No data loss from time-based expiry
- Low-traffic periods fully logged

**Implementation**:
```python
handler = RotatingFileHandler(
    filename="app.log",
    maxBytes=10_000_000,  # 10MB
    backupCount=5
)
```

### Pattern 3: Deployment Event Tracking
**Problem**: Need to understand deployment lifecycle and configuration changes.

**Solution**: Dedicated JSONL file for deployment events, never rotated.

**Events Tracked**:
1. **startup**: Bot starting with full configuration snapshot
2. **ready**: Bot fully initialized and accepting requests
3. **shutdown**: Graceful shutdown (when implemented)

**Example Deployment Log**:
```json
{
  "timestamp": "2025-11-03T20:10:13.629654+00:00",
  "event": "startup",
  "version": "v0.0.1",
  "container_id": "3f33660445f8",
  "config": {
    "bot_mode": "polling",
    "database_url": "/app/data/bot.db",
    "whisper_providers": ["faster-whisper"],
    "max_queue_size": 10,
    "max_concurrent_workers": 1
  }
}
```

**Benefits**:
- Full history of all deployments
- Configuration changes tracked over time
- Enables rollback decision support
- ~1KB per deployment, minimal disk usage

### Pattern 4: Structured JSON Logging
**Problem**: Plain text logs difficult to parse and analyze programmatically.

**Solution**: JSON-formatted logs with python-json-logger library.

**Benefits**:
- Easy parsing with jq: `cat app.log | jq 'select(.level=="ERROR")'`
- Machine-readable for log aggregation tools
- Structured context: additional fields without parsing
- Consistent format across services

**Example Analysis**:
```bash
# Count errors by logger
cat app.log | jq -r '.logger' | sort | uniq -c

# Filter logs by version
jq 'select(.version=="v0.0.1")' app.log

# Extract timestamps for specific events
jq -r 'select(.message | contains("Processing")) | .timestamp' app.log
```

### Pattern 5: Optional Remote Syslog
**Problem**: Want centralized logging without forcing complexity in MVP.

**Solution**: Optional syslog handler configuration via environment variables.

**Configuration**:
```bash
SYSLOG_ENABLED=true
SYSLOG_HOST=logs.papertrailapp.com
SYSLOG_PORT=514
```

**Benefits**:
- Easy integration with Papertrail, Loggly, etc.
- Opt-in: disabled by default for simplicity
- Same log format sent to both file and syslog
- Enables log aggregation as project grows

## Versioning and Release Patterns (added 2025-11-03)

### Pattern 1: Automatic Semantic Versioning
**Problem**: Manual version management is overhead, git SHA not user-friendly.

**Solution**: Automated semantic versioning with separate workflows.

**Architecture**:
```
Build & Tag Workflow (on push to main)
  ↓
1. Test migrations
2. Calculate next version (v0.1.0 → v0.1.1)
3. Build Docker image
4. Push with version tags
5. Create git tag
6. Create GitHub Release
  ↓ (tag pushed triggers next workflow)
Deploy Workflow (on tag push)
  ↓
1. Run migrations on VPS
2. Deploy specific version
3. Health checks
```

**Version Calculation**:
```bash
LAST_TAG=$(git describe --tags --abbrev=0 || echo "v0.0.0")
VERSION=${LAST_TAG#v}  # Remove 'v' prefix
IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"
NEW_PATCH=$((PATCH + 1))
NEW_VERSION="v${MAJOR}.${MINOR}.${NEW_PATCH}"
```

**Benefits**:
- Zero manual version management for patches
- User-friendly versions (v0.1.1 vs 09f9af8)
- Separation of build and deploy
- Testable between stages
- Full version history

### Pattern 2: Separated Build and Deploy Workflow
**Problem**: Combined workflow makes testing difficult and limits flexibility.

**Solution**: Two separate workflows with tag-based trigger.

**Advantages**:
1. **Testing**: Can build and test before deploying
2. **Rollback**: Can deploy any previous version manually
3. **Staging**: Can deploy same version to multiple environments
4. **Debugging**: Workflow failures isolated

**Implementation**:
- Build workflow: Creates version, builds image, pushes tag
- Tag push: Triggers deploy workflow automatically
- Deploy workflow: Can also be triggered manually via workflow_dispatch

### Pattern 3: workflow_dispatch for Manual Deployments
**Problem**: workflow_run trigger has limitations with tag references.

**Discovered Issue**: `workflow_run` receives `refs/heads/main` instead of tag, causing Docker image name issues.

**Solution**: Use `workflow_dispatch` for manual deployments:
```bash
gh workflow run deploy.yml -f version=v0.0.1
```

**Benefits**:
- Reliable deployment of any version
- Works around GitHub Actions security limitations
- Enables re-deployment of previous versions
- Full control over when deployment happens

**Pattern**:
```yaml
on:
  push:
    tags: ['v*.*.*']  # Automatic for manually created tags
  workflow_dispatch:  # Manual trigger
    inputs:
      version:
        description: 'Version tag to deploy (e.g., v0.1.0)'
        required: true
        type: string
```

### Pattern 4: Version-Tagged Docker Images
**Problem**: Need to deploy and rollback specific versions easily.

**Solution**: Multiple Docker image tags per build.

**Tags Created**:
- `konstantinbalakin/telegram-voice2text-bot:v0.1.1` (semantic version)
- `konstantinbalakin/telegram-voice2text-bot:09f9af8` (git SHA)
- `konstantinbalakin/telegram-voice2text-bot:latest` (most recent)

**Benefits**:
- Easy rollback: `docker pull ...bot:v0.1.0`
- Version history preserved
- Can compare versions easily
- Latest always available for testing

### Pattern 5: GitHub Releases for Changelog
**Problem**: Need user-facing changelog without manual work.

**Solution**: Automated GitHub Release creation on tag push.

**Release Contents**:
- Release notes with Docker pull commands
- Link to full changelog (git compare)
- Automated from commit messages
- Tagged with semantic version

**Benefits**:
- Automatic documentation of releases
- Users can see what changed
- Links to specific Docker images
- Historical record of changes

## GitHub Actions Workflow Patterns (added 2025-11-03)

### Pattern 1: Explicit Permissions for Tag Pushing
**Problem**: GitHub Actions can't push tags by default.

**Error**: `Permission to konstantinbalakin/telegram-voice2text-bot.git denied to github-actions[bot]`

**Solution**: Explicitly grant permissions in workflow:
```yaml
jobs:
  build:
    permissions:
      contents: write  # Push tags
      packages: write  # Push Docker images
```

**Key Learning**: Default `GITHUB_TOKEN` has read-only permissions for security. Must explicitly grant write access per job.

### Pattern 2: Workflow Trigger Limitations
**Problem**: Workflows triggered by `GITHUB_TOKEN` don't trigger other workflows (security feature).

**Impact**: Build & Tag workflow creates a tag, but Deploy workflow doesn't trigger automatically.

**Reason**: Prevents infinite workflow loops and security issues.

**Solutions**:
1. **workflow_dispatch**: Manual trigger with version input (WORKS)
2. **workflow_run**: Automatic trigger after workflow completes (HAS LIMITATIONS)
3. **PAT (Personal Access Token)**: Use instead of GITHUB_TOKEN (more permissive)

**Chosen**: workflow_dispatch for reliability and control.

### Pattern 3: workflow_run Limitations and Solution
**Issue**: `workflow_run` trigger receives branch reference instead of tag.

**Problem**:
```yaml
on:
  workflow_run:
    workflows: ["Build and Tag"]
    types: [completed]
```

**Result**: `GITHUB_REF=refs/heads/main` instead of `refs/tags/v0.1.1`

**Impact**: Docker image names become `...bot:refs/heads/main` (invalid)

**Solution (2025-11-04)**: Use `git describe --tags --abbrev=0` to get latest tag from repository
```yaml
- name: Extract version from tag
  id: version
  run: |
    if [ "${{ github.event_name }}" = "workflow_run" ]; then
      git fetch --tags
      VERSION=$(git describe --tags --abbrev=0)
    fi
```

**Requirements**:
- Need `fetch-depth: 0` in checkout step (full git history)
- Works because Build & Tag workflow pushes tag BEFORE workflow_run fires
- Enables fully automatic deployment without workflow_dispatch

**Documentation**: Added to troubleshooting in git-workflow.md

### Pattern 4: Iterative Workflow Testing
**Experience**: Required 5 workflow runs to identify and fix all issues.

**Issues Found**:
1. poetry.lock not synced (CI failed)
2. mypy type error (CI failed)
3. unused import (ruff failed)
4. black formatting (CI failed)
5. GitHub Actions permissions (deploy failed)
6. workflow_run limitations (deploy didn't trigger)

**Learning**: Test workflows incrementally, expect multiple iterations, document issues for future reference.
