# Active Context: Telegram Voice2Text Bot

## Current Status (2025-12-08)

**Phase**: Phase 10 - Interactive Transcription Processing 🚀
**Stage**: Phase 10.7 COMPLETE ✅ → Ready for Phase 10.8 (Retranscription)
**Branch**: `docs/phase10-interactive-transcription-plan`
**Production Version**: v0.0.3+
**Production Status**: ✅ OPERATIONAL

### Infrastructure
- **VPS**: 3GB RAM, 4 CPU cores (Russian VPS, ~$10-15/month)
- **Docker**: Automated builds and deployments
- **CI/CD**: Fully automatic (GitHub Actions)
- **Database**: SQLite with automated migrations
- **Bot**: Live on Telegram, healthy, responding

### Current Configuration

**Whisper Model**: `faster-whisper / medium / int8 / beam1`
- Performance: RTF ~0.6x (60s audio → ~36s)
- Quality: Excellent for Russian language
- Resources: ~2GB RAM peak

**Hybrid Transcription** (Optional, disabled by default):
- Short audio (<20s): Quality model directly
- Long audio (≥20s): Fast draft (small model) + LLM refinement
- Performance: 6-9x faster for long audio
- Cost: ~$0.0002 per 60s (DeepSeek V3)

**Queue System**:
- FIFO with atomic position tracking
- Sequential processing (max_concurrent=1)
- Live progress updates every 5s
- Duration limit: 120s max, Queue size: 10 requests

---

## Recent Developments (Last 2 Weeks)

### ✅ Phase 10.7: Interactive Transcription - Phase 7 (File Handling) COMPLETE (2025-12-08)

**Achievement**: Automatic file attachment for long transcription variants (>4096 characters)

**What Was Implemented**:
1. **File Generation** (`src/services/file_handler.py`, NEW FILE, 163 lines):
   - `FileHandler` class for managing transcription file exports
   - `export_transcription_to_file()` - Main method generates .txt with UTF-8 encoding
   - `_get_filename()` - Creates descriptive filenames (transcription_[mode]_[timestamp].txt)
   - `_get_caption()` - Generates informative captions with metadata
   - Automatic cleanup after sending
   - Thread-safe temp directory management

2. **Callback Handler Updates** (`src/bot/callbacks.py`):
   - `_send_variant_message()` method enhanced (lines 171-302)
   - Detects text length before sending (>4096 chars threshold)
   - Sends as file when needed with proper caption
   - Sends as edited message when within limits
   - Creates keyboard markup after determining send method
   - Proper error handling for all scenarios

3. **Testing**:
   - Comprehensive test suite: `tests/unit/test_file_handler.py` (183 lines)
   - 12 unit tests covering all functionality
   - Tests: filename generation, caption formatting, file export, cleanup
   - All 148 tests passing (136 existing + 12 new)

**User Experience**:
```
User requests structured mode for long audio transcription
  ↓
Bot generates structured text (6000+ chars)
  ↓
Bot detects text length exceeds 4096 chars
  ↓
Bot sends file:
📄 transcription_structured_20251208_143052.txt
Caption: 📝 Структурированный текст
Длина: 6234 символов
  ↓
Keyboard with buttons still appears in caption
[Исходный текст]
[📝 Структурировать (вы здесь)]
[💡 О чем текст?]
[😊 Смайлы]
[🕐 Таймкоды]
```

**Files Created**:
- `src/services/file_handler.py` (163 lines, NEW)
- `tests/unit/test_file_handler.py` (183 lines, NEW)

**Files Modified**:
- `src/bot/callbacks.py` (+132 lines, refactored `_send_variant_message()`)
- `src/services/__init__.py` (+2 lines, export FileHandler)

**Key Patterns Established**:
1. **Length Detection Before Sending**: Check text length and choose appropriate delivery method
2. **Descriptive Filenames**: Include mode and timestamp for easy identification
3. **Informative Captions**: Show text length and mode in caption
4. **Keyboard in Caption**: Buttons work even when content is file attachment
5. **Automatic Cleanup**: Always clean up temp files after sending
6. **Thread-Safe Temp Directory**: Use proper temp directory management

**Impact**:
- ✅ Supports transcriptions of any length
- ✅ No data loss from truncation
- ✅ Clean UX with file downloads
- ✅ All interactive features work with files
- ✅ Proper error handling and cleanup

**Testing**: ✅ All 148 tests passed (136 + 12 new file handler tests)
**Status**: ✅ Complete, tested, ready for Phase 8 (Retranscription)
**Completion Date**: 2025-12-08
**Next**: Phase 10.8 - Retranscription with different quality settings

