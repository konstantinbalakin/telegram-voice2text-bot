# Project Brief: Telegram Voice2Text Bot

## Project Vision

Create a Telegram bot for transcribing voice messages with **exceptional user experience** using **API-first architecture** with intelligent text processing.

**Current Approach (2025-01-09):**
- OpenAI Whisper API for fast, accurate transcription (primary)
- DeepSeek V3 for intelligent text structuring and processing
- faster-whisper local model as fallback (reliability)
- Interactive features: Structure, Magic, Summary modes

**Initial Vision (2025-10-12):**
- Local Whisper AI model only (faster-whisper)
- Zero API costs
- Privacy-focused (all processing local)
- Cost-effective solution

**Evolution:** See [architecture-evolution.md](./architecture-evolution.md) for complete pivot story

## Core Objectives

**Primary Goal**: Build a production-ready Telegram bot with the **best user experience** for voice-to-text transcription.

**Current Objectives (2025-01-09):**
1. Fast transcription (<15 seconds for 1-minute audio)
2. High-quality Russian speech recognition
3. Intelligent text processing (structuring, summary, magic)
4. Reliable service (API with local fallback)
5. Cost-effective operations (~$0.006 per message)

**Initial Objectives (2025-10-12):**
1. Zero API costs (local processing only)
2. Privacy-focused (no data sent externally)
3. Cost-effective (free to operate)

**Status**: ✅ Phase 10.15 Complete (2025-12-25)
- Bot deployed and operational on VPS
- API-first architecture with local fallback
- All interactive features enabled
- Full file type support (voice, audio, documents, videos)

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
   - Queue-based architecture (up to 10 tasks, optimized for 1GB VPS)
   - Sequential processing (1 transcription at a time for stability)
   - Live progress updates with visual progress bar (every 5 seconds)
   - Graceful backpressure handling with queue position feedback

