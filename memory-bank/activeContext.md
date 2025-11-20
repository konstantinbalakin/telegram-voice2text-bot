# Active Context: Telegram Voice2Text Bot

## Current Status

**Phase**: Phase 8 - Hybrid Transcription Acceleration ✅ COMPLETE (2025-11-20)
**Date**: 2025-11-20
**Stage**: Production operational with hybrid transcription acceleration feature
**Branch**: feature/hybrid-transcription (PR #44 created, ready for merge)
**Production Version**: v0.0.3+ (hybrid feature in PR, pending merge and deployment)
**Production Status**: ✅ OPERATIONAL - All systems stable, hybrid transcription feature ready for deployment
**Completed**: Initial deployment, database fix, DNS configuration, swap setup, CI/CD path filtering, documentation reorganization, production bug fix, queue-based concurrency control, database migration system, production limit optimization, long transcription message splitting, **centralized logging ✅**, **automatic semantic versioning ✅**, **workflow fixes ✅**, **fully automatic deployment ✅**, **queue position calculation fix ✅**, **file naming conflict fix ✅**, **dynamic queue notifications ✅**, **hybrid transcription acceleration ✅**
**Next Phase**: Manual testing, gradual rollout, performance monitoring

## Production Configuration Finalized ✅

**Decision**: `faster-whisper / medium / int8 / beam1`

After comprehensive manual analysis of benchmark transcripts (30+ configurations tested across 7s, 24s, 163s audio samples):

- **Performance on Production VPS (4 CPU + 3GB RAM)**:
  - RTF ~0.6x for medium model (60s audio → ~36s processing)
  - RTF ~0.45x achievable with optimization
- **Quality**: Excellent for Russian language, good accuracy on long informal speech
- **Resources**: ~2GB RAM peak for medium model
- **Tradeoff**: Prioritized quality over speed for better user experience

Alternative faster configurations (tiny, small) showed unacceptable quality degradation (22-78% similarity on some samples).

📄 Full analysis: `memory-bank/benchmarks/final-decision.md`

## Recent Changes

### QUEUE-BASED CONCURRENCY CONTROL IMPLEMENTATION ✅ (2025-10-29)
**Achievement**: Complete rewrite of request handling to prevent crashes and improve user experience

**Problem Solved**:
- Bot crashed when processing 4-minute audio file on 2 CPU / 2 GB RAM VPS
- No concurrency controls → multiple simultaneous transcriptions exhausted resources
- No user feedback during processing
- No duration limits → resource exhaustion
- No analytics on request lifecycle

**Solution Implemented** (6 phases, commits: 8eea54f, f6e1d5c):

**Phase 1: Database Migration**
- Added `updated_at` column for lifecycle tracking
- Added `transcription_length` (int) instead of `transcription_text` for privacy
- Made `voice_duration_seconds` and `model_size` nullable for staged writes
- Migration: `alembic/versions/a9f3b2c8d1e4_*.py`

**Phase 2: Repository Updates**
- Refactored `UsageRepository` with `create()` and `update()` methods
- Three-stage lifecycle: download → processing → complete
- Privacy-friendly: only store transcription length, not text

**Phase 3: Queue Manager** (`src/services/queue_manager.py`)
- FIFO queue with configurable size (default: 50)
- Semaphore-based concurrency control (default: max_concurrent=1)
- Background worker with graceful error handling
- Request/response tracking with timeout support
- Non-blocking enqueue operation

**Phase 4: Progress Tracker** (`src/services/progress_tracker.py`)
- Live progress bar updates every 5 seconds:
  ```
  🔄 Обработка [████████░░░░] 40%
  ⏱️ Прошло: 8с | Осталось: ~12с
  ```
- RTF-based time estimation (default: 0.3x)
- Telegram rate limit handling (RetryAfter, TimedOut)
- Visual feedback during transcription

**Phase 5: Configuration Updates** (`src/config.py`)
- `max_voice_duration_seconds`: 300 → **120** (2 minutes)
- `max_queue_size`: 100 → **10** (final production value, optimized 2025-10-29)
- `max_concurrent_workers`: 3 → **1** (sequential processing)
- `progress_update_interval`: **5** seconds
- `progress_rtf`: **0.3** (for estimation)

**Phase 6: Handler Integration** (`src/bot/handlers.py`)
- Duration validation: reject files > 120 seconds
- Queue capacity check: reject when queue full
- Staged database writes:
  - Stage 1: Create record on download
  - Stage 2: Update with duration after download
  - Stage 3: Update with results after transcription
- Queue position feedback to users
- Estimated wait time display
- Graceful error handling

**User Experience Improvements**:

*Before*:
- ❌ No feedback during processing
- ❌ Crashes on long files or concurrent requests
- ❌ No queue management

*After*:
- ✅ Live progress bar every 5 seconds
- ✅ Duration limit: 120s with clear rejection message
- ✅ Queue position: "📋 В очереди: позиция 3"
- ✅ Estimated wait time: "⏱️ Примерное время ожидания: ~60с"
- ✅ Sequential processing prevents crashes

**New User Flow**:
```
1. 📥 Загружаю файл...
2. 📋 В очереди: позиция 3 (if queued)
   ⏱️ Примерное время ожидания: ~60с
3. 🔄 Обработка [████████░░░░] 40%
   ⏱️ Прошло: 8с | Осталось: ~12с
4. ✅ Готово!
   [transcription text]
```

**Files Created**:
- `src/services/__init__.py`
- `src/services/queue_manager.py`
- `src/services/progress_tracker.py`
- `alembic/versions/a9f3b2c8d1e4_add_updated_at_and_transcription_length.py`
- `memory-bank/plans/2025-10-29-queue-based-concurrency-plan.md`

**Files Modified**:
- `src/storage/models.py` - Usage model with staged fields
- `src/storage/repositories.py` - create/update methods
- `src/bot/handlers.py` - Complete refactor with queue integration
- `src/config.py` - New queue and progress settings
- `src/main.py` - QueueManager initialization

**Production Configuration** (deployed 2025-10-29):
```bash
# Production .env values
MAX_VOICE_DURATION_SECONDS=120
MAX_QUEUE_SIZE=10  # Optimized from initial 50
MAX_CONCURRENT_WORKERS=1
PROGRESS_UPDATE_INTERVAL=5
PROGRESS_RTF=0.3
```

**Deployment Status**:
- ✅ Code merged to main
- ✅ Database migration applied (a9f3b2c8d1e4)
- ✅ CI/CD pipeline deployed to production
- ✅ Environment variables updated
- ✅ Bot operational with queue system
- ⏳ Real-world usage monitoring ongoing

**Branch**: `main`
**Status**: ✅ Deployed to production
**Documentation**: `memory-bank/plans/2025-10-29-queue-based-concurrency-plan.md`

**Key Pattern Established**: Queue-based request management with progress feedback is essential for resource-constrained deployments. Sequential processing (max_concurrent=1) prevents crashes while maintaining acceptable UX through live progress updates.

### CRITICAL BUG FIX: faster-whisper Missing from Docker Image ✅ (2025-10-29)
**Impact**: Production bot was crashing on startup with `ModuleNotFoundError: No module named 'faster_whisper'`

**Root Cause Analysis**:
1. In `pyproject.toml`, `faster-whisper` marked as `optional = true` dependency
2. Local `requirements.txt` was correct (generated with `--extras "faster-whisper"`)
3. **CI/CD workflow (.github/workflows/build-and-deploy.yml:51) was exporting requirements.txt WITHOUT `--extras` flag before Docker build**
4. Docker images built without `faster-whisper` package
5. Container crashed on startup when importing `faster_whisper` module

**Symptoms**:
- Container status: `Restarting (1)` - infinite restart loop
- Docker image size: 614 MB (vs normal ~1 GB)
- Logs: `ModuleNotFoundError: No module named 'faster_whisper'`

**Fix** (#19):
```diff
- poetry export --without dev -f requirements.txt -o requirements.txt
+ poetry export --without dev -f requirements.txt -o requirements.txt --extras "faster-whisper"
```

**Verification**:
- ✅ Build succeeded with correct dependencies
- ✅ Docker image: 614 MB → 1.03 GB (correct size)
- ✅ Container status: `healthy`
- ✅ FasterWhisper model initialized successfully
- ✅ Bot responding to messages

**Key Lesson**: When using optional dependencies in Poetry, CI/CD must explicitly include extras in export command. Local development scripts were correct, but CI/CD workflow diverged.

**Files Modified**: `.github/workflows/build-and-deploy.yml`

### Documentation Reorganization ✅ (2025-10-28)
**Achievement**: Complete documentation restructuring for better navigation and reduced redundancy

**Changes**:
- **New Structure**: Hierarchical `docs/` organization
  - `docs/getting-started/` - Installation, configuration, quick start (3 new files)
  - `docs/development/` - Architecture, testing, git workflow, dependencies (4 files)
  - `docs/deployment/` - Docker, VPS setup, CI/CD (3 files)
  - `docs/research/benchmarks/` - Performance benchmarks (5 files moved)
- **New Documentation**:
  - `docs/README.md` - Central navigation index
  - `docs/deployment/docker.md` - Docker deployment guide
  - `docs/development/architecture.md` - System architecture documentation
  - `docs/getting-started/*` - Installation, configuration, quick start guides
- **Files Moved**: DEPLOYMENT.md, VPS_SETUP.md, TESTING.md, WORKFLOW.md, DEPENDENCIES.md, benchmarks
- **README.md**: Reduced from 461 to 229 lines, focused on project overview
- **Requirements Simplification**: Merged `requirements-docker.txt` into single `requirements.txt`
- **Removed**: `run.sh` (replaced with documentation)

**Benefits**:
- Clear hierarchy organized by audience (getting started → development → deployment)
- Eliminated content overlap and redundancy
- Easier navigation with central index
- Reduced root directory clutter
- Single source of truth for requirements
- Scalable structure for future growth

**Implementation Plan**: `memory-bank/plans/2025-10-29-docs-reorganization-plan.md`

### CI/CD Path Filtering Optimization ✅ (2025-10-28)
**Achievement**: Workflows now intelligently skip operations for documentation-only changes

**Problem Solved**: Previously used `paths-ignore` which prevented workflows from running entirely for docs-only PRs. This caused GitHub's required status checks to never be created, blocking PR merges even when no code was changed.

**Solution Implemented** (#15):
- Replaced `paths-ignore` with `tj-actions/changed-files@v45` action
- Added conditional steps (`if: steps.changed-files.outputs.any_changed == 'true'`) to expensive operations
- Ensured workflows always run (status checks created) but skip heavy steps when only docs change

**Files Modified**:
- `.github/workflows/ci.yml`: Conditional test execution, linting, type checking
- `.github/workflows/build-and-deploy.yml`: Conditional build and deploy jobs

**Benefits**:
- ✅ Required status checks always created (no merge blocks)
- ✅ CI minutes saved on docs-only changes (skips tests, build, deploy)
- ✅ Workflows complete successfully even when skipping steps
- ✅ Maintains code quality gates for actual code changes

**Pattern**: Conditional execution with always-run workflows for required status checks

### VPS Deployment SUCCESS ✅ (2025-10-27)
**Achievement**: Bot successfully deployed and operational on 1GB VPS

**Issues Resolved**:
1. **Database Directory Issue** (#11)
   - Error: `sqlite3.OperationalError: unable to open database file`
   - Fix: Added directory creation in `init_db()` (src/storage/database.py:72-87)
   - Handles volume mount replacing container directories

2. **DNS Resolution Failure** (#12)
   - Error: `failed to lookup address information` for transfer.xethub.hf.co
   - Fix: Added DNS servers in docker-compose.prod.yml (VPS host + Google DNS)
   - Enables HuggingFace model downloads

3. **OOM Killer (Exit Code 137)**
   - Issue: Container killed during model loading (medium requires ~1.3GB peak)
   - Fix: Created 1GB swap file on VPS
   - Result: **Bot stable and healthy**

**Production Metrics** (2025-10-27):
- **Memory Usage**: 516 MB RAM + 755 MB swap = **1.27 GB total**
- **Model**: medium/int8 successfully loaded
- **Status**: Container healthy, bot responding
- **Performance**: RTF **3.04x** (9s audio → 27s processing)
  - 10x slower than local benchmark (0.3x)
  - Bottleneck: 1 vCPU + heavy swap usage

### Performance Gap Identified 🎯
**Current**: RTF 3.04x (3x slower than audio)
**Target**: RTF 0.3x (3x faster than audio, as measured locally)
**Gap**: **10x performance difference** vs local machine

**Root Causes**:
1. **Swap bottleneck**: 755 MB active swap usage severely degrades I/O
2. **Limited CPU**: 1 vCPU vs multi-core local machine
3. **Resource contention**: System using swap for model data access

**Next Steps**: Systematically test different VPS configurations

### Provider Architecture Cleanup ✅
- **Removed**: openai-whisper provider (original Whisper)
  - Deleted: `src/transcription/providers/whisper_provider.py`
  - Deleted: `tests/unit/test_whisper_service.py`
  - Removed from factory, router, all imports

- **Dependencies Optimized**:
  - Removed: `openai-whisper`, `torch` from pyproject.toml
  - `requirements-docker.txt`: 75 → 50 dependencies (~2-3GB Docker image savings)
  - Deleted: `requirements-full.txt`, `docker-compose.prod.yml` (obsolete)

- **Updated Defaults**:
  - `FASTER_WHISPER_MODEL_SIZE`: base → **medium**
  - `FASTER_WHISPER_BEAM_SIZE`: 5 → **1** (greedy decoding, faster)
  - All documentation updated with production benchmarks

- **Provider Tests Added**:
  - `tests/unit/test_faster_whisper_provider.py` (6 tests)
  - `tests/unit/test_openai_provider.py` (7 tests)
  - All 45 unit tests passing ✅

### Quality Assurance ✅
- ✅ mypy: No type errors
- ✅ ruff: All checks passed
- ✅ black: Code formatted
- ✅ pytest: 45/45 tests passing

### NEW: Database Migration System ✅ (2025-10-29)
**Achievement**: Seamless database migration deployment system

**Implementation** (commit 5c4cc5a):

**1. Automated Migration Testing in CI**
- New `test-migrations` job in GitHub Actions workflow
- Tests fresh database migration (from scratch)
- Tests upgrade/downgrade cycle for reversibility
- Tests application startup after migration
- Runs in parallel with build job

**2. Production Migration Job**
- New `migrate` job between build and deploy
- SSH to VPS and applies migrations before code update
- Automatic rollback on migration failure (downgrade -1)
- Stops deployment if migration fails
- Shows migration status before/after

**3. Health Check System**
- New `src/health_check.py` script
- Checks database connectivity
- Verifies schema version matches HEAD
- Used by docker-compose health check
- Prevents unhealthy containers from running

**4. Updated init_db() Function**
- Removed `create_all()` (doesn't work with migrations)
- Added migration version verification
- Logs current schema revision on startup
- Raises error if schema out of date
- Prevents bot from starting with wrong schema

**5. Comprehensive Documentation**
- `docs/development/database-migrations.md` - Developer guide (creating and testing migrations)
- `docs/deployment/migration-runbook.md` - Operations runbook (manual procedures, rollback, emergency)
- Updated `docs/deployment/vps-setup.md` with Phase 6.5 (migration management)

**Deployment Flow**:
```
push to main
  ↓
test-migrations (parallel with build)
  ↓
build (Docker image)
  ↓
migrate (apply migrations on VPS)
  ↓ (if success)
deploy (restart bot)
  ↓
health check (verify schema)
```

**Rollback Strategy**: If migration fails → automatic `alembic downgrade -1` → deployment stops → bot continues on old version

**Status**: ✅ Operational since 2025-10-29, tested with production migration a9f3b2c8d1e4

### PRODUCTION LIMIT OPTIMIZATION ✅ (2025-10-29)
**Achievement**: Fine-tuned queue limits for 1GB VPS constraints (PR #25)

**Changes**:
- `MAX_QUEUE_SIZE`: 100 → 50 → **10** (final)
- `MAX_CONCURRENT_WORKERS`: 3 → **1** (maintained)
- `MAX_VOICE_DURATION_SECONDS`: 300 → **120** (maintained)

**Rationale**:
- Conservative approach for resource-constrained 1GB RAM + 1 vCPU VPS
- Prevents memory exhaustion with sequential processing
- Queue size of 10 provides adequate buffering without excessive memory overhead
- Maintains acceptable UX through progress feedback

**Deployment**: Automated via CI/CD, environment variables updated in GitHub Actions

**Status**: ✅ Deployed and operational

### LONG TRANSCRIPTION MESSAGE SPLITTING ✅ (2025-10-30)
**Achievement**: Automatic splitting of long transcriptions to handle Telegram's 4096 character limit

**Problem Encountered**:
- Telegram limits messages to 4096 characters
- 31-minute voice message produced 23,676 character transcription
- Bot crashed with `telegram.error.BadRequest: Message is too long`
- Critical bug blocking users from transcribing longer messages

**Solution Implemented** (commit 0906229):

**1. Smart Text Splitting Function**
- Added `split_text()` function in `src/bot/handlers.py`
- Reserves 50 characters for message headers
- Effective max: 4046 characters per chunk
- Smart boundary detection (paragraph → newline → sentence → word → force)
- Guarantees no chunk exceeds 4096 chars including header

**2. Updated Data Model**
- Added `user_message: Message` to `TranscriptionRequest`
- Enables proper reply threading for multi-message responses
- Modified `src/services/queue_manager.py`

**3. Dynamic Message Handling**
- Short transcriptions (≤4096): Edit status message (no change)
- Long transcriptions (>4096): Delete status message + send numbered parts
  ```
  📝 Часть 1/6
  [chunk 1]

  📝 Часть 2/6
  [chunk 2]
  ...
  ```
- 0.1s delay between messages to avoid rate limits

**Production Testing**:
- ✅ 31-minute voice (1885s) → 23,676 chars
- ✅ Split into 6 messages successfully
- ✅ Processing time: 559s (RTF 0.30x)
- ✅ All messages delivered without errors

**Impact**:
- ✅ Bot can now handle any length voice message
- ✅ Clean UX with numbered message parts
- ✅ No data loss or truncation
- ✅ Graceful edge case handling

**Files Modified**:
- `src/bot/handlers.py` (90 lines added: split_text + multi-message logic)
- `src/services/queue_manager.py` (1 line: user_message field)

**Status**: ✅ Tested locally, ready for production push

### Phase 7: Centralized Logging & Automatic Versioning ✅ COMPLETE (2025-11-03)
**Achievement**: Full observability with version tracking and automated semantic versioning

**Problem Solved**:
- No logs preserved across container rebuilds during deployments
- Git SHA version identifiers not user-friendly
- No correlation between logs and deployed versions
- Manual version management required

**Solution Implemented** (2 major features):

#### Feature 1: Centralized Logging System

**1. Logging Infrastructure** (`src/utils/logging_config.py`, 233 lines)
- **VersionEnrichmentFilter**: Custom filter adds version and container_id to all log records
- **CustomJsonFormatter**: JSON formatter with ISO timestamps and structured context
- **setup_logging()**: Configures file handlers with rotation, optional remote syslog
- **log_deployment_event()**: Records deployment lifecycle (startup, ready, shutdown)

**2. Log Files**:
- **app.log**: All INFO+ logs in JSON format
  - **Size-based rotation**: 10MB per file, keeps 5 backups
  - Total: ~60MB max (app.log + app.log.1-5)
  - Structure: timestamp, level, logger, version, container_id, message, context
- **errors.log**: ERROR/CRITICAL logs only
  - **Size-based rotation**: 5MB per file, keeps 5 backups
  - Total: ~30MB max
- **deployments.jsonl**: Deployment events
  - **Never rotated**: JSONL format, one event per line
  - Tracks: startup (with full config), ready, shutdown
  - ~1KB per deployment, ~365KB/year

**3. Version Tracking**:
- `APP_VERSION` environment variable set by CI/CD (git SHA)
- Short form (7 chars) included in every log entry
- Enables filtering logs by specific deployment
- Container ID tracking for multi-instance deployments

**4. Integration Points**:
- `src/main.py`: Logging initialization, deployment events
- `docker-compose.prod.yml`: Volume mount for log persistence (`./logs:/app/logs`)
- `.github/workflows/deploy.yml`: APP_VERSION passed from git tag

**5. Configuration**:
```python
# Environment Variables
APP_VERSION=<git-tag>  # Set by CI/CD
LOG_DIR=/app/logs
LOG_LEVEL=INFO
SYSLOG_ENABLED=false  # Optional
SYSLOG_HOST=  # Optional (e.g., logs.papertrailapp.com)
SYSLOG_PORT=514  # Optional
```

**6. Documentation**:
- `docs/development/logging.md` (347 lines): Complete logging guide
  - Log file formats and rotation strategy
  - Configuration and usage
  - Searching and analyzing logs with jq
  - Remote syslog setup (Papertrail)
  - Troubleshooting

**Rotation Strategy Decision**:
- **Size-based only** (NOT time-based): "Если мало логов, то пусть хранятся долго"
- If few logs generated → files kept for weeks/months
- Predictable disk usage: ~90MB max total
- No data loss from time-based rotation

**Files Created**:
- `src/utils/logging_config.py`
- `docs/development/logging.md`
- `memory-bank/plans/2025-11-03-centralized-logging.md` (implementation plan)

**Files Modified**:
- `pyproject.toml` - Added `python-json-logger = "^4.0.0"` dependency
- `src/main.py` - Logging setup, deployment event tracking
- `docker-compose.prod.yml` - LOG_DIR, SYSLOG_* environment variables
- `docs/README.md` - Added logging documentation link

**Key Benefit**: Full traceability - every log entry knows its version, enabling post-mortem analysis of any deployment

#### Feature 2: Automatic Semantic Versioning

**Problem**: Git SHA (09f9af8) not user-friendly for tracking releases

**Solution**: Automatic semantic versioning with separate build and deploy workflows

**1. Build & Tag Workflow** (`.github/workflows/build-and-tag.yml`)
- **Trigger**: Push to main (after PR merge)
- **Steps**:
  1. Run database migration tests (fresh DB, upgrade/downgrade cycle, app startup)
  2. Calculate next version:
     ```bash
     LAST_TAG=$(git describe --tags --abbrev=0 || echo "v0.0.0")
     VERSION=${LAST_TAG#v}  # Remove 'v' prefix
     IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"
     NEW_PATCH=$((PATCH + 1))
     NEW_VERSION="v${MAJOR}.${MINOR}.${NEW_PATCH}"
     ```
  3. Build Docker image
  4. Export requirements with extras: `poetry export --extras "faster-whisper"`
  5. Push to Docker Hub with multiple tags:
     - `konstantinbalakin/telegram-voice2text-bot:$NEW_VERSION` (e.g., v0.1.1)
     - `konstantinbalakin/telegram-voice2text-bot:${{ github.sha }}`
     - `konstantinbalakin/telegram-voice2text-bot:latest`
  6. Create annotated git tag: `git tag -a "$NEW_VERSION" -m "Release $NEW_VERSION"`
  7. Push tag to GitHub
  8. Create GitHub Release

**2. Deploy Workflow** (`.github/workflows/deploy.yml`)
- **Trigger**: Tag creation (refs/tags/v*.*.*)
- **Steps**:
  1. **Migrate Job** (runs first):
     - Extract version from tag
     - SSH to VPS
     - Checkout tagged version
     - Check current database revision
     - Handle existing DB without alembic version (stamp to initial revision)
     - Run `alembic upgrade head`
     - Automatic rollback on failure: `alembic downgrade -1`
     - Abort deployment if migration fails
  2. **Deploy Job** (runs after migrate succeeds):
     - Extract version from tag
     - SSH to VPS
     - Checkout tagged version
     - Create .env with production configuration
     - Pull Docker image by version tag
     - Rolling update: `docker compose up -d --no-deps bot`
     - Health check verification (15s wait)
     - Image cleanup (keep last 3 versions)

**3. Version Format**:
- **Automatic patch versions**: v0.1.0 → v0.1.1 → v0.1.2 (every merge to main)
- **Manual minor/major versions**:
  ```bash
  git tag -a v0.2.0 -m "Release v0.2.0: Add quota system"
  git push origin v0.2.0  # Triggers deployment
  ```

**4. Workflow Separation**:
```
PR merged to main
  ↓
Build & Tag Workflow
  - Test migrations
  - Build image
  - Create v0.1.1 tag
  - Push to Docker Hub
  - Create GitHub Release
  ↓ (tag created)
Deploy Workflow (triggered by tag)
  - Run migrations on VPS
  - Deploy v0.1.1
  - Health checks
  ↓
Production running v0.1.1
```

**5. Initial Version**:
- Created `v0.1.0` tag at commit 09f9af8
- Next merge to main will create `v0.1.1` automatically

**6. Documentation**:
- `docs/development/git-workflow.md` - Added comprehensive versioning section (517 lines total):
  - Automatic versioning workflow
  - Creating manual minor/major versions
  - Viewing versions and rollback procedures
  - Docker image tagging strategy
  - Troubleshooting version issues

**Files Created**:
- `.github/workflows/build-and-tag.yml`
- `.github/workflows/deploy.yml`
- Git tag: `v0.1.0` (initial version)

**Files Modified**:
- `.github/workflows/build-and-deploy.yml` → `.github/workflows/build-and-deploy.yml.old` (disabled)
- `docs/development/git-workflow.md` - Added "Versioning and Releases" section

**Key Benefits**:
- ✅ User-friendly version numbers (v0.1.0 instead of 09f9af8)
- ✅ Automatic patch version increments
- ✅ Separation of build and deploy for testing
- ✅ Automated GitHub Releases with changelog
- ✅ Version-tagged Docker images for rollback
- ✅ Full version history: `git tag -l "v*"`

**Deployment Status**:
- ✅ Both systems implemented and tested
- ✅ Initial version v0.0.1 created and deployed
- ✅ Documentation complete
- ✅ Logging system active on production VPS
- ✅ Logs being collected successfully with version tracking
- ✅ Workflow fixes deployed (PRs #30, #31, #32)
- ✅ Fully automatic deployment working (v0.0.3)

**Production Verification** (2025-11-03):
- ✅ Version v0.0.1 running on VPS
- ✅ Logs directory created: `/opt/telegram-voice2text-bot/logs/`
- ✅ Log files:
  - `app.log` (9.3KB) - All logs with version enrichment
  - `errors.log` (0KB) - No errors yet
  - `deployments.jsonl` (586B) - Startup and ready events
- ✅ Every log entry includes version "v0.0.1" and container_id
- ✅ Deployment events recorded with full configuration
- ✅ Docker container: `kosbalakin/telegram-voice2text-bot:v0.0.1`
- ✅ Container status: `healthy`

**Workflow Improvements** (PRs #30, #31, #32):
- PR #30: Added `contents: write` and `packages: write` permissions to Build & Tag workflow
- PR #31: Added `workflow_run` and `workflow_dispatch` triggers to Deploy workflow
- PR #32: ✅ SOLVED automatic deployment issue
  - Problem: `workflow_run` receives `refs/heads/main` instead of tag
  - Solution: Get latest tag via `git describe --tags --abbrev=0` for workflow_run trigger
  - Result: Fully automatic deployment working (v0.0.3 deployed successfully)

**Key Pattern Established**: Centralized logging with version tracking is essential for production observability. Size-based log rotation ensures logs persist longer when generation is low, while automatic semantic versioning provides user-friendly release tracking without manual version management. For GitHub Actions: when `workflow_run` has limitations, use `git describe --tags --abbrev=0` to get latest tag instead of relying on GITHUB_REF.

### Phase 7.2: Fully Automatic Deployment Pipeline ✅ COMPLETE (2025-11-04)
**Achievement**: Resolved workflow_run limitations to achieve fully automatic CI/CD pipeline without manual intervention

**Problem Encountered** (after Phase 7.1):
- User requirement: "не, погоди. Я хотел, чтобы было все автоматически без ручных вмешательств"
- workflow_run trigger receives `refs/heads/main` instead of tag reference
- This caused Docker image naming issues: `konstantinbalakin/telegram-voice2text-bot:refs/heads/main` (invalid)
- Manual workaround (workflow_dispatch) was acceptable but not fully automatic
- User expectation: **Merge to main → automatic production deploy** with zero manual steps

**Solution Implemented** (PR #32):

**1. Version Extraction Logic in Deploy Workflow**
- Modified `.github/workflows/deploy.yml` to handle all trigger types
- Added conditional version extraction based on `github.event_name`:
  ```yaml
  - name: Extract version from tag
    id: version
    run: |
      if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
        VERSION="${{ github.event.inputs.version }}"
      elif [ "${{ github.event_name }}" = "push" ]; then
        VERSION=${GITHUB_REF#refs/tags/}
      else
        # workflow_run - get latest tag from repository
        git fetch --tags
        VERSION=$(git describe --tags --abbrev=0)
      fi
  ```

**2. Key Insight**:
- `workflow_run` trigger doesn't provide tag reference in GITHUB_REF
- Solution: Use `git describe --tags --abbrev=0` to get latest tag from repository
- This works because Build & Tag workflow creates and pushes tag BEFORE triggering deploy

**3. Additional Changes**:
- Added `fetch-depth: 0` to checkout steps (need full history for git describe)
- Added success check: `if: ${{ github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success' }}`
- Prevents deployment if build failed

**Testing**:
- ✅ v0.0.2 deployment successful (initial test)
- ✅ v0.0.3 deployment successful (production verification)
- ✅ Both migrate and deploy jobs ran automatically
- ✅ Container healthy, bot operational
- ✅ No manual intervention required

**Deployment Flow (Fully Automatic)**:
```
PR merged to main
  ↓
Build & Tag Workflow
  - Test migrations
  - Build Docker image
  - Create v0.0.3 tag
  - Push tag to GitHub
  ↓ (triggers workflow_run)
Deploy Workflow (automatic)
  - Extract version via git describe
  - Run migrations on VPS
  - Deploy v0.0.3
  - Health checks
  ↓
Production running v0.0.3
```

**Files Modified**:
- `.github/workflows/deploy.yml` - Added version extraction logic, fetch-depth, success check

**Impact**:
- ✅ Zero manual intervention required
- ✅ Main branch is deployable source of truth
- ✅ Full automation: PR merge → production deploy
- ✅ Version tracking maintained
- ✅ Rollback still possible via workflow_dispatch

**Key Pattern Established**: For GitHub Actions workflow_run limitations, use `git describe --tags --abbrev=0` to retrieve the latest tag created by previous workflow. This enables fully automatic deployment pipelines without manual triggers.

**Status**: ✅ Deployed and operational, v0.0.3 running in production

### Phase 7.3: Production Bug Fixes ✅ COMPLETE (2025-11-19)
**Achievement**: Fixed two critical bugs affecting queue position display and concurrent file downloads

**Bug 1: Queue Position Always Showing "1"**

**Problem**: When multiple audio files were sent in sequence, all queued messages displayed "📋 В очереди: позиция 1" instead of their actual positions (2, 3, etc.).

**Root Cause Analysis**:
- The `enqueue()` method returned the correct position, but the handler was recalculating it using `get_queue_depth()`
- Race condition: by the time `get_queue_depth()` was called, the worker had already pulled items from the queue
- `qsize()` is unreliable because the background worker immediately empties the queue

**Solution Implemented**:
1. Added `_total_pending` counter in `QueueManager` class
2. Counter increments BEFORE `put()` to get correct position atomically
3. Counter decrements in `finally` block after request completes
4. Handler now uses the position returned by `enqueue()` directly

**Files Modified**:
- `src/services/queue_manager.py`:
  ```python
  # In __init__:
  self._total_pending: int = 0

  # In enqueue():
  self._total_pending += 1
  position = self._total_pending
  await self._queue.put(request)
  return position

  # In _process_request() finally block:
  self._total_pending -= 1
  ```
- `src/bot/handlers.py`: Use returned position instead of recalculating

**Bug 2: FileNotFoundError with Concurrent Users**

**Problem**: When two users forwarded the same voice message, the second user got `FileNotFoundError` because the file was already deleted.

**Root Cause Analysis**:
- Same Telegram `file_id` creates the same filename
- First request downloads file, processes it, deletes it after completion
- Second request tries to access the same filename but file is gone
- Issue: filename collision when multiple users process the same forwarded message

**Solution Implemented**:
- Added UUID suffix to all downloaded filenames
- Each download creates a unique file regardless of `file_id`

**Files Modified**:
- `src/transcription/audio_handler.py`:
  ```python
  import uuid

  # In download_voice_message():
  unique_suffix = uuid.uuid4().hex[:8]
  audio_file = self.temp_dir / f"{file_id}_{unique_suffix}{extension}"

  # In download_from_url():
  unique_suffix = uuid.uuid4().hex[:8]
  audio_file = self.temp_dir / f"{file_id}_{unique_suffix}{extension}"
  ```

**Testing Results**:
- ✅ Queue positions now correctly show 1, 2, 3...
- ✅ User confirmed: "Вроде теперь ок"
- ✅ File naming conflict resolved
- ✅ All code quality checks pass (syntax, mypy, ruff)

**Key Patterns Established**:
1. **Atomic Counter Pattern**: For queue position tracking, use a dedicated counter that increments/decrements atomically rather than relying on `qsize()` which can be affected by concurrent workers
2. **Unique File Naming Pattern**: When multiple users may process the same resource (same file_id), always add UUID suffix to prevent filename collisions and race conditions

**Impact**:
- ✅ Accurate queue position feedback for users
- ✅ No more file conflicts when multiple users forward same message
- ✅ Improved reliability for concurrent usage scenarios

**Status**: ✅ Implemented and tested locally, ready for production deployment

### Phase 7.4: Dynamic Queue Notifications ✅ COMPLETE (2025-11-19)
**Achievement**: Enhanced queue notification system with accurate wait time calculation and dynamic updates

**Problem Solved**:
- Confusing message formulation: "Примерное время ожидания" didn't clarify if it was queue wait or processing time
- Inaccurate wait time calculation: used duration of current message instead of messages ahead in queue
- No dynamic updates: users didn't see position changes when queue progressed
- Didn't account for messages currently being processed
- Didn't correctly handle parallel processing (max_concurrent > 1)

**Solution Implemented**:

**1. Enhanced QueueManager** (`src/services/queue_manager.py`)
- Added `_pending_requests: list[TranscriptionRequest]` to track queue items with their data
- Added `_processing_requests: list[TranscriptionRequest]` to track items being processed
- Added `_on_queue_changed` callback for notifying handlers when queue changes
- New methods:
  - `get_estimated_wait_time_by_id()`: Calculates wait time based on:
    - Duration of all currently processing requests
    - Duration of all pending requests ahead in queue
    - Divides by `max_concurrent` for parallel processing
  - `get_queue_position_by_id()`: Returns current position in pending queue
  - `set_on_queue_changed()`: Registers callback for queue updates

**2. Dynamic Message Updates** (`src/bot/handlers.py`)
- New method `_update_queue_messages()`:
  - Called when any request starts processing
  - Iterates through all pending requests
  - Updates each user's status message with new position and times
  - Handles Telegram API errors gracefully
- Improved message format with clear separation:
  ```
  📋 В очереди: позиция 2
  ⏱️ Ожидание в очереди: ~1м 50с
  🎯 Обработка вашего сообщения: ~18с
  ```

**3. Accurate Wait Time Calculation**
```python
# Calculate total duration of items currently being processed
processing_duration = sum(r.duration_seconds for r in self._processing_requests)

# Get requests ahead in pending queue
pending_duration_ahead = sum(r.duration_seconds for r in items_ahead)

# Total wait = (processing + pending ahead) * RTF / concurrent workers
wait_time = (processing_duration + pending_duration_ahead) * rtf / max_concurrent

# Processing time = current message duration * RTF
processing_time = current_request.duration_seconds * rtf
```

**4. Time Formatting**
- Shows seconds for times < 60s: "~18с"
- Shows minutes and seconds for longer times: "~1м 50с"

**User Experience Improvements**:

*Before*:
- ❌ "Примерное время ожидания: ~18с" (confusing - is it wait or processing?)
- ❌ Time based on own message duration, not queue
- ❌ No updates when queue progresses
- ❌ All messages showed position 1 due to race condition

*After*:
- ✅ Clear separation: "Ожидание в очереди" vs "Обработка вашего сообщения"
- ✅ Wait time calculated from actual messages ahead
- ✅ Dynamic updates when queue progresses
- ✅ Correct position display (1, 2, 3...)
- ✅ Accounts for messages currently being processed
- ✅ Handles parallel processing correctly

**Files Modified**:
- `src/services/queue_manager.py`:
  - Added `_pending_requests`, `_processing_requests` lists
  - Added `_on_queue_changed` callback
  - Added `get_estimated_wait_time_by_id()`, `get_queue_position_by_id()`, `set_on_queue_changed()`
  - Updated `enqueue()` to add to `_pending_requests`
  - Updated `_process_request()` to move between lists and call callback
- `src/bot/handlers.py`:
  - Added `_update_queue_messages()` method
  - Registered callback in `__init__`
  - Updated queue notification formatting in both handlers

**Testing Results**:
- ✅ User confirmed: "Белиссимо! Все идеально вроде работает"
- ✅ Positions correctly show 1, 2, 3...
- ✅ Wait times accurately reflect messages ahead
- ✅ Processing times show individual message duration
- ✅ Messages update dynamically when queue progresses
- ✅ All code quality checks pass (ruff, mypy)

**Key Patterns Established**:
1. **Callback Pattern for Queue Updates**: Use callbacks to notify handlers when queue state changes, enabling dynamic UI updates
2. **Dual List Tracking**: Separate lists for pending and processing requests enables accurate time calculation
3. **Time Formatting Helper**: Consistent time display with appropriate units (seconds vs minutes)

**Plan Documentation**: `memory-bank/plans/2025-01-19-queue-notifications-improvement.md`

**Impact**:
- ✅ Clear, informative queue notifications
- ✅ Accurate wait time estimates
- ✅ Better user experience with dynamic updates
- ✅ Full transparency about queue state

**Status**: ✅ Implemented and tested, ready for production deployment

## Phase 8: Hybrid Transcription Acceleration ✅ COMPLETE (2025-11-20)

**Achievement**: Implemented 6-9x faster processing for long audio through hybrid transcription strategy

**Implementation**: 3-phase development completed in single session

### Phase 1: LLM Service Infrastructure ✅
- Created `src/services/llm_service.py` (263 lines)
  - Abstract `LLMProvider` base class
  - `DeepSeekProvider` with retry logic and error handling
  - `LLMFactory` for provider creation
  - `LLMService` high-level API with fallback
- Added LLM and hybrid strategy configuration to `src/config.py`
- Added `tenacity ^9.0.0` dependency for retry logic
- Created 19 comprehensive unit tests (all passing)
- Full type safety (mypy) and linting (ruff) compliance

**Key Features**:
- DeepSeek V3 integration via OpenAI-compatible API
- Retry logic with exponential backoff
- Text truncation for long inputs (max 10,000 chars)
- Graceful fallback on errors (timeout, API failure)
- Token usage logging

### Phase 2: Hybrid Strategy & Audio Preprocessing ✅
- Added `HybridStrategy` to `src/transcription/routing/strategies.py`
  - Duration-based routing (<20s: quality model, ≥20s: draft model)
  - Methods: `get_model_for_duration()`, `requires_refinement()`
- Added audio preprocessing to `src/transcription/audio_handler.py`
  - `preprocess_audio()`: Mono conversion + speed adjustment pipeline
  - `_convert_to_mono()`: ffmpeg-based mono conversion
  - `_adjust_speed()`: ffmpeg atempo filter (0.5x-2.0x range)
  - Graceful fallback to original on errors
- Created 29 unit tests for hybrid strategy and preprocessing (all passing)
- ffmpeg already verified in Dockerfile

**Configuration Added**:
```python
# Hybrid Strategy
hybrid_short_threshold: int = 20
hybrid_draft_provider: str = "faster-whisper"
hybrid_draft_model: str = "small"
hybrid_quality_provider: str = "faster-whisper"
hybrid_quality_model: str = "medium"

# Audio Preprocessing
audio_convert_to_mono: bool = False
audio_target_sample_rate: int = 16000
audio_speed_multiplier: float = 1.0
```

### Phase 3: Handler Integration ✅
- Updated `src/bot/handlers.py`:
  - Added preprocessing pipeline in `_process_transcription()`
  - Staged message updates (draft → refining → final)
  - LLM refinement for long audio in hybrid mode
  - Fallback to draft if LLM fails
  - Cleanup of preprocessed files
- Updated `src/main.py`:
  - LLM service initialization with proper error handling
  - Resource cleanup on shutdown
- All 93 unit tests passing

**User Experience (Hybrid Mode)**:
```
For long audio (≥20s):
1. 📥 Загружаю файл...
2. 🔄 [progress bar for draft]
3. ✅ Черновик готов:
   [draft text]
   🔄 Улучшаю текст...
4. ✨ Готово!
   [refined text]

For short audio (<20s):
1. 📥 Загружаю файл...
2. 🔄 [progress bar]
3. ✅ Готово!
   [final text]
```

### Quality Assurance ✅
- **Tests**: 93 unit tests passing (19 new for LLM, 29 for hybrid/preprocessing)
- **Type Safety**: mypy - no errors
- **Linting**: ruff - all checks passed
- **Formatting**: black - code formatted
- **Coverage**: Comprehensive test coverage for all new code

### Implementation Stats
- **5 commits** in feature branch:
  - Phase 1: LLM service infrastructure
  - Phase 2: Hybrid strategy and preprocessing
  - Phase 3: Handler integration
  - Style: Code formatting
  - Fix: Type annotations and unused imports
- **8 new files created**
- **93 tests passing**
- **Pull Request**: #44 created with comprehensive documentation

### Expected Performance
- **60s audio**: 36s → ~6s (6x faster)
  - Draft transcription: ~4s (small model, RTF 0.2x)
  - LLM refinement: ~2s (DeepSeek V3)
- **Cost**: ~$0.0002 per 60s audio (vs $0.006 OpenAI Whisper API)
- **Quality**: LLM corrects grammar, punctuation, capitalization

### Configuration (Default: Disabled)
```bash
# Disabled by default for safety
WHISPER_ROUTING_STRATEGY=single
LLM_REFINEMENT_ENABLED=false

# Enable hybrid mode:
WHISPER_ROUTING_STRATEGY=hybrid
HYBRID_SHORT_THRESHOLD=20
HYBRID_DRAFT_MODEL=small
LLM_REFINEMENT_ENABLED=true
LLM_API_KEY=sk-your-deepseek-key
```

### Documentation ✅
- `.env.example`: Updated with hybrid configuration (lines 249-385)
- Implementation plan: `memory-bank/plans/2025-11-20-hybrid-transcription-acceleration.md`
- Checklist: `memory-bank/plans/2025-11-20-hybrid-implementation-checklist.md`
- PR #44: Comprehensive summary with testing plan

### Key Patterns Established
1. **Hybrid Routing Strategy**: Duration-based provider selection for performance optimization
2. **LLM Post-Processing**: Use fast draft + LLM refinement instead of slow quality model
3. **Graceful Degradation**: Fallback to draft on LLM failures (timeout, API errors)
4. **Staged UI Updates**: Show draft immediately, then refine for better UX
5. **Audio Preprocessing Pipeline**: Optional transformations with error fallback

### Next Steps
1. ⏳ Manual testing with real voice messages
2. ⏳ Merge PR #44 to main
3. ⏳ Production deployment (disabled by default)
4. ⏳ Gradual rollout to specific users
5. ⏳ Monitor performance and costs
6. ⏳ Enable for all users after validation

**Status**: ✅ Implementation complete, PR created, ready for testing and deployment
**Pull Request**: https://github.com/konstantinbalakin/telegram-voice2text-bot/pull/44

---

## Next Steps (Current Priority)

### 1. Production Monitoring (High Priority) ⏳

**Current Production State**:
- Version: v0.0.1
- Logging: ✅ Active and collecting
- Health: ✅ Container healthy
- Performance: Stable

**Monitor These Metrics**:
- Queue depth (should stay < 10)
- CPU usage (should stay < 80%)
- Memory usage (RAM + swap)
- Processing times (RTF metrics)
- Rejection rates (duration > 120s, queue full)
- Progress bar functionality
- Error rates

**Actions**:
```bash
# Watch logs
docker logs -f telegram-voice2text-bot

# Check resource usage
docker stats telegram-voice2text-bot

# Monitor queue depth (from application logs)
grep "queue_depth" logs/bot.log
```

### 3. Documentation Maintenance ✅ COMPLETE

**Updated**:
- ✅ Memory Bank activeContext.md (Phase 6.7 documented)
- ✅ Memory Bank progress.md (Phase 6.7 completion added)
- ✅ All key learnings captured

### 4. Future Performance Optimization (Low Priority)

**Only if needed** (after queue system proves stable):

1. **Test 3 CPU** (if concurrent load increases)
   - Update `MAX_CONCURRENT_WORKERS=2`
   - Monitor CPU usage
   - Cost: ~$1-2/month increase

2. **Add Metrics Dashboard** (optional)
   - Prometheus + Grafana
   - Track: queue depth, processing times, rejection rate

3. **Optimize RTF** (if users complain about wait times)
   - Current: RTF ~0.3x with sequential processing
   - Could experiment with smaller models for short files

**Current Approach**: Start conservative (sequential, 120s limit), scale up only if needed based on actual usage patterns.

## Current Infrastructure

**VPS Configuration**:
- Provider: Russian VPS (~$10-15/month)
- RAM: 3GB
- CPU: 4 CPU cores
- OS: Ubuntu (clean)
- Docker: Installed and operational

**Deployment**:
- Method: Automated via GitHub Actions
- Trigger: Push to main branch
- Process: Build → Push to Docker Hub → SSH deploy
- Status: Fully operational

**Monitoring**:
- Container: `docker stats` for resources
- Logs: `docker logs telegram-voice2text-bot`
- Health: Container health checks passing