---

### ✅ Phase 10.6: Interactive Transcription - Phase 6 (Timestamps) COMPLETE (2025-12-05)

**Achievement**: Timestamp formatting for audio >5 minutes with toggle functionality

**What Was Implemented**:
1. **TextProcessor Timestamp Methods** (`src/services/text_processor.py:379-480`):
   - `format_with_timestamps()` - Main method for adding timestamps
   - `_format_time()` - Formats seconds as [MM:SS] or [HH:MM:SS]
   - `_format_timestamps_summary()` - Simplified strategy for summary mode
   - Different strategies: original/structured (each segment) vs summary (first segment only)

2. **Keyboard Integration** (`src/bot/keyboards.py:271-280`):
   - Row 5: "🕐 Таймкоды" toggle button
   - Only shown for audio >5 min (when segments exist)
   - Label changes: "🕐 Таймкоды" ↔ "Убрать таймкоды"

3. **Callback Handler** (`src/bot/callbacks.py:778-931`):
   - `handle_timestamps_toggle()` - 120-line toggle implementation
   - Checks segment availability before processing
   - Generates timestamped variants on-demand
   - Caches variants with generated_by="formatting"
   - Synchronous formatting (no LLM needed)

4. **Tests** (`tests/unit/test_text_processor_timestamps.py`):
   - 15 comprehensive unit tests
   - TestFormatTime: 6 tests (seconds, minutes, hours, boundaries)
   - TestFormatWithTimestamps: 6 tests (single, multiple segments, modes, empty)
   - TestFormatTimestampsSummary: 3 tests (first segment, empty, multiline)
   - All 136 tests passing

**User Experience**:
```
Audio >5 min transcribed
  ↓
[Исходный текст]
[📝 Структурировать]
[💡 О чем текст?]
[😊 Смайлы]
[🕐 Таймкоды]  ← Click to add timestamps
  ↓
Text updates:
[00:00] Первая фраза текста.
[00:15] Вторая фраза текста.
[00:32] Третья фраза текста.
  ↓
[Убрать таймкоды]  ← Shows enabled state
```

**Bug Fixes During Implementation**:
1. **Emoji Button in Summary/Structured Modes** (`src/bot/keyboards.py:205-257`):
   - Problem: emoji_level > 0 showed non-functional "😊 Смайлы" button
   - Solution: Restructured logic to show "Убрать смайлы" when emoji_level > 0
   - User feedback: "чет для 30секундного аудио изменения смайлов перестали работать"

2. **Segments Storage Optimization** (`src/bot/handlers.py`):
   - Problem: Segments saved even when ENABLE_TIMESTAMPS_OPTION=false
   - Solution: Added feature flag check before saving segments
   - Now only saves when feature enabled
   - Added debug logging for disabled feature case

**Files Modified**:
- `src/services/text_processor.py` (+102 lines) - Timestamp formatting methods
- `src/bot/keyboards.py` (+10 lines, fixed emoji logic) - Row 5 timestamps button
- `src/bot/callbacks.py` (+154 lines) - Toggle handler and router update
- `src/bot/handlers.py` (+11 lines, -2 lines) - Segments storage optimization
- `tests/unit/test_text_processor_timestamps.py` (+169 lines, NEW) - Comprehensive test suite

**Testing**: ✅ All 136 tests passed (121 + 15 new timestamp tests)
**Status**: ✅ Complete, tested, ready for Phase 7 (File Handling)
**Completion Date**: 2025-12-05
**Next**: Phase 10.7 - File handling for text >4096 chars

---

### ✅ Phase 10.5: Interactive Transcription - Phase 5 (Emoji Option) COMPLETE (2025-12-04)

**Achievement**: LLM-powered emoji enhancement for transcriptions with 4 levels of control

**What Was Implemented**:
1. **LLM Prompt** (`prompts/emoji.md`):
   - Flexible template with {instruction} placeholder
   - Requirements for natural emoji distribution
   - Emoji placement guidelines (paragraphs, key phrases)

2. **TextProcessor Emoji Method** (`src/services/text_processor.py:303-378`):
   - `add_emojis()` method with 4 levels: 0 (none), 1 (few), 2 (moderate), 3 (many)
   - Relative instructions that adapt to text length
   - LLM refinement with graceful fallback

