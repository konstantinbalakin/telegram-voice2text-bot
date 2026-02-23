# Progress Overview: Telegram Voice2Text Bot

## Project Timeline

**Start Date**: 2025-10-12
**Current Version**: v0.0.3+
**Production Status**: ✅ OPERATIONAL - All systems deployed and stable

## Recent Infrastructure Updates

### Package Manager Migration (2026-01-27)
- **Migration**: Poetry → UV ✅ Complete
- **Duration**: 1 day (6 stages)
- **Impact**:
  - 95 packages in `uv.lock`
  - All 181 tests passing
  - CI/CD pipelines updated
  - 12 documentation files updated
  - Faster dependency resolution and builds
- **Branch**: `refactor/poetry-to-uv`
- **Status**: Ready for merge to main

### Code Audit & Refactoring (2026-02, PR #96-102)
5 волн, 53 задачи, только рефакторинг (без бизнес-функциональности):
- **Wave 1**: 22 quick-fix (security, performance, architecture) ✅
- **Wave 2**: 13 задач (IDOR, квоты, бизнес-исключения, 27 тестов) ✅
- **Wave 3**: 9 задач (async subprocess, ffmpeg streaming, rate limiter, 130 тестов) ✅
- **Wave 4**: 5 архитектурных (handlers.py 2239→786, TranscriptionOrchestrator, AsyncService) ✅
- **Wave 5**: 157 новых тестов (callbacks, handlers, orchestrator, integration) ✅
- **Pre-commit hooks**: ruff, black, mypy, pytest ✅
- **Итого тестов**: 181 → 590 (+226%)

## Completed Phases

### Infrastructure & Core (Phases 1-7.4)
- **Phase 1-4**: Project setup, core bot, providers, CI/CD ✅ (2025-10-12 to 2025-10-24)
- **Phase 5**: VPS deployment & production validation ✅ (2025-10-27)
- **Phase 5.1**: CI/CD optimization & documentation reorganization ✅ (2025-10-28)
- **Phase 5.2**: Critical production bug fix (faster-whisper missing) ✅ (2025-10-29)
- **Phase 6**: Queue-based concurrency control with progress tracking ✅ (2025-10-29)
- **Phase 6.5**: Database migration system with automated CI/CD ✅ (2025-10-29)
- **Phase 6.6**: Production limit optimization (queue size: 10) ✅ (2025-10-29)
- **Phase 6.7**: Long transcription message splitting (>4096 chars) ✅ (2025-10-30)
- **Phase 7**: Centralized logging & automatic semantic versioning ✅ (2025-11-03)
- **Phase 7.1**: Workflow fixes & production deployment ✅ (2025-11-03)
- **Phase 7.2**: Fully automatic deployment pipeline ✅ (2025-11-04)
- **Phase 7.3**: Queue position & file naming bug fixes ✅ (2025-11-19)
- **Phase 7.4**: Dynamic queue notifications with accurate time calculation ✅ (2025-11-19)

### Performance & Advanced Features (Phases 8-9)
- **Phase 8**: Hybrid transcription acceleration (6-9x speedup for long audio) ✅ (2025-11-20)
- **Phase 8.1**: DEBUG logging enhancement ✅ (2025-11-24)
- **Phase 8.2**: LLM debug mode (draft vs refined comparison) ✅ (2025-11-24)
- **Phase 8.3**: LLM performance tracking in database ✅ (2025-11-24)
- **Phase 9**: Large file support via Telethon (20MB → 2GB) ✅ (2025-11-30)

### Interactive Transcription System (Phase 10.1-10.14)
- **Phase 10.1**: Infrastructure (database, keyboards, callbacks, segments) ✅ (2025-12-03)
- **Phase 10.2**: Structured mode with LLM text structuring ✅ (2025-12-03)
- **Phase 10.3**: Length variations (shorter/longer with 3 levels) ✅ (2025-12-03)
- **Phase 10.4**: Summary mode with key points extraction ✅ (2025-12-03)
- **Phase 10.5**: Emoji option (4 levels: none/few/moderate/many) ✅ (2025-12-04)
- **Phase 10.6**: Timestamps for long audio (>5 minutes) ✅ (2025-12-05)
- **Phase 10.7**: File handling for text >4096 chars (PDF generation) ✅ (2025-12-08)
- **Phase 10.8**: Retranscription with quality improvements ✅ (2025-12-08)
- **Phase 10.9**: Retranscription UX improvements (progress bar, parent-child tracking) ✅ (2025-12-09)
- **Phase 10.10**: HTML formatting & PDF generation ✅ (2025-12-09)
- **Phase 10.11**: Provider-aware audio format conversion (OpenAI gpt-4o support) ✅ (2025-12-15)
- **Phase 10.12**: StructureStrategy (automatic structured transcription) ✅ (2025-12-16)
- **Phase 10.13**: OpenAI long audio chunking (unlimited duration) ✅ (2025-12-17)
- **Phase 10.14**: Magic Mode (publication-ready text transformation) ✅ (2025-12-19)
- **Phase 10.15**: Document & Video File Support (universal file type handling) ✅ (2025-12-25)

