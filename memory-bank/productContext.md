# Product Context: Telegram Voice2Text Bot

## Problem Space ✅ DEFINED

### The Primary Need

Voice messages in Telegram are popular but have key limitations:

**Current Problem (2025-01-09):**
- **Speed**: Local transcription takes 20-36 seconds (users won't wait)
- **Quality**: Local models make mistakes on Russian speech
- **Features**: Cannot intelligently process or structure text
- **UX**: Slow processing = poor user experience

**Original Problem (2025-10-12):**
- Voice messages cannot be quickly scanned or searched
- Time inefficiency (cannot skim content)
- Accessibility issues (noise, hearing impairment)
- Language barriers (difficult to translate)

**Solution**: Fast API transcription + intelligent text processing

## Target Users ✅ DEFINED

### Primary User Profile

**Phase 1 (MVP)**: Developer and close circle
- Russian-speaking Telegram users
- Tech-savvy individuals comfortable with bots
- Users who receive many voice messages
- Users who value speed and quality (API-first approach)

**Phase 2 (Public)**: General Telegram audience
- Professionals managing high message volume
- Users in noise-sensitive environments
- People with accessibility needs
- Multi-language communities

### User Personas

**Persona 1: "Busy Professional"**
- Receives 10-20 voice messages daily
- Needs to quickly scan content during work
- Values speed and accuracy
- Willing to pay for unlimited access

**Persona 2: "Quality Seeker"**
- Values accuracy and speed over zero cost
- Wants professional-looking transcriptions
- Appreciates intelligent text processing
- Willing to pay for quality service

**Persona 3: "Accessibility User"**
- Hearing impairment or language barriers
- Needs text format for voice content
- Uses assistive technologies
- Benefits from free tier

## Product Vision ✅ ESTABLISHED

### What Success Looks Like

**Version 1.0 (MVP)** - ✅ Complete (2025-10-24)
- Accepts voice messages in private chats
- Transcribes using faster-whisper medium model
- Returns text within 30 seconds for 1-minute audio
- Queue-based processing with progress feedback

**Version 2.0 (Interactive)** - ✅ Complete (2025-12-25)
- OpenAI API transcription (5-10s for 1-minute audio)
- DeepSeek V3 text processing (structuring, magic, summary)
- Interactive keyboard with mode switching
- Variant caching in database
- Document and video file support (up to 2GB)
- All file types: voice, audio, documents, videos

**Version 3.0 (Future)** - Phase 11+
- Analytics dashboard
- Quotas & billing system
- Multi-language support beyond Russian

### Core User Experience ✅ DESIGNED

**Interaction Model**: Direct chat with bot
- Private chat focused (groups in future)
- Simple command-based interface
- Minimal learning curve

**Primary User Flow**:
1. **User** sends voice/audio/video file to bot
2. **Bot** immediately acknowledges with "⏳ Обрабатываю..." (Processing...)
3. **Bot** downloads file (Bot API or Telethon for >20MB)
4. **Bot** transcribes using OpenAI API (5-10s for 1-minute audio)
5. **Bot** processes with DeepSeek V3 (2-5s for structuring)
6. **User** receives structured text with interactive keyboard:
   - Исходный текст (Original)
   - 📝 Структурировать (Structure)
   - 🪄 Сделать красиво (Magic)
   - 📋 О чем этот текст (Summary)
7. **User** can switch modes, adjust emoji/length/timestamps
8. **User** can retranscribe with different quality options

**Performance**:
- Total time: 7-15 seconds (vs 20-36s local)
- Quality: Excellent for Russian speech
- Features: LLM-powered transformations

**Current Status**: Free during user acquisition, no quota checks yet

**Error Scenarios**:
- Quota exceeded: "❌ Превышен дневной лимит..."
- Queue full: "⚠️ Сервис перегружен. Попробуйте через 30 секунд."
- Processing timeout: "❌ Не удалось обработать. Попробуйте снова."
- Too long: "❌ Максимальная длительность: 5 минут"

## Value Proposition ✅ UPDATED (2025-01-09)

**Core Value**: Best-in-class voice-to-text with exceptional UX

**Current Key Differentiators:**
1. **Speed**: OpenAI API transcription in 5-10 seconds (vs 20-36s local)
2. **Quality**: Best-in-class Russian speech recognition (OpenAI whisper-1)
3. **Intelligence**: LLM-powered structuring, summary, magic modes
4. **Reliability**: API with local fallback = always works
5. **File Support**: Any audio/video format (up to 2GB)

**Cost Structure:**
- Transcription: $0.006 per minute
- Text processing: ~$0.0002 per 60s
- Total: ~$0.0062 per 60-second message
- **Acceptable for quality provided**

**Competitive Comparison (Updated):**
- vs. Local-only bots: 4-7x faster, better quality, LLM features
- vs. Other API bots: Interactive features, DeepSeek processing
- vs. Telegram native: More accurate, searchable, structured
- vs. Cloud APIs: Better UX, text processing, Russian-optimized

**Original Value Proposition (Archived 2025-12-25):**
- Zero API Costs: Local Whisper model, no per-request charges
- Privacy: No data sent to external services
- Speed: faster-whisper is 4x faster than alternatives
- Free Tier: 60 seconds/day sustainable for casual users

**Why Change?** See [architecture-evolution.md](./architecture-evolution.md)

---

## Current User Experience ✅ NEW (2025-01-09)

**Primary Flow:**
1. User sends voice/audio/video file
2. Bot acknowledges: "⏳ Обрабатываю..."
3. OpenAI API transcribes: 5-10 seconds (for 1-minute audio)
4. DeepSeek V3 structures: 2-5 seconds
5. User receives structured text with interactive keyboard:
   - Исходный текст (Original)
   - 📝 Структурировать (Structure)
   - 🪄 Сделать красиво (Magic)
   - 📋 О чем этот текст (Summary)

**Performance:**
- Total time: 7-15 seconds (vs 20-36s local)
- Quality: Excellent for Russian speech
- Features: LLM-powered transformations
- File types: Voice, audio, documents, videos (up to 2GB)

**User Feedback:**
- "Так быстро!" (So fast!)
- "Удобно, можно структурировать" (Convenient, can structure)
- "Намного лучше чем другие боты" (Much better than other bots)

---

## Scope ✅ DEFINED

### MVP Features (Phase 1)

**In Scope** (✅ Complete 2025-10-24):
- Voice message transcription (speech-to-text)
- Queue-based processing
- Progress tracking
- Russian language focus
- Private chat support

**Out of Scope** (Future):
- ❌ Payment integration (Phase 11+)
- ❌ Group chat support (Phase 11+)
- ❌ Multi-language support (Phase 11+)
- ❌ Analytics dashboard (Phase 11+)

### Future Enhancements Roadmap

**Phase 2-10: Interactive Features** (✅ Complete 2025-12-25)
- Text structuring (paragraphs, headings, lists)
- Magic mode (publication-ready text)
- Summary mode (key points)
- Interactive keyboard with mode switching
- Length variations (shorter/longer)
- Emoji options (4 levels)
- Timestamps for long audio
- File export (PDF for >3000 chars)
- Document and video file support
- OpenAI API integration
- Long audio chunking (>23 minutes)

**Phase 11+: Future Enhancements**
- Analytics dashboard
- Quotas & billing system
- Group chat support
- Multi-language support beyond Russian
- Advanced search capabilities

## Product Principles ✅ UPDATED (2025-01-09)

1. **User Experience First**: Fast transcription (7-15s total) > free but slow
2. **Quality Over Cost**: OpenAI API worth the price for accuracy
3. **Intelligence**: LLM-powered features (structure, magic, summary)
4. **Reliability**: API with fallback = always available
5. **Privacy**: API processing (same as Telegram itself)
6. **Simplicity**: Instant value, minimal learning curve
7. **Extensibility**: Built to grow with user needs

**Original Principles (Archived 2025-12-25):**
1. Privacy First: Local processing by default, no data sharing
2. Cost Conscious: Optimize for zero API costs
3. User Respect: Clear status, helpful errors, no spam
4. Accessibility: Free tier sufficient for casual use
5. Simplicity: Minimal learning curve, instant value
6. Extensibility: Built to grow with user needs

## Non-Goals ✅ UPDATED (2025-01-09)

What this bot intentionally **won't do**:

1. **Zero-Cost Operation**: API costs accepted for UX quality (~$0.006/min)
2. **Local-Only Processing**: API-first architecture (local is fallback)
3. **Real-time Translation**: Focus is transcription + text processing
4. **Social Features**: No user profiles, friends, or sharing
5. **Audio Generation**: No text-to-speech (TTS)
6. **Advanced Analytics**: Basic usage tracking only
7. **Multi-platform**: Telegram-only, no web app or mobile app

**Removed (2025-12-25):**
- ❌ "Audio Storage": Changed - files stored 7 days for retranscription
- ❌ "Zero API Costs": Changed - API costs accepted for UX

## User Experience Details

### Command Set

**MVP Commands**:
- `/start` - Welcome message, feature overview
- `/help` - Usage instructions
- *Send voice/audio/video* - Primary interaction, triggers transcription

**Current Interactive Features** (Phase 10, ✅ Complete):
- Inline keyboard with mode switching
- Original / Structured / Magic / Summary modes
- Length variations (shorter/longer)
- Emoji levels (0-3)
- Timestamps for long audio
- File export (PDF for >3000 chars)

**Future Commands** (Phase 11+):
- `/history` - View recent transcriptions
- `/upgrade` - Purchase additional quota
- `/language` - Set preferred language
- `/settings` - Configure preferences

### Message Formats

**Status Messages** (Russian):
- ⏳ "Обрабатываю..." (Processing)
- ✅ "Расшифровка:\n{text}" (Transcription)
- ❌ "Ошибка: {reason}" (Error)
- ℹ️ "Доступно сегодня: {seconds} сек" (Available today)

**Tone**: Friendly, concise, professional

### Performance Expectations

**Current Performance (API-First):**
- **Fast response**: Status within 1 second
- **Rapid processing**: 7-15 seconds for 1-minute audio
- **High reliability**: 99%+ success rate (API with fallback)
- **Clear feedback**: Progress updates every 5 seconds

**Original Performance (Local-Only):**
- **Slow processing**: 20-36 seconds for 1-minute audio
- **Good reliability**: 95%+ success rate
- **Resource intensive**: ~2GB RAM usage

## Success Metrics

### MVP Success Criteria

**Functional**:
- Bot accepts and transcribes voice messages
- Quota system works correctly
- Error handling is graceful

**Performance**:
- 95% of 1-minute audio transcribed in <15 seconds (API-first)
- Queue handles 10 concurrent users
- Zero downtime during normal operation (API with fallback)

**User Satisfaction**:
- Users understand how to use (no confused questions)
- Errors are self-explanatory
- Free tier meets casual use needs

### Future Metrics (Phase 2+)

- Daily active users (DAU)
- Transcription accuracy rate
- Average processing time
- Quota upgrade conversion rate
- User retention (7-day, 30-day)

## Notes

**Key Insight (2025-01-09)**: The pivot to API-first architecture (OpenAI + DeepSeek) transformed the bot from a slow local tool to a fast, intelligent service. Users now get exceptional UX (7-15s vs 20-36s), LLM-powered features, and best-in-class quality. API costs (~$0.006 per message) are acceptable for the value provided.

**Architecture Evolution**:
- **Initial (2025-10-12)**: Local-only, zero API costs, privacy-focused
- **Problem**: Too slow (20-36s), poor UX, users won't wait
- **Solution (2025-12-25)**: API-first, fast transcription, LLM features
- **Result**: 4-7x faster, better quality, happy users, acceptable costs

**User Language**: All user-facing messages in Russian, but codebase and documentation in English for broader accessibility.

**Monetization Strategy**: Currently free during user acquisition. Future: Freemium model with API cost recovery (~$18.60/month for 100 daily users). Payment integration planned for Phase 11+.
