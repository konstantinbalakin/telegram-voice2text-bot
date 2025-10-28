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
