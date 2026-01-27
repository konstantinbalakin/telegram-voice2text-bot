# System Patterns: Telegram Voice2Text Bot

**Last Updated**: 2026-01-27
**Architecture**: API-First (OpenAI + DeepSeek + Local Fallback)

---

## Current Architecture Overview

### High-Level Design

Current architecture is **API-first** with intelligent text processing:

```
User Input (Voice/Audio/Video)
  ↓
File Detection & Download
  ↓
┌──────────────────────────────────────┐
│ Primary: OpenAI API (whisper-1)      │
│ - Fast: 5-10s for 1-minute audio      │
│ - Quality: Best-in-class Russian      │
└──────────────────────────────────────┘
  ↓ (if API fails)
┌──────────────────────────────────────┐
│ Fallback: faster-whisper (local)     │
│ - Model: medium/int8/beam1           │
│ - Slower: 20-36s for 1-minute audio  │
└──────────────────────────────────────┘
  ↓
┌──────────────────────────────────────┐
│ LLM: DeepSeek V3                     │
│ - Structure, Magic, Summary modes    │
│ - 2-5s processing time               │
└──────────────────────────────────────┘
  ↓
Interactive Keyboard + Variant Caching
```

**See:** [architecture-evolution.md](./architecture-evolution.md) for complete story

---

## Essential Patterns (15 Critical Patterns)

### 1. API-First Transcription Pattern

**Problem:** Local transcription too slow (20-36s) for good UX

**Solution:** Use OpenAI API as primary, local model as fallback

**Implementation:**
```python
# In routing strategy
if primary_provider == "openai":
    try:
        result = await openai_provider.transcribe(audio)
    except APIError:
        result = await fallback_provider.transcribe(audio)
```

**Benefits:**
- 4-7x faster (5-10s vs 20-36s)
- Better quality (OpenAI > local)
- Reliable (fallback ensures availability)

**Added:** 2025-12-25
**Location:** `src/transcription/routing/strategies.py`

---

### 2. LLM Text Processing Pattern

**Problem:** Raw transcription needs intelligent structuring

**Solution:** Use DeepSeek V3 for text transformation

**Implementation:**
```python
# In TextProcessor
async def create_structured(self, text: str) -> str:
    prompt = load_prompt("prompts/structured.md")
    refined = await llm_service.refine_text(text, prompt)
    return sanitize_html(refined)
```

