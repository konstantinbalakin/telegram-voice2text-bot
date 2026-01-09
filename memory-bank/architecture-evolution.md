# Architecture Evolution: Local-First → API-First

**Last Updated**: 2025-01-09
**Current Status**: API-First Architecture (OpenAI + DeepSeek + Local Fallback)

---

## Initial Vision (2025-10-12)

### Goals
- Local Whisper only (faster-whisper medium)
- Zero API costs
- Complete privacy
- Cost-effective solution

### Implementation
- **Model**: faster-whisper medium/int8/beam1
- **Performance**: RTF ~0.3x (3x faster than audio)
- **Memory**: ~2GB RAM peak
- **Quality**: Excellent for Russian

### Limitations Discovered
- **Slow**: 60s audio = 20-36s processing
- **Resource-intensive**: 2GB RAM
- **No advanced features**: No structuring, no summary
- **User experience**: "Too slow"

---

## The Pivot (2025-11-20 → 2025-12-25)

### Why API-First?

#### 1. User Experience Quality
- **OpenAI API**: 5-10 seconds for 1-minute audio
- **Local**: 20-36 seconds for 1-minute audio
- **Improvement**: 4-7x faster for users

#### 2. Transcription Quality
- **OpenAI whisper-1**: Best-in-class for Russian
- **gpt-4o-transcribe**: Even better accuracy
- **Local medium**: Good but not excellent

#### 3. Feature Capabilities
- LLM text processing (DeepSeek V3)
- Structuring, summary, magic modes
- Impossible with local-only architecture

#### 4. Reliability
- **API**: 99.9% uptime, consistent quality
- **Local**: VPS crashes, memory issues, variability

#### 5. Cost Acceptability
- Transcription: $0.006/min (whisper-1)
- Text processing: ~$0.0002 per 60s (DeepSeek)
- 60s message total: ~$0.0062
- **Acceptable for quality provided**

### Migration Path

#### Phase 1: Local Only (2025-10-12 → 2025-11-19)
- faster-whisper medium/int8/beam1
- Queue-based processing
- Progress tracking
- No LLM features

#### Phase 2: Hybrid Experiment (2025-11-20 → 2025-12-04)
- Short audio: Local quality model
- Long audio: Local draft → LLM refinement
- First LLM integration (DeepSeek V3)
- Structured mode feature

#### Phase 3: API Integration (2025-12-15 → 2025-12-25)
- OpenAI API provider added
- Provider-aware preprocessing
- Long audio chunking
- Document + video support

#### Phase 4: API-First (2025-12-25 → Present)
- OpenAI API as primary transcription
- DeepSeek V3 for all text processing
- faster-whisper as fallback only
- All interactive features enabled

### Decision Timeline

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-11-20 | Add LLM refinement | Improve long audio quality |
| 2025-12-04 | Add interactive features | User feedback: "Make it beautiful" |
| 2025-12-15 | Add OpenAI provider | Better quality, reliability |
| 2025-12-25 | Make OpenAI primary | UX: speed matters most |
| 2025-01-09 | Document pivot | Clarify architecture evolution |

---

## Current Architecture (2025-01-09)

### Production Stack

#### Transcription Layer

**Primary: OpenAI API**
- Model: whisper-1 (default), gpt-4o-transcribe (optional)
- Performance: 5-10s for 1-minute audio
- Quality: Best-in-class for Russian
- Cost: $0.006/min
- Fallback: Auto-switch to whisper-1 for >23min audio

**Fallback: faster-whisper local**
- Model: medium/int8/beam1
- Performance: 20-36s for 1-minute audio
- Used: When OpenAI API unavailable

#### Text Processing Layer

**Provider: DeepSeek V3**
- Features:
  - Structured mode (paragraphs, headings, lists)
  - Magic mode (publication-ready text)
  - Summary mode (key points)
- Performance: 2-5s processing time
- Cost: ~$0.0002 per 60s audio
- Quality: Excellent Russian text transformation

#### File Support
- Voice messages (Telegram standard)
- Audio files (MP3, OGG, WAV, etc.)
- Documents (.aac, .flac, .wma, .amr, etc.)
- Videos (.mp4, .mkv, .avi, .mov with audio extraction)
- Large files: Up to 2GB via Telethon