## Current Feature Set

### Core Transcription
- ✅ faster-whisper (medium/int8, RTF ~0.3x)
- ✅ OpenAI Whisper API (gpt-4o-transcribe, gpt-4o-mini-transcribe, whisper-1)
- ✅ Provider fallback strategies
- ✅ Hybrid transcription (draft + LLM refinement)
- ✅ StructureStrategy (automatic structured transcription)
- ✅ Queue management (max 10 concurrent, sequential processing)
- ✅ Progress tracking with live updates
- ✅ Duration limits (120s max)

### File Handling
- ✅ Voice messages (standard Telegram voice input)
- ✅ Audio files (sent as Telegram audio messages)
- ✅ Document files with audio MIME types (.aac, .flac, .m4a, .wma, etc.)
- ✅ Video files with audio track extraction (.mp4, .mkv, .avi, .mov, .webm)
- ✅ Large files via Telethon (up to 2GB)
- ✅ Provider-aware format conversion (OGA → MP3/WAV for gpt-4o)
- ✅ OpenAI long audio chunking (parallel/sequential with overlap)
- ✅ PDF generation for long transcriptions
- ✅ HTML formatting with Telegram parse mode
- ✅ Audio extraction from video using ffmpeg

### Interactive Features (Phase 10)
- ✅ Mode switching (original/structured/summary/magic)
- ✅ Length variations (3 levels shorter/longer)
- ✅ Emoji levels (4 levels: 0-3)
- ✅ Timestamps for long audio (>5 min)
- ✅ Retranscription (free/paid options)
- ✅ Variant caching in database
- ✅ File export for long texts (>3000 chars)
- ✅ Magic Mode (publication-ready text with author's voice)

### Infrastructure
- ✅ SQLite database with migrations (Alembic)
- ✅ Automated CI/CD with GitHub Actions
- ✅ Docker deployment with health checks
- ✅ Centralized logging with version tracking
- ✅ Automatic semantic versioning
- ✅ DEBUG mode with comprehensive logging

## Technical Architecture

### Package Management
- **Package Manager**: uv (migrated from Poetry 2026-01-27)
- **Lock File**: `uv.lock` (95 packages)
- **Standard**: PEP 621 compliant `pyproject.toml`
- **Benefits**: Faster resolution, Rust-based, standards-compliant

### Transcription Providers
- **faster-whisper**: Local transcription (default: medium/int8)
- **OpenAI API**: Cloud transcription (gpt-4o-transcribe, gpt-4o-mini-transcribe, whisper-1)

### Routing Strategies
- **single**: Single provider, no fallback
- **fallback**: Primary + fallback provider
- **benchmark**: Performance testing mode
- **hybrid**: Duration-based (short=quality, long=draft+LLM)
- **structure**: Automatic structuring with configurable emoji levels

### LLM Services
- **DeepSeek**: Text refinement, structuring, summary (cost-effective)
- Retry logic with exponential backoff
- Graceful fallback on failures

### Database Models
- **Usage**: Transcription metadata, processing times, parent-child relationships
- **TranscriptionState**: UI state tracking (mode, emoji, timestamps, file message tracking)
- **TranscriptionVariant**: Cached text variations (mode, length, emoji)
- **TranscriptionSegment**: Timestamps for long audio

## Performance Metrics

**VPS Configuration**: 1GB RAM, 1 vCPU
**Processing**:
- Short audio (<20s): RTF 0.3x (faster-whisper medium)
- Long audio (≥20s hybrid): RTF 0.1x (small draft + LLM)
- Queue: Sequential processing (max_concurrent=1)
- Progress: Live updates every 5s

**OpenAI Chunking** (for audio >1400s):
- Strategy 1 (default): Auto-switch to whisper-1 model (no duration limit)
- Strategy 2: Parallel chunking (2-3x faster, no context between chunks)
- Strategy 3: Sequential chunking (slower, context preservation via prompts)

## Production Configuration

**Key Settings**:
```bash
# Routing Strategy
WHISPER_ROUTING_STRATEGY=structure  # Automatic structured transcription

# StructureStrategy
STRUCTURE_PROVIDER=faster-whisper
STRUCTURE_MODEL=medium
STRUCTURE_DRAFT_THRESHOLD=20  # Show draft for audio ≥20s
STRUCTURE_EMOJI_LEVEL=1  # 0=none, 1=few, 2=moderate, 3=many

# LLM Refinement (required for structure strategy)
LLM_REFINEMENT_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat

# Queue & Limits
MAX_VOICE_DURATION_SECONDS=120
MAX_QUEUE_SIZE=10
MAX_CONCURRENT_WORKERS=1

# Interactive Mode
INTERACTIVE_MODE_ENABLED=true
ENABLE_STRUCTURED_MODE=true
ENABLE_MAGIC_MODE=true
ENABLE_SUMMARY_MODE=true
ENABLE_EMOJI_OPTION=true
ENABLE_LENGTH_VARIATIONS=true
ENABLE_TIMESTAMPS_OPTION=true
ENABLE_RETRANSCRIBE=true
FILE_THRESHOLD_CHARS=3000  # Text >3000 chars sent as file

# OpenAI Long Audio Handling
OPENAI_GPT4O_MAX_DURATION=420
OPENAI_CHANGE_MODEL=true  # Auto-switch to whisper-1 for long audio
OPENAI_CHUNKING=false  # Enable manual chunking if needed
```

## Known Limitations

1. **Performance**: RTF 3.04x on 1GB/1vCPU VPS (mitigated by progress feedback and hybrid mode)
2. **File Storage**: Audio files saved for retranscription (TTL: 7 days cleanup)
3. **OpenAI Duration Limits**: gpt-4o models ~1400s (mitigated by auto model switch or chunking)

## Next Steps

### Monitoring & Optimization
- ⏳ Monitor StructureStrategy adoption and quality
- ⏳ Gather feedback on emoji levels and draft threshold
- ⏳ Monitor OpenAI chunking performance and strategies
- ⏳ Evaluate hybrid vs structure strategy usage patterns

### Potential Future Features
- [ ] PostgreSQL migration for production scale
- [ ] User quotas and billing system
- [ ] Multi-language support beyond Russian
- [ ] Voice message compression options
- [ ] Batch processing for multiple files

## Documentation

**Detailed Plans**: See `memory-bank/plans/` for phase-by-phase implementation details
**System Docs**: See `docs/` for architecture, deployment, and development guides
**Configuration**: See `.env.example` for comprehensive configuration options

## Key Patterns Established

1. **Duration-Based Workflows**: Use duration thresholds to determine UX approach (draft preview vs direct result)
2. **Variant Caching**: Database-backed caching of all text variations with composite unique keys
3. **Progressive Disclosure**: Show drafts for long operations, direct results for fast operations
4. **Provider-Aware Preprocessing**: Optimize audio format based on target provider requirements
5. **Graceful Degradation**: LLM failures fall back to original text, never block users
6. **Parent-Child Usage Tracking**: Preserve history through retranscription chains
7. **Semantic Versioning**: Automatic patch increments, manual minor/major versions
8. **Semaphore-Based Rate Limiting**: Control concurrent API calls for parallel chunking
9. **Chunk Overlap**: Small overlap between chunks prevents word cutting at boundaries
10. **Universal File Type Support**: Handle voice, audio, documents, and video through unified transcription pipeline
11. **MIME Type Filtering**: Validate document MIME types before processing to avoid non-audio files
12. **Audio Stream Detection**: Check for audio streams in video files before attempting extraction
13. **Standards-Compliant Packaging**: PEP 621 with UV for fast, reliable dependency management
14. **Unified Media Handler Pattern**: Single `_handle_media_message()` with `MediaInfo` dataclass handles voice/audio/document/video
15. **Service Layer Separation**: `TranscriptionOrchestrator` isolates business logic from Telegram handlers
16. **AsyncService Protocol**: Runtime-checkable protocol for uniform async lifecycle (initialize/shutdown/is_initialized)
17. **Business Exception Hierarchy**: Typed exceptions in `src/exceptions.py` for structured error handling
18. **IDOR Protection**: Callback query ownership verification
19. **Pre-commit/Pre-push Hooks**: Automated quality gates (ruff, black, mypy, pytest)

---

**Branch**: `main`
**Latest Deployment**: Automatic via GitHub Actions on merge to main
