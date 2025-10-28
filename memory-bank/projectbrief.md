# Project Brief: Telegram Voice2Text Bot

## Project Vision

Create a Telegram bot for transcribing voice messages using local Whisper AI model. Designed as a cost-effective, privacy-focused solution for converting voice messages to text with optional summarization capabilities.

## Core Objectives

**Primary Goal**: Build a production-ready Telegram bot that transcribes voice messages locally without relying on paid APIs.

**Current Status**: Phase 5 Complete (2025-10-27) - Bot deployed and operational on VPS. Performance optimization experiments planned.

**Date**: Started 2025-10-12, Production-ready 2025-10-24

## Functionality Scope ✅ DECIDED

### MVP Features (Phase 1)
1. **Voice Transcription** - Core functionality
   - Accept voice messages via Telegram
   - Transcribe using local faster-whisper model
   - Return transcribed text to user
   - Support for Russian and other languages

2. **Quota System** - Usage management
   - Free tier: 60 seconds/day per user
   - Unlimited access flag for privileged users
   - Daily quota reset mechanism
   - Usage tracking and history

3. **Async Processing** - Performance
   - Queue-based architecture (up to 100 tasks)
   - Concurrent processing (3 simultaneous transcriptions)
   - Status updates during processing
   - Graceful backpressure handling

### Future Features (Post-MVP)
1. **Text Processing Pipeline**
   - Summary generation from transcriptions
   - Key points extraction
   - Extensible processor interface

2. **Payment Integration**
   - Purchase additional quota via Telegram Payments
   - Transaction management
   - Billing history

3. **Advanced Deployment**
   - Webhook mode for production
   - Horizontal scaling with Redis queue
   - GPU support for faster processing

## Technology Stack ✅ DECIDED

- **Language**: Python 3.11+
- **Bot Framework**: python-telegram-bot v22.5
- **Transcription**: faster-whisper v1.2.0 (4x faster than openai-whisper)
  - **Production Model**: medium/int8/beam1 (finalized 2025-10-24)
  - **Performance**: RTF ~0.3x (3x faster than audio)
  - **Memory**: ~2GB RAM peak (tested in production)
  - **Provider Architecture**: faster-whisper (local), OpenAI API (optional fallback)
- **Database**: SQLAlchemy + SQLite (MVP) → PostgreSQL (production)
- **Architecture**: Hybrid Queue (monolith with asyncio queue)
- **Deployment**: Docker + VPS with polling → webhook

**Rationale**: Optimizes for local processing, zero API costs, excellent Russian language support, and clear scaling path.

**Key Decision (2025-10-24)**: After comprehensive benchmarking (30+ configurations, 3 audio samples), selected medium/int8/beam1 as production default. Prioritized quality over speed based on manual transcript analysis. Removed openai-whisper provider to reduce Docker image size by ~2-3GB.

## Use Case ✅ DEFINED

**Target Users**:
- Initially: Personal use by developer
- Future: Public bot for general Telegram users
- Focus: Russian-speaking users, but multi-language support

**Expected Scale**:
- MVP: 10-50 concurrent users
- Production: 100-500 users
- Resource: 2-3GB RAM VPS recommended (2GB minimum for medium model, tested in production)

**Privacy**: All processing local, no data sent to external APIs

## Project Context

- **Naming**: "telegram-voice2text-bot" (renamed from telegram-voice-bot-v2)
- **Language Context**: Russian-speaking developer, Russian UI, international tools
- **Approach**: Structured development using Memory Bank methodology
- **Cost Focus**: Zero API costs via local Whisper model

## Success Criteria

### MVP Success (Phases 1-4) ✅ COMPLETE (2025-10-24)
- ✅ Project structure initialized
- ✅ Dependencies defined and documented
- ✅ Configuration system implemented
- ✅ Voice transcription working end-to-end
- ✅ Quota system functional
- ✅ Docker deployment ready
- ✅ Test coverage >80% (45 unit tests passing)
- ✅ CI/CD pipeline operational
- ✅ Production model finalized (medium/int8/beam1)
- ✅ Provider architecture flexible (faster-whisper + OpenAI API)
- ✅ Quality checks automated (mypy, ruff, black, pytest)