#### Interactive Features
- Inline keyboard with 3 main buttons:
  - 📝 Структурировать (Structure)
  - 🪄 Сделать красиво (Magic)
  - 📋 О чем этот текст (Summary)
- Variant caching in database
- File export for long text (>3000 chars)

### Architecture Diagram

```
User sends voice/audio/video
  ↓
Bot handler (type detection)
  ↓
File download (Bot API or Telethon)
  ↓
Audio extraction (if video)
  ↓
┌─────────────────────────────────┐
│ Primary: OpenAI API             │
│ - whisper-1 or gpt-4o-transcribe │
│ - 5-10 seconds for 1-minute      │
└─────────────────────────────────┘
  ↓ (if API fails)
┌─────────────────────────────────┐
│ Fallback: faster-whisper        │
│ - medium/int8/beam1             │
│ - 20-36 seconds for 1-minute    │
└─────────────────────────────────┘
  ↓
Transcription result
  ↓
┌─────────────────────────────────┐
│ DeepSeek V3 (LLM)               │
│ - Structured / Magic / Summary  │
│ - 2-5 seconds processing        │
└─────────────────────────────────┘
  ↓
Interactive keyboard
- Original / Structured / Magic / Summary
- Variant caching
- File export (if long)
  ↓
User response
```

### Configuration

**Environment Variables (.env):**
```bash
# Transcription providers
WHISPER_PROVIDERS=["openai", "faster-whisper"]
PRIMARY_PROVIDER=openai
FALLBACK_PROVIDER=faster-whisper
OPENAI_MODEL=whisper-1

# LLM text processing
LLM_REFINEMENT_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-...

# Interactive features
INTERACTIVE_MODE_ENABLED=true
ENABLE_STRUCTURED_MODE=true
ENABLE_MAGIC_MODE=true
ENABLE_SUMMARY_MODE=true
```

### Performance Metrics

| Operation | API-First | Local-Only | Improvement |
|-----------|-----------|------------|-------------|
| 60s audio transcription | 5-10s | 20-36s | **4-7x faster** |
| Text structuring | 2-5s | N/A | New feature |
| Total end-to-end | 7-15s | 20-36s | **2-5x faster** |
| Memory usage | <500MB | ~2GB | **4x less** |
| CPU usage | Low | High | **Significant** |

### Cost Structure

**Per 60-second message:**
- OpenAI transcription: $0.006
- DeepSeek processing: ~$0.0002
- **Total: ~$0.0062 per message**

**Monthly estimates:**
- 100 messages/day × 30 days = 3000 messages
- 3000 × 60s = 180,000 seconds = 50 hours
- Cost: 3000 × $0.0062 = **$18.60/month**

**Comparison:**
- Free (local): $0 but poor UX
- API-first: $18.60/month for 100 daily users
- **Conclusion**: Cost acceptable for UX quality

### Benefits Realized

1. **User Experience**: 4-7x faster = users actually use the bot
2. **Quality**: OpenAI > local for Russian speech
3. **Features**: Structuring, magic, summary (impossible locally)
4. **Reliability**: API with fallback = always works
5. **Resource usage**: 4x less memory/CPU on VPS
6. **Scalability**: Can handle 10x more users

### Trade-offs Accepted

1. **Cost**: $18.60/month vs $0 (but worth it for UX)
2. **Privacy**: Data sent to API (but same as Telegram itself)
3. **Dependency**: Require internet + API keys (acceptable for production)

---

## Future Considerations

### Potential Improvements
- **Cost optimization**: Cache common phrases, batch requests
- **Hybrid mode**: Short = local, long = API (balanced approach)
- **Multiple providers**: Add Azure, Google Speech for redundancy
- **Local LLM**: Run DeepSeek-like model locally when hardware allows

### Monitoring Metrics
- API cost per user/month
- Average transcription time
- Error rate (API failures)
- Feature usage (structure/magic/summary)
- User satisfaction feedback

---

## Related Documentation

- [Current System Patterns](./systemPatterns.md) - Essential implementation patterns
- [Technical Context](./techContext.md) - Current technology stack
- [Project Brief](./projectbrief.md) - Project goals and status
- [Product Context](./productContext.md) - User experience and value props