### Interactive Features (Phase 10, Implemented 2025-12-03 to 2025-12-25)
1. **Text Processing Pipeline** ✅
   - Structured mode (paragraphs, headings, lists)
   - Magic mode (publication-ready text with author's voice)
   - Summary mode (key points extraction)
   - LLM-powered: DeepSeek V3

2. **Interactive Keyboard** ✅
   - Mode switching (original/structured/magic/summary)
   - Length variations (shorter/longer with 3 levels)
   - Emoji levels (4 levels: none/few/moderate/many)
   - Timestamps for long audio (>5 min)
   - Variant caching in database

3. **File Support** ✅
   - Voice messages (Telegram standard)
   - Audio files (MP3, OGG, WAV, M4A, FLAC, etc.)
   - Documents (.aac, .flac, .wma, .amr, etc.)
   - Videos (.mp4, .mkv, .avi, .mov with audio extraction)
   - Large files: Up to 2GB via Telethon

### Future Features (Post-MVP)
1. **Payment Integration**
   - Purchase additional quota via Telegram Payments
   - Transaction management
   - Billing history

2. **Advanced Deployment**
   - Webhook mode for production
   - Horizontal scaling with Redis queue
   - Multi-language support beyond Russian

## Technology Stack ✅ DECIDED

- **Language**: Python 3.11+
- **Bot Framework**: python-telegram-bot v22.5

**Transcription Stack:**
- **Primary**: OpenAI Whisper API
  - Models: whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe
  - Performance: 5-10s for 1-minute audio
  - Cost: $0.006/minute
- **Fallback**: faster-whisper v1.2.0 (local)
  - Model: medium/int8/beam1
  - Performance: 20-36s for 1-minute audio
  - Cost: Free

**Text Processing:**
- **Provider**: DeepSeek V3
  - Model: deepseek-chat
  - Features: Structuring, Magic, Summary
  - Performance: 2-5s processing
  - Cost: ~$0.0002 per 60s audio

**Decision Rationale:** See [architecture-evolution.md](./architecture-evolution.md)

**Production Configuration**:
- Transcription: OpenAI API (primary) + faster-whisper (fallback)
- Text Processing: DeepSeek V3 for all LLM features
- Database: SQLAlchemy + SQLite
- Architecture: Queue-based monolith with asyncio
- Deployment: Docker + VPS with polling

## Use Case ✅ DEFINED

**Target Users**:
- Initially: Personal use by developer
- Future: Public bot for general Telegram users
- Focus: Russian-speaking users, but multi-language support

**Expected Scale**:
- MVP: 10-50 concurrent users
- Production: 100-500 users
- Resource: 3GB RAM, 4 CPU cores VPS (current production config)

**Privacy**: API-first architecture (data sent to OpenAI/DeepSeek, same as Telegram itself)

## Project Context

- **Naming**: "telegram-voice2text-bot" (renamed from telegram-voice-bot-v2)
- **Language Context**: Russian-speaking developer, Russian UI, international tools
- **Approach**: Structured development using Memory Bank methodology
- **Cost Focus**: API costs accepted for UX quality (~$0.006 per message)

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

### Production Success (Phase 5-10) ✅ COMPLETE (2025-10-27 to 2025-12-25)
- ✅ VPS server deployed (upgraded to 3GB RAM, 4 CPU cores)
- ✅ SSH and Docker operational
- ✅ Automated CI/CD deployment working
- ✅ Bot stable and responding to messages
- ✅ Critical issues resolved: database, DNS, OOM, missing dependencies
- ✅ Queue-based concurrency control deployed
- ✅ Database migration system automated
- ✅ Production limits optimized (queue=10, workers=1, duration=120s)
- ✅ Live progress feedback operational
- ✅ Hybrid transcription acceleration (Phase 8)
- ✅ Large file support via Telethon (Phase 9)
- ✅ Interactive transcription system (Phase 10, all 15 sub-phases)
- ✅ API-first architecture with OpenAI + DeepSeek (Phase 10)
- ✅ Document and video file support (Phase 10.15)
- **Performance**: API-first provides 5-15s total time (vs 20-36s local)
- **Status**: Production operational, free during user acquisition

## Constraints

### Technical Constraints
- Must work with Telegram Bot API (rate limits, file size limits)
- Voice format: OGG/Opus (Telegram standard)
- Max voice duration: 2 minutes (120 seconds, enforced since 2025-10-29)
- CPU-bound processing requires thread pool isolation
- Database migrations automated via Alembic (since Phase 6.5)

### Resource Constraints
- Production VPS: 3GB RAM, 4 CPU cores (upgraded from 1GB for API-first)
- Model size: ~1.5GB for medium model (fallback only)
- Sequential processing: 1 transcription at a time (prevents resource exhaustion)
- Queue size: 10 tasks maximum
- Docker image: ~1GB (optimized)
- Memory usage: <500MB RAM with API-first (vs ~2GB with local)

### Business Constraints
- API costs accepted for UX quality: ~$0.006 per message
- Cost-effective operations: ~$18.60/month for 100 daily users
- Free tier during user acquisition phase
- Future: Payment integration for quota expansion

## Implementation Timeline

**Phase 1-4 (MVP)**: ✅ Complete (2025-10-12 to 2025-10-24, 12 days)
- Day 1-2: Project setup + Database models ✅
- Day 3-4: Whisper integration + Queue system ✅
- Day 5-6: Bot handlers + Integration ✅
- Day 7-8: Testing + CI/CD pipeline ✅
- Day 9-10: Provider architecture + Flexible routing ✅
- Day 11-12: Benchmark analysis + Model finalization ✅

**Phase 5 (Deployment)**: ✅ Complete (2025-10-27 to 2025-10-29)
- VPS purchase and initial configuration ✅
- Automated deployment via CI/CD ✅
- Production validation and monitoring ✅
- Queue-based concurrency control ✅ (Phase 6)
- Database migration system ✅ (Phase 6.5)
- Production limit optimization ✅ (Phase 6.6)

**Phase 7 (Observability)**: ✅ Complete (2025-11-03 to 2025-11-04)
- Centralized logging with version tracking ✅
- Automatic semantic versioning ✅
- GitHub Actions workflow fixes ✅
- Production deployment v0.0.1 ✅
- Fully automatic deployment pipeline ✅ (v0.0.3)

**Phase 8 (Hybrid Transcription)**: ✅ Complete (2025-11-20)
- Draft + LLM refinement workflow ✅
- 6-9x speedup for long audio ✅
- LLM performance tracking ✅

**Phase 9 (Large File Support)**: ✅ Complete (2025-11-30)
- Telethon integration for >20MB files ✅
- Support up to 2GB ✅
- Hybrid download strategy ✅

**Phase 10 (Interactive Transcription)**: ✅ Complete (2025-12-03 to 2025-12-25)
- Database models (State, Variant, Segment) ✅
- Structured mode with LLM ✅
- Length variations ✅
- Summary mode ✅
- Emoji option ✅
- Timestamps ✅
- PDF file handling ✅
- Retranscription ✅
- OpenAI API provider ✅
- Provider-aware preprocessing ✅
- StructureStrategy (auto-structured) ✅
- Long audio chunking ✅
- Magic mode ✅
- Document & video support ✅

**Phase 11+ (Future)**: Analytics dashboard, quotas & billing, multi-language

## Risk Assessment

### Key Risks Identified
1. ✅ **Whisper Performance** - Resolved by API-first architecture (4-7x faster)
2. ✅ **Resource Consumption** - Mitigated by API-first (<500MB vs ~2GB local)
3. ✅ **Audio Format** - Mitigated by provider-aware preprocessing
4. ✅ **Model Quality** - Resolved via OpenAI API (best-in-class for Russian)
5. ✅ **Docker Image Size** - Optimized, ~1GB image
6. ✅ **Scale Concerns** - API-first allows 10x more users
7. ✅ **API Costs** - Acceptable: ~$0.006 per message, ~$18.60/month for 100 daily users
8. 🔄 **API Dependencies** - Mitigated by local fallback (faster-whisper)

## Notes

**Key Success Factor (2025-01-09)**: The pivot to API-first architecture (OpenAI + DeepSeek) resulted in 4-7x faster transcription (5-10s vs 20-36s), better quality, and LLM-powered features impossible with local-only approach. API costs (~$0.006 per message) are acceptable for the UX quality provided.

**Architecture Philosophy**: Start simple (monolith) but structure for growth. Queue abstraction allows future migration to Redis for horizontal scaling. API-first with local fallback provides best UX + reliability.

**Architecture Evolution (2025-11-20 to 2025-12-25)**:
- **Initial vision (2025-10-12)**: Local-only, zero API costs, privacy-focused
- **Problem discovered**: Local transcription too slow (20-36s), users won't wait
- **Phase 1 (2025-11-20)**: Added LLM refinement (DeepSeek V3) for long audio
- **Phase 2 (2025-12-15)**: Added OpenAI API provider for better quality
- **Phase 3 (2025-12-25)**: Made OpenAI primary, API-first architecture
- **Result**: 4-7x faster, better quality, intelligent features, happy users

**Provider Architecture (Current)**:
- **Primary**: OpenAI Whisper API (whisper-1, gpt-4o-transcribe)
- **Fallback**: faster-whisper local (medium/int8/beam1)
- **Text Processing**: DeepSeek V3 (structuring, magic, summary)
- **Rationale**: Best UX quality with cost-effective operations

**Performance Comparison**:
- API-first: 5-15s total time (5-10s transcription + 2-5s LLM)
- Local-only: 20-36s transcription time
- **Improvement**: 2-5x faster overall

**Cost Structure**:
- Per 60-second message: ~$0.0062 (OpenAI $0.006 + DeepSeek $0.0002)
- Monthly (100 messages/day): ~$18.60/month
- **Conclusion**: Cost acceptable for UX quality provided

---

## Initial Vision (Archived 2025-12-25)

**Original Goals (2025-10-12):**
- Primary Goal: Build a bot using local Whisper AI model
- Zero API costs (free to operate)
- Privacy-focused (all processing local)
- Cost-effective solution for personal use

**Why Pivot?**
- Speed: Local transcription too slow (20-36s vs 5-10s API)
- Quality: OpenAI API better than local models
- Features: LLM text processing impossible locally
- UX: Users won't wait 30+ seconds for transcription

**Migration documented in:** [architecture-evolution.md](./architecture-evolution.md)