### Production Success (Phase 5) ✅ COMPLETE (2025-10-27)
- ✅ VPS server deployed (1GB RAM + 1GB swap, 1 vCPU)
- ✅ SSH and Docker operational
- ✅ Automated CI/CD deployment working
- ✅ Bot stable and responding to messages
- ✅ Critical issues resolved: database, DNS, OOM
- ⚠️ **Performance below target**: RTF 3.04x vs target 0.3x
- **Next Phase**: Performance optimization experiments (RAM/CPU scaling)

## Constraints

### Technical Constraints
- Must work with Telegram Bot API (rate limits, file size limits)
- Voice format: OGG/Opus (Telegram standard)
- Max voice duration: 5 minutes (300 seconds)
- CPU-bound processing requires thread pool isolation

### Resource Constraints
- MVP target: 2-3GB RAM VPS (2GB minimum, observed ~2GB peak in production)
- Model size: ~1.5GB for medium model
- Concurrent processing limit: 3 (memory constraint)
- Queue size: 100 tasks maximum
- Docker image: ~2GB (optimized, removed torch/openai-whisper)
- Note: Initial benchmarks overestimated memory (3.5GB); actual production usage ~2GB

### Business Constraints
- Zero budget for external APIs
- Local processing requirement
- Free tier must be sustainable

## Implementation Timeline

**Phase 1-4 (MVP)**: ✅ Complete (2025-10-12 to 2025-10-24, 12 days)
- Day 1-2: Project setup + Database models ✅
- Day 3-4: Whisper integration + Queue system ✅
- Day 5-6: Bot handlers + Integration ✅
- Day 7-8: Testing + CI/CD pipeline ✅
- Day 9-10: Provider architecture + Flexible routing ✅
- Day 11-12: Benchmark analysis + Model finalization ✅

**Phase 5 (Deployment)**: 🔄 Ready to start
- VPS purchase and initial configuration
- Automated deployment via CI/CD
- Production validation and monitoring

**Phase 6+ (Future)**: Text processing pipeline, payment integration

## Risk Assessment

### Key Risks Identified
1. ✅ **Whisper Performance** - Mitigated by faster-whisper selection & medium model benchmarking
2. ✅ **Resource Consumption** - Mitigated by semaphore limits (3 workers), actual ~2GB peak in production
3. ✅ **Audio Format** - Mitigated by faster-whisper handling OGG/Opus natively
4. ✅ **Model Quality** - Resolved via comprehensive benchmarking (30+ configs, manual analysis)
5. ✅ **Docker Image Size** - Optimized by removing torch/openai-whisper (~2-3GB savings)
6. 🔄 **Scale Concerns** - Migration path to Redis queue documented
7. ✅ **VPS Memory** - Actual 2GB peak observed (initial 3.5GB estimate was incorrect), 2-3GB VPS sufficient

## Notes

**Key Success Factor**: The decision to use faster-whisper v1.2.0 instead of openai-whisper resulted in 4x performance improvement and 75% less memory usage - critical for MVP viability on modest hardware.

**Architecture Philosophy**: Start simple (monolith) but structure for growth. Queue abstraction allows future migration to Redis for horizontal scaling.

**Model Selection Breakthrough (2025-10-24)**: After extensive benchmarking (30+ configurations across 3 audio samples), chose medium/int8/beam1 as production default. Manual transcript analysis revealed that faster configurations (tiny, small) had unacceptable quality degradation (22-78% similarity in worst cases). The medium model with greedy decoding (beam1) provides excellent Russian transcription quality at RTF ~0.3x (3x faster than audio). This decision prioritizes user experience (quality) over raw speed, while still being fast enough for production use. Memory usage: ~2GB peak (initial benchmark estimate of 3.5GB was incorrect due to measurement methodology).

**Provider Architecture Evolution**: Initially supported 3 providers (faster-whisper, openai-whisper, OpenAI API). After benchmarking showed that faster-whisper medium outperformed openai-whisper in both speed and quality, removed openai-whisper provider entirely. This reduced Docker image size by ~2-3GB and simplified the codebase. Current architecture: faster-whisper (default, local) + OpenAI API (optional, fallback for future use).

**Next Major Milestone**: VPS deployment and production validation. Code is production-ready, awaiting infrastructure purchase.
