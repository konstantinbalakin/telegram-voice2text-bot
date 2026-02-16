# Active Context: Telegram Voice2Text Bot

## Current Status (2026-02-16)

**Phase**: Code Audit Complete (5 waves) ✅
**Production Version**: v0.0.3+
**Production Status**: ✅ OPERATIONAL
**Tests**: 590 (unit + integration)
**Branch**: main

### Infrastructure
- **VPS**: 3GB RAM, 4 CPU cores
- **Docker**: Automated builds and deployments
- **CI/CD**: GitHub Actions + pre-commit/pre-push hooks
- **Database**: SQLite with Alembic migrations
- **Bot**: Live on Telegram

---

## Recent: Code Audit (2026-02-11 — 2026-02-16)

5 волн рефакторинга без изменения бизнес-функциональности (PR #96-102).

### Wave 1 (PR #96): 22 Quick Fixes
- Security: subprocess timeout, mask DB URL/API key, UUID filenames, healthcheck exec form
- Performance: SQL SUM aggregation, persistent httpx client, variant lookup index, configurable max_tokens
- Architecture: named constants, modern typing, helper functions

### Wave 2 (PR #98): 13 Tasks
- **IDOR protection** — verify callback query ownership
- **Daily quota check** per user (configurable limit)
- **Sensitive data filter** — masks bot token in logs
- **Callback validation** — actions, params, types
- **Business exceptions** hierarchy (`src/exceptions.py`)
- **datetime.utcnow()** → timezone-aware
- 27 new tests (keyboards, split_text, QueueManager, IDOR, quota, logging)

### Wave 3 (PR #99): 9 Tasks
- **async subprocess** — `subprocess.run()` → `asyncio.create_subprocess_exec()`
- **ffmpeg streaming** — pydub → ffmpeg pipe (no OOM on large files)
- **get_or_create_variant()** — eliminates race condition on double get_variant
- **Progress tracker rate limiter** — configurable interval, global 0.5s limit
- **HTML sanitization** — escape_html for Whisper, sanitize_html for LLM
- 130 new tests (config, progress tracker, db retry)

### Wave 4 (PR #100): 5 Architectural Tasks
- **A1**: Unified 4 media handlers → `MediaInfo` dataclass + `_handle_media_message()` (handlers.py: 2239→786 lines, −65%)
- **A2**: `_process_transcription` (506 lines) → 5 focused methods
- **A3**: `TranscriptionOrchestrator` extracted to `src/services/` (792 lines). handlers.py now only routes Telegram messages.
- **A4**: Callbacks deduplication → `_generate_variant()` + `MODE_LABELS`
- **A5**: `AsyncService` protocol (`src/services/lifecycle.py`) — uniform async lifecycle

### Wave 5 (PR #102): 157 New Tests
- 46 tests — CallbackHandlers
- 34 tests — BotHandlers
- 30 tests — TranscriptionOrchestrator
- 11 integration tests (real DB, queue→orchestrator, variant caching, IDOR)

**Total**: 181 → 590 tests (+226%)

### Pre-commit Hooks (PR #97)
- **Pre-commit**: no-commit-to-branch, ruff, black
- **Pre-push**: mypy, pytest

---

## Architecture (Post-Audit)

### Service Layer Separation
```
Telegram Message → BotHandlers (routing only, 786 lines)
                      ↓
              TranscriptionOrchestrator (business logic, 792 lines)
                      ↓
              CallbackHandlers (variant generation via _generate_variant())
```

### Key Abstractions
- `MediaInfo` dataclass — unified voice/audio/document/video handling
- `TranscriptionOrchestrator` — preprocess → transcribe → structure → refine → send
- `AsyncService` Protocol — initialize/shutdown/is_initialized for all services
- Business exceptions (`src/exceptions.py`) — typed error hierarchy

---

## Next Steps

### Short-term
- Merge audit results to main (done)
- Monitor production stability post-refactoring
- Consider increasing test coverage for edge cases

### Future (Phase 11+)
- Analytics dashboard
- Quotas & billing
- Multi-language support
- PostgreSQL migration

---

## Key Files

**Core Services**:
- `src/bot/handlers.py` — Telegram message routing (786 lines)
- `src/bot/callbacks.py` — Callback handlers with `_generate_variant()`
- `src/services/transcription_orchestrator.py` — Business logic (792 lines)
- `src/services/lifecycle.py` — AsyncService protocol
- `src/exceptions.py` — Business exception hierarchy

**Configuration**:
- `src/config.py` — All settings with validation
- `.pre-commit-config.yaml` — Pre-commit/pre-push hooks

**Tests**:
- `tests/unit/` — 579 unit tests
- `tests/integration/` — 11 integration tests
