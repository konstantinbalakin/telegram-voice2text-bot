# Active Context: Telegram Voice2Text Bot

## Current Status (2025-12-03)

**Phase**: Phase 10 - Interactive Transcription Processing 🚀
**Stage**: Phase 10.1 COMPLETE ✅ → Ready for Phase 10.2 (Structured Mode)
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

### Phase 10.2: Structured Text Mode (NEXT)

**Goal**: LLM-based text formatting with punctuation and paragraphs

**Implementation Tasks**:
1. Create `src/services/text_processor.py`:
   - `create_structured(text)` method
   - LLM prompt for structuring
   - Graceful fallback on errors

2. Update `src/bot/keyboards.py`:
   - Add "📝 Структурировать" button
   - Update state indicator ("вы здесь")

3. Update `src/bot/callbacks.py`:
   - Implement structured mode handler
   - Generate variant on first request
   - Cache in database
   - Update message text + keyboard

4. Save original variant in `src/bot/handlers.py`:
   - After transcription, save as "original" mode

5. Feature flag: `ENABLE_STRUCTURED_MODE` (already exists)

**Expected User Experience**:
```
[Transcription text]

[Исходный текст]
[📝 Структурировать]  ← Click to format text

→ Message updates with formatted text:
- Proper punctuation
- Paragraph breaks
- Bullet lists (if appropriate)

[Исходный текст]
[📝 Структурировать (вы здесь)]  ← State indicator
```

**Acceptance Criteria**:
- ✅ Button appears when `ENABLE_STRUCTURED_MODE=true`
- ✅ Click generates structured text via LLM
- ✅ Variant cached in database (no regeneration on re-click)
- ✅ Message updates with new text + keyboard state
- ✅ Works with/without LLM enabled
- ✅ All tests passing

**Plan**: See `memory-bank/plans/2025-12-02-interactive-transcription-processing.md` Phase 2

### Future Phases (Phase 10.3-10.8)

**Phase 3**: Length variations (5 levels: shorter ← short ← default → long → longer)
**Phase 4**: Summary mode ("О чем текст?")
**Phase 5**: Emoji option (0, 1-2, 3-5 levels)
**Phase 6**: Timestamps (for audio >5 min)
**Phase 7**: File handling (for text >4096 chars)
**Phase 8**: Retranscription (two quality methods)

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
