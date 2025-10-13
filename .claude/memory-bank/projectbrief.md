# Project Brief: Telegram Voice2Text Bot

## Project Vision

Create a Telegram bot for transcribing voice messages using local Whisper AI model. Designed as a cost-effective, privacy-focused solution for converting voice messages to text with optional summarization capabilities.

## Core Objectives

**Primary Goal**: Build a production-ready Telegram bot that transcribes voice messages locally without relying on paid APIs.

**Current Status**: Phase 1 Implementation - Project setup complete, moving to core feature implementation.

**Date**: Started 2025-10-12

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
- **Database**: SQLAlchemy + SQLite (MVP) → PostgreSQL (production)
- **Architecture**: Hybrid Queue (monolith with asyncio queue)
- **Deployment**: Docker + VPS with polling → webhook

**Rationale**: Optimizes for local processing, zero API costs, excellent Russian language support, and clear scaling path.

## Use Case ✅ DEFINED

**Target Users**:
- Initially: Personal use by developer
- Future: Public bot for general Telegram users
- Focus: Russian-speaking users, but multi-language support

**Expected Scale**:
- MVP: 10-50 concurrent users
- Production: 100-500 users
- Resource: 4GB RAM VPS sufficient for MVP

**Privacy**: All processing local, no data sent to external APIs

## Project Context

- **Naming**: "telegram-voice2text-bot" (renamed from telegram-voice-bot-v2)
- **Language Context**: Russian-speaking developer, Russian UI, international tools
- **Approach**: Structured development using Memory Bank methodology
- **Cost Focus**: Zero API costs via local Whisper model

## Success Criteria

### MVP Success (Phase 1) ✅
- ✅ Project structure initialized
- ✅ Dependencies defined and documented
- ✅ Configuration system implemented
- 🔄 Voice transcription working end-to-end
- 🔄 Quota system functional
- 🔄 Docker deployment ready
- 🔄 Test coverage >70%

### Production Success (Phase 2-3)
- VPS deployment with webhook mode
- PostgreSQL database migration
- CI/CD pipeline operational
- Monitoring and logging in place

## Constraints

### Technical Constraints
- Must work with Telegram Bot API (rate limits, file size limits)
- Voice format: OGG/Opus (Telegram standard)
- Max voice duration: 5 minutes (300 seconds)
- CPU-bound processing requires thread pool isolation

### Resource Constraints
- MVP target: 4GB RAM VPS
- Model size: ~500MB for base model
- Concurrent processing limit: 3 (memory constraint)
- Queue size: 100 tasks maximum

### Business Constraints
- Zero budget for external APIs
- Local processing requirement
- Free tier must be sustainable

## Implementation Timeline

**Phase 1 (MVP)**: 6 days estimated
- Day 1: Project setup ✅ + Database models 🔄
- Day 2: Whisper integration + Queue system
- Day 3: Bot handlers
- Day 4-5: Integration & testing
- Day 6: Docker deployment

**Phase 2**: VPS deployment + webhook (1 week)
**Phase 3**: Text processing pipeline (2 weeks)
**Phase 4**: Payment integration (2 weeks)

## Risk Assessment

### Key Risks Identified
1. ✅ **Whisper Performance** - Mitigated by faster-whisper selection
2. ✅ **Resource Consumption** - Mitigated by semaphore limits (3 workers)
3. ✅ **Audio Format** - Mitigated by faster-whisper handling OGG/Opus natively
4. 🔄 **Scale Concerns** - Migration path to Redis queue documented

## Notes

**Key Success Factor**: The decision to use faster-whisper v1.2.0 instead of openai-whisper resulted in 4x performance improvement and 75% less memory usage - critical for MVP viability on modest hardware.

**Architecture Philosophy**: Start simple (monolith) but structure for growth. Queue abstraction allows future migration to Redis for horizontal scaling.

**Next Major Milestone**: Complete database models and Whisper service integration to achieve first end-to-end transcription.