3. **Keyboard Integration** (`src/bot/keyboards.py:205-255`):
   - Row 4: Emoji controls
   - Default button "😊 Смайлы" activates level 2 (moderate)
   - Expanded controls: [Меньше/Убрать] [😊/😊😊/😊😊😊] [Больше]
   - 3 emoji indicators showing current level

4. **Callback Handlers** (`src/bot/callbacks.py:592-777`):
   - `handle_emoji_toggle()` with 4-level logic
   - Direction: "moderate" (default), "increase", "decrease"
   - Variant caching and state management

**User Feedback & Improvements**:
- **Problem**: Initial 3-level implementation (0/1/2) with hard-coded counts (1-2, 3-5 emojis)
  - User: "На маленький текст это норм. А вот если большой текст, то эти смайлы теряются"
  - Fixed emoji counts didn't scale with text length
  - Default button to level 1 gave too few emojis

- **Solution**:
  - Expanded to 4 levels (0/1/2/3) for finer control
  - Changed default to level 2 (moderate) for balanced first impression
  - Replaced hard counts with relative instructions ("минимальное количество", "умеренное количество", "щедрое количество")
  - LLM now adapts emoji density to text length

**Key Pattern Established**:
**Relative LLM Instructions Over Hard Counts**: For features that scale with content size (emojis, summaries), use qualitative descriptions instead of specific numbers. This allows the LLM to adapt intelligently to varying text lengths - more emojis for long texts, fewer for short texts, all from the same prompt.

**Files Modified**:
- `prompts/emoji.md` (created)
- `src/services/text_processor.py` (lines 303-378)
- `src/bot/keyboards.py` (lines 205-255)
- `src/bot/callbacks.py` (lines 592-777)

**Testing**: ✅ All 121 tests passed
**Status**: ✅ Complete, tested with user feedback, operational
**Next**: Phase 10.6 - Timestamps Option

---

### ✅ Phase 10.1: Interactive Transcription - Phase 1 COMPLETE (2025-12-03)

**Achievement**: Foundation infrastructure for inline button-based transcription features

**What Was Implemented**:
1. **Database Models** - 3 new tables:
   - `transcription_states`: UI state tracking per message
   - `transcription_variants`: Cached text variations (mode, length, emoji, timestamps)
   - `transcription_segments`: faster-whisper segments for timestamp features

2. **Callback System**:
   - `src/bot/keyboards.py`: Callback data encoding, keyboard generation
   - `src/bot/callbacks.py`: Callback routing and handlers
   - Compact format: `action:usage_id:params` (64-byte limit validation)

3. **Segment Extraction**: Modified faster-whisper provider to return segments

4. **Feature Flags**: Master switch + phase-specific flags for gradual rollout

**User Experience**:
```
[Transcription text]

[Исходный текст (вы здесь)]  ← Inline button
```

**Critical Bugs Fixed**:
1. **allowed_updates=Update.ALL_TYPES** - CRITICAL FIX
   - Required for Telegram to send callback_query updates
   - Without this: buttons show "Загрузка..." indefinitely
   - Location: `src/main.py:219`

2. **draft_text UnboundLocalError** - Fixed variable scope issue when LLM disabled

**Status**: ✅ Tested, deployed, operational
**Next**: Phase 2 - Structured Mode (LLM-based text formatting with punctuation, paragraphs)

---

### ✅ Large File Support via Telethon (2025-11-30)

**Achievement**: Support files up to 2 GB (100x increase from 20 MB)

**Solution**: Hybrid download strategy
- ≤20 MB: Bot API (fast, existing)
- >20 MB: Telethon Client API (MTProto, up to 2 GB)

**Technical**:
- Telethon v1.42.0 (actively maintained)
- Session-based auth (persistent)
- Feature flag: `TELETHON_ENABLED`

---

### Other Recent Enhancements (Nov 2025)

**Hybrid Transcription** (Phase 8): 6-9x faster for long audio via draft+LLM
**DEBUG Logging** (Phase 8.1): Comprehensive logging for local development
**LLM Debug Mode** (Phase 8.2): Side-by-side draft vs refined comparison
**LLM Performance Tracking** (Phase 8.3): Database fields for LLM metrics
**Smart Audio Preprocessing** (Phase 8.4): 97% file size reduction (WAV→Opus)

*Details in progress.md and systemPatterns.md*

---

## Key Patterns & Decisions

### Interactive Transcription Patterns (Phase 10.1)

**1. Callback Data Encoding**
- Format: `action:usage_id:param=value`
- 64-byte Telegram limit with validation
- Example: `mode:125:mode=structured`