**Features:**
- Structured mode (paragraphs, headings, lists)
- Magic mode (publication-ready, author's voice)
- Summary mode (key points)

**Benefits:**
- Professional-looking text
- Scannable structure
- Quick comprehension

**Added:** 2025-12-04
**Location:** `src/services/text_processor.py`

---

### 3. Fallback Strategy Pattern

**Problem:** API can fail (network, rate limits, downtime)

**Solution:** Graceful degradation to local model

**Implementation:**
```python
try:
    result = await openai_provider.transcribe(audio)
except (APIError, Timeout, NetworkError) as e:
    logger.warning(f"OpenAI failed: {e}, using fallback")
    result = await faster_whisper_provider.transcribe(audio)
```

**Key Features:**
- Automatic fallback on errors
- User sees result either way
- Logging for monitoring

**Benefits:**
- Always returns transcription
- No user-facing errors
- Reliability = trust

**Added:** 2025-12-15
**Location:** `src/transcription/routing/strategies.py`

---

### 4. Variant Caching Pattern

**Problem:** Re-generating same text variant wastes API money

**Solution:** Cache in database with composite key

**Implementation:**
```python
# Check cache first
existing = await variant_repo.get_variant(
    usage_id, mode="structured", length="default", emoji=1
)
if existing:
    return existing.text_content

# Generate and cache
structured = await text_processor.create_structured(original)
await variant_repo.create(
    usage_id=usage_id,
    mode="structured",
    text_content=structured
)
```

**Key:**
- Composite unique key: (usage_id, mode, length, emoji, timestamps)
- Prevents duplicate LLM calls
- Fast re-display on mode switch

**Benefits:**
- Cost savings (no duplicate API calls)
- Fast re-display (database read vs LLM call)
- Better UX (instant mode switching)

**Added:** 2025-12-03
**Location:** `src/storage/repositories.py`

---

### 5. Interactive Keyboard Pattern

**Problem:** Users want text variations without re-sending

**Solution:** Inline keyboard with mode switching

**Implementation:**
```python
keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Исходный текст", callback_data="mode:original")],
    [InlineKeyboardButton("📝 Структурировать", callback_data="mode:structured")],
    [InlineKeyboardButton("🪄 Сделать красиво", callback_data="mode:magic")],
    [InlineKeyboardButton("📋 О чем этот текст", callback_data="mode:summary")],
])
```

**Key Features:**
- Mode switching (original/structured/magic/summary)
- Emoji/length/timestamps options
- "Currently viewing" indicator
- State tracking in database

**Benefits:**
- Rich interaction without re-sending
- Explore different transformations
- Single message for all variants

**Added:** 2025-12-03
**Location:** `src/bot/keyboards.py`, `src/bot/callbacks.py`

---

### 6. File Delivery Pattern

**Problem:** Telegram 4096 char limit, long text needs file

**Solution:** Threshold-based delivery (text vs file)

**Implementation:**
```python
FILE_THRESHOLD_CHARS = 3000  # Conservative limit

if len(text) <= FILE_THRESHOLD_CHARS:
    # Send as message with keyboard
    await message.reply_text(text, reply_markup=keyboard)
else:
    # Send as file + info message with keyboard
    info_msg = await message.reply_text("📝 Транскрипция готова! Файл ниже ↓", reply_markup=keyboard)
    file_obj = io.BytesIO(text.encode("utf-8"))
    await message.reply_document(document=file_obj, filename="transcription.txt")
```

**Key Features:**
- Threshold: 3000 chars (conservative)
- Two-message pattern (info + file)
- Keyboard on info message
- State tracking (is_file_message)

**Benefits:**
- No data loss for long text
- Professional PDF for >3000 chars
- Consistent UX across all message types

**Added:** 2025-12-08
**Location:** `src/bot/handlers.py`

---

### 7. Progress Tracking Pattern

**Problem:** Long operations need user feedback

**Solution:** Background task updates message every 5 seconds

**Implementation:**
```python
progress = ProgressTracker(
    message=status_msg,
    duration_seconds=audio_duration,
    rtf=0.3,  # Real-time factor
    update_interval=5
)
await progress.start()

# Automatically updates with progress bar:
# 🔄 [████████░░░░] 40% (12s / 30s)

await progress.stop()
```

**Key Features:**
- Visual progress bar
- RTF-based time estimation
- Telegram rate limit handling
- Graceful cleanup

**Benefits:**
- Reduces perceived wait time
- Shows system is working
- Transparent about progress

**Added:** 2025-10-29
**Location:** `src/services/progress_tracker.py`

---

### 8. Queue Management Pattern

**Problem:** Concurrent transcriptions crash VPS (1GB RAM)

**Solution:** Bounded queue with sequential processing

**Implementation:**
```python
queue_manager = QueueManager(
    max_queue_size=10,  # Max pending requests
    max_concurrent=1,    # Sequential processing
)

# Enqueue with position tracking
position = await queue_manager.enqueue(request)

# Worker processes sequentially
async def _process_request(request):
    result = await transcribe(request.file_path)
    await send_result(request.chat_id, result)
```

**Key Features:**
- FIFO queue (max 10 pending)
- Sequential processing (1 at a time)
- Atomic position tracking
- Graceful backpressure

**Benefits:**
- No crashes (resource limits respected)
- Fair ordering (FIFO)
- Predictable performance

**Added:** 2025-10-29
**Location:** `src/services/queue_manager.py`

---

### 9. Provider-Aware Preprocessing Pattern

**Problem:** Different providers need different audio formats

**Solution:** Preprocess based on target provider

**Implementation:**
```python
def preprocess_audio(audio_path, target_provider):
    if target_provider == "openai":
        model = settings.openai_model
        if model in ["gpt-4o-transcribe", "gpt-4o-mini-transcribe"]:
            # These models require MP3/WAV
            return convert_to_mp3(audio_path)
        else:
            # whisper-1 supports OGA
            return audio_path
    elif target_provider == "faster-whisper":
        # OGA optimal for local
        return audio_path
```

**Key Features:**
- Smart format conversion (only when needed)
- Optimal format per provider
- Backward compatible

**Benefits:**
- Enables new OpenAI models (gpt-4o-*)
- No unnecessary conversions
- Best performance per provider

**Added:** 2025-12-15
**Location:** `src/transcription/audio_handler.py`

---

### 10. Graceful Degradation Pattern

**Problem:** LLM failures shouldn't block users

**Solution:** Always fallback to original text

**Implementation:**
```python
try:
    structured = await llm_service.refine_text(original, prompt)
    final_text = sanitize_html(structured)
except (LLMTimeoutError, LLMAPIError, Exception) as e:
    logger.error(f"LLM failed: {e}")
    final_text = original  # Fallback to original

# Always return something
await send_result(final_text)
```

**Key Features:**
- Try LLM first
- Catch all exceptions
- Fallback to original
- Never block user

**Benefits:**
- Users always get result
- No error messages for failures
- Better UX (graceful vs broken)

**Added:** 2025-11-20
**Location:** `src/bot/handlers.py`, `src/services/llm_service.py`

---

### 11. Feature Flags Pattern

**Problem:** Need safe rollout for new features

**Solution:** Environment-based feature toggles

**Implementation:**
```python
# In config.py
interactive_mode_enabled: bool = Field(default=False)
enable_structured_mode: bool = Field(default=False)
enable_magic_mode: bool = Field(default=False)

# In handlers
if settings.enable_structured_mode:
    keyboard.add(structured_button)
```

**Key Features:**
- Master switch + per-feature flags
- Disabled by default
- Gradual rollout possible

**Benefits:**
- Deploy code without activating
- Test with specific users
- Quick disable if issues

**Added:** 2025-12-03
**Location:** `src/config.py`, `src/bot/keyboards.py`

---

### 12. State Management Pattern

**Problem:** Track UI state per transcription (mode, emoji, length)

**Solution:** Database model with state fields

**Implementation:**
```python
class TranscriptionState(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    usage_id: Mapped[int] = mapped_column(ForeignKey("usage.id"))
    message_id: Mapped[int]  # For keyboard updates
    active_mode: Mapped[str]  # "original", "structured", "magic", "summary"
    emoji_level: Mapped[int]  # 0-3
    length_level: Mapped[str]  # "shorter", "short", "default", "long", "longer"
    timestamps_enabled: Mapped[bool]
    is_file_message: Mapped[bool]
```

**Key Features:**
- Tracks all UI state
- Allows mode switching
- Keyboard updates based on state

**Benefits:**
- Rich interactive UX
- State persistence
- Accurate keyboard display

**Added:** 2025-12-03
**Location:** `src/storage/models.py`

---

### 13. Error Handling Pattern

**Problem:** Users see cryptic errors, don't know what to do

**Solution:** Clear, actionable error messages in Russian

**Implementation:**
```python
try:
    result = await transcribe(audio)
except AudioTooLongError:
    await message.reply_text(
        f"⚠️ Максимальная длительность: {limit}с\n"
        f"Ваш файл: {user_duration}с ({user_duration // 60}м {user_duration % 60}с)"
    )
except QueueFullError:
    await message.reply_text(
        f"⚠️ Очередь переполнена. Попробуйте через {wait_time}с.\n"
        f"В очереди: {queue_depth} запросов"
    )
except TranscriptionError:
    await message.reply_text("❌ Не удалось обработать. Попробуйте снова.")
```

**Key Features:**
- Russian language
- Emoji for clarity
- Actionable advice
- Context information (duration, queue depth)

**Benefits:**
- Users understand what happened
- Clear next steps
- Better support experience

**Added:** 2025-10-29
**Location:** `src/bot/handlers.py`

---

### 14. Long Audio Handling Pattern

**Problem:** OpenAI gpt-4o models have ~23min duration limit

**Solution:** Three strategies (model switch, parallel chunking, sequential)

**Implementation:**
```python
if duration > settings.openai_gpt4o_max_duration:
    if settings.openai_change_model:
        # Strategy 1: Switch to whisper-1 (no limit)
        return await openai_provider.transcribe(audio, model="whisper-1")
    elif settings.openai_chunking:
        if settings.openai_parallel_chunks:
            # Strategy 2: Parallel chunking (fast)
            chunks = split_audio(audio, overlap=2s)
            results = await asyncio.gather(*[transcribe(c) for c in chunks])
        else:
            # Strategy 3: Sequential chunking (context preservation)
            chunks = split_audio(audio, overlap=2s)
            results = []
            for chunk in chunks:
                context = results[-1] if results else None
                result = await transcribe(chunk, context=context)
                results.append(result)
        return " ".join(results)
```

**Key Features:**
- Auto model switch (default)
- Parallel chunking (2-3x faster)
- Sequential chunking (context preservation)
- 2-second overlap prevents word cutting

**Benefits:**
- Unlimited duration audio
- Flexible strategies
- No quality loss

**Added:** 2025-12-17
**Location:** `src/transcription/providers/openai_provider.py`

---

### 15. Multi-File Support Pattern

**Problem:** Users send audio in various formats (documents, videos)

**Solution:** Universal file type handling

**Implementation:**
```python
# Voice handler (standard)
application.add_handler(MessageHandler(filters.VOICE, voice_handler))

# Audio handler (music files)
application.add_handler(MessageHandler(filters.AUDIO, audio_handler))

# Document handler (audio files as documents)
application.add_handler(MessageHandler(filters.DOCUMENT, document_handler))
# MIME type validation: audio/* only

# Video handler (extract audio)
application.add_handler(MessageHandler(filters.VIDEO, video_handler))
# Extract audio track with ffmpeg
```

**Key Features:**
- 4 handlers for different file types
- MIME type validation for documents
- Audio extraction from video
- Unified transcription pipeline

**Benefits:**
- Support any audio-containing file
- Better UX (no "wrong format" errors)
- Professional (handles videos)

**Added:** 2025-12-25
**Location:** `src/bot/handlers.py`, `src/transcription/audio_handler.py`

---

## Historical Patterns Reference

The following patterns have been implemented throughout the project's evolution.
For detailed documentation, see the archived version: `systemPatterns-2025-01-09-pre-update.md`

### Architecture & Design Patterns (8 patterns)
1. **Producer-Consumer Pattern** - Queue-based request processing
2. **Repository Pattern** - Database access abstraction
3. **Service Layer Pattern** - Business logic encapsulation
4. **Thread Pool Pattern** - CPU-bound work isolation
5. **Middleware Pattern** - Cross-cutting concerns (quota, rate limit)
6. **Configuration Object Pattern** - Pydantic settings
7. **Strategy Pattern** - Provider routing (single/fallback/benchmark/hybrid/structure)
8. **Factory Pattern** - Provider instantiation

### Queue & Progress Patterns (4 patterns)
9. **Queue-Based Request Management** - Bounded FIFO queue
10. **Progress Tracking** - Live progress bar updates
11. **Staged Database Writes** - Lifecycle tracking (download → transcribe → refine)
12. **Graceful Degradation** - Clear error messages

### Large File Support (1 pattern)
13. **Hybrid Download Strategy** - Bot API ≤20MB + Client API >20MB

### Logging & Observability (11 patterns)
14. **Version-Enriched Logging** - Add version/container_id to all logs
15. **Size-Based Log Rotation** - 10MB files, 5 backups
16. **Deployment Event Tracking** - JSONL deployment log
17. **Structured JSON Logging** - Machine-readable logs
18. **Optional Remote Syslog** - Centralized logging
19. **Automatic Semantic Versioning** - v0.X.Y auto-increment
20. **Separated Build and Deploy Workflow** - Two-stage CI/CD
21. **Workflow Dispatch for Manual Deployments** - gh workflow trigger
22. **Version-Tagged Docker Images** - latest + SHA tags
23. **GitHub Releases for Changelog** - Auto-generated
24. **Iterative Workflow Testing** - Multiple CI/CD iterations

### Queue Management (5 patterns)
25. **Atomic Counter for Queue Position** - Accurate position tracking
26. **Unique File Naming with UUID** - Prevent concurrent access conflicts
27. **Callback Pattern for Queue Changes** - Observer pattern
28. **Dual List Tracking** - Pending + processing lists
29. **Dynamic Message Update** - Update all pending messages

### Hybrid & LLM Patterns (7 patterns)
30. **Hybrid Transcription Strategy** - Duration-based routing
31. **LLM Post-Processing** - Draft + refinement workflow
32. **Staged UI Updates** - Show draft, then refine
33. **Audio Preprocessing Pipeline** - Mono conversion, speed adjustment
34. **Abstract LLM Provider** - Pluggable LLM providers
35. **Graceful Degradation for LLM** - Always return draft
36. **Feature Flags for Production Safety** - Disable by default

### Text Processing Patterns (3 patterns)
37. **Relative LLM Instructions** - Qualitative vs quantitative prompts
38. **Threshold-Based File Delivery** - Text vs PDF based on length
39. **Circular Import Resolution** - Function-level imports

### Advanced Features (5 patterns)
40. **Parent-Child Usage Tracking** - Retranscription history
41. **Progress Bar with Dynamic Duration** - Method-specific estimation
42. **Refinement Control via Context** - Skip refinement for retranscription
43. **Provider-Aware Preprocessing** - Format optimization per provider
44. **Audio Chunking with Overlap** - Long audio splitting
45. **Universal File Type Support** - Voice + audio + documents + video
46. **Audio Extraction from Video** - ffmpeg-based extraction
47. **ffprobe-Based Duration Detection** - Document/video duration

**Total:** 47 patterns implemented across 4 development months

---

## Development Workflow

### Local Development
1. Create feature branch from `main`
2. Make changes with test coverage
3. Run quality checks: `make check` (mypy, ruff, black, pytest)
4. Commit with conventional commits format
5. Push and create PR for code review

### CI/CD Pipeline
1. **On Pull Request**: Automated tests + quality checks
2. **On Merge to main**: Build Docker image + push to registry
3. **Automatic Deployment**: VPS pulls latest image + restarts bot
4. **Versioning**: Automatic patch increment (v0.0.X)

### Git Workflow
- **Protected Branch**: `main` (requires PR + review)
- **Feature Branches**: `feature/`, `fix/`, `docs/` prefixes
- **Commit Format**: Conventional Commits (feat:, fix:, docs:, etc.)
- **Pull Request**: Required for all changes
- **Deployment**: Automatic on merge to main

### Code Quality Standards
- **Type Hints**: Required for all functions (mypy strict mode)
- **Testing**: pytest with >80% coverage target
- **Formatting**: black (line length 100)
- **Linting**: ruff (fast linter)
- **Documentation**: Docstrings for public APIs

---

## Key Technical Decisions

**Update:** Mark local-first decisions as "Historical"

| Date | Decision | Status | Rationale |
|------|----------|--------|-----------|
| 2025-10-12 | Python 3.11+ | ✅ Active | Best Whisper integration |
| 2025-10-12 | python-telegram-bot | ✅ Active | Most mature library |
| 2025-10-12 | faster-whisper | ⚠️ Fallback | Kept for reliability |
| 2025-10-12 | Hybrid Queue Architecture | ✅ Active | Balanced scalability |
| 2025-10-12 | SQLAlchemy + SQLite/PostgreSQL | ✅ Active | Good migration path |
| 2025-12-25 | **OpenAI API Primary** | ✅ **Active** | **Best UX (speed + quality)** |
| 2025-12-25 | **DeepSeek V3 for LLM** | ✅ **Active** | **Intelligent text processing** |
| 2025-12-25 | **Local model fallback** | ✅ **Active** | **Reliability** |

**For complete evolution story:** See [architecture-evolution.md](./architecture-evolution.md)

---

## Related Documentation

- [Architecture Evolution](./architecture-evolution.md) - Complete pivot story
- [Technical Context](./techContext.md) - Current technology stack
- [Project Brief](./projectbrief.md) - Project goals and status
- [Product Context](./productContext.md) - User experience and value props