**2. allowed_updates Configuration**
- **CRITICAL**: Must include `Update.ALL_TYPES` in `start_polling()`
- Without this, callback_query updates not received
- Non-obvious requirement, caused significant debugging

**3. Send Message Before Keyboard**
- Message ID must exist before creating TranscriptionState
- Add keyboard via `edit_reply_markup()` after message sent
- Avoids race conditions

**4. Session Management for Callbacks**
- Create repositories with async session per callback invocation
- Wrapper pattern: `callback_query_wrapper()` in main.py

**5. Segment Storage Threshold**
- Only save segments for audio >300s (5 minutes)
- Optimizes database storage

**6. Feature Flag System**
- Master switch: `INTERACTIVE_MODE_ENABLED`
- Phase-specific flags: `ENABLE_STRUCTURED_MODE`, etc.
- Gradual rollout strategy

### Queue System Patterns (Phase 6-7, Oct 2025)

**1. Atomic Counter Pattern**
- Use dedicated `_total_pending` counter for positions
- DON'T use `qsize()` - unreliable with concurrent workers
- Increment before put(), decrement in finally block

**2. Unique File Naming**
- Add UUID suffix: `{file_id}_{uuid8}.extension`
- Prevents conflicts when multiple users forward same message

**3. Live Progress Feedback**
- Updates every 5s via message edits
- Visual progress bar + RTF-based time estimates
- Dramatically improves UX even when processing is slow

**4. Sequential Processing**
- `max_concurrent=1` prevents resource exhaustion
- Essential for 3GB RAM / 4 CPU VPS
- Acceptable UX through progress updates

### Deployment Patterns (Phase 7, Nov 2025)

**1. Fully Automatic Pipeline**
- PR merge → Build & Tag → Deploy (zero manual steps)
- Version calculation: `git describe --tags --abbrev=0`
- Separate build and deploy workflows

**2. Database Migrations**
- Automated testing in CI (fresh DB, upgrade/downgrade cycle)
- Production migration before deploy
- Automatic rollback on failure

**3. Centralized Logging**
- Size-based rotation (not time-based)
- Version in every log entry
- Persists across container rebuilds

---

## Next Steps

### Phase 10.8: Retranscription (FUTURE)

**Goal**: Allow users to retranscribe with different quality settings

**Two Approaches**:
1. **Method 1: Different Model** - Use higher quality model (large vs medium)
2. **Method 2: Different Provider** - Use OpenAI Whisper API for reference quality

**Plan**: See Phase 8 in implementation plan

---

## Important Context for Future Sessions

### Critical Configuration

**Environment Variables to Remember**:
```bash
# Interactive Mode
INTERACTIVE_MODE_ENABLED=true
ENABLE_STRUCTURED_MODE=false  # Phase 2+
ENABLE_SUMMARY_MODE=false     # Phase 4+

# Queue System
MAX_QUEUE_SIZE=10
MAX_CONCURRENT_WORKERS=1
MAX_VOICE_DURATION_SECONDS=120

# LLM (Optional)
LLM_REFINEMENT_ENABLED=false
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat

# Telethon (Optional)
TELETHON_ENABLED=false
TELEGRAM_API_ID=<from my.telegram.org>
TELEGRAM_API_HASH=<from my.telegram.org>
```

### Key Files to Know

**Interactive Transcription**:
- `src/bot/keyboards.py` - Keyboard generation
- `src/bot/callbacks.py` - Callback handlers
- `src/storage/models.py` - State, Variant, Segment models
- `src/main.py:219` - allowed_updates=Update.ALL_TYPES (CRITICAL)

**Queue System**:
- `src/services/queue_manager.py` - FIFO queue, atomic counter
- `src/services/progress_tracker.py` - Live progress updates

**LLM Integration**:
- `src/services/llm_service.py` - LLM provider abstraction
- `src/services/text_processor.py` - Will be created in Phase 2

### Common Pitfalls

1. **Forgetting allowed_updates**: Buttons won't work without `Update.ALL_TYPES`
2. **Variable scope**: Ensure variables defined before use (draft_text bug)
3. **Session management**: Create repositories with session per callback
4. **64-byte limit**: Validate callback_data length
5. **LLM graceful fallback**: Always handle LLM failures

---

## Documentation

**Full History**: See `memory-bank/progress.md`
**Patterns**: See `memory-bank/systemPatterns.md`
**Tech Stack**: See `memory-bank/techContext.md`
**Implementation Plan**: `memory-bank/plans/2025-12-02-interactive-transcription-processing.md`
**Phase 1 Acceptance**: `PHASE1_ACCEPTANCE.md`
