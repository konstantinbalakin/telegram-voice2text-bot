# Active Context: Telegram Voice2Text Bot

## Current Status (2025-12-19)

**Phase**: Phase 10 - Interactive Transcription Processing 🚀
**Stage**: Phase 10.14 COMPLETE ✅ (Magic Mode)
**Branch**: feature/magic-mode-button (PR #67 open)
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

### ✅ Phase 10.14: Magic Mode (2025-12-19)

**What**: New "🪄 Сделать красиво" button for publication-ready text transformation

**Key Implementation**:
- LLM prompt (`prompts/magic.md`) - preserves author's voice, warm conversational tone
- `TextProcessor.create_magic()` method - transforms transcription to Telegram-ready post
- Configuration: `ENABLE_MAGIC_MODE=true` (enabled by default)
- Keyboard: Row 4, after Structured, before Summary
- Callback handler with progress tracker and variant caching
- Fixed emoji_level=1, no length variations (simple UX)

**Bug Fix**:
- Mypy error: Changed from non-existent `update()` to cached variant pattern

**Status**: ✅ Complete, PR #67 open, CI/CD running
**Next**: Merge → Deploy → User feedback

---

### ✅ Phase 10.13: OpenAI Long Audio Chunking (2025-12-17)

**What**: Handle OpenAI gpt-4o audio >1400s through chunking or model switch

**Key Implementation**:
- Three strategies: (1) Auto model switch to whisper-1, (2) Parallel chunking, (3) Sequential chunking
- pydub for audio splitting with overlap
- Configuration: 7 new parameters (`OPENAI_GPT4O_MAX_DURATION`, etc.)
- Semaphore-based rate limiting for parallel processing

**Status**: ✅ Complete, merged, deployed

---

### ✅ Phase 10.12: StructureStrategy (2025-12-16)

**What**: Automatic structured transcription with duration-based workflows

**Key Implementation**:
- New routing strategy for auto-structuring
- Short audio (<20s): Direct structured result
- Long audio (≥20s): Draft → Structured
- Configurable emoji levels (0-3)
- Duration threshold: `STRUCTURE_DRAFT_THRESHOLD=20s`

**Status**: ✅ Complete, merged, deployed

---

## Active Patterns & Decisions

### Interactive Mode Architecture (Phase 10)

**Mode Types**:
1. **Simple modes** (original, summary, magic) - No length variations, single button
2. **Complex modes** (structured) - Length variations with dynamic keyboard
3. **Auto modes** (StructureStrategy) - Automatic processing based on duration

**Variant Caching Pattern**:
```python
# Always check existence first
existing = await repo.get_variant(usage_id, mode, length, emoji, timestamps)
if existing:
    variant = existing  # Use cached
else:
    variant = await repo.create(...)  # Generate new
```

**Emoji Level Management**:
- Original/Summary: emoji_level = 0 (no emojis)
- Structured/Magic: emoji_level = 1 (moderate emojis)
- User can adjust via emoji buttons (0-3 levels)

**File Handling**:
- Threshold: 3000 characters
- Short text: Telegram message with HTML formatting
- Long text: PDF file with professional styling
- State tracking: `is_file_message`, `file_message_id`

### LLM Integration

**Prompt-Driven Features**:
- Structured mode: `prompts/structured.md`
- Summary mode: `prompts/summary.md`
- Magic mode: `prompts/magic.md`
- Emoji variations: `prompts/emoji.md`
- Length adjustments: `prompts/length_*.md`

**Processing Flow**:
1. Load prompt template from file (with fallback)
2. Format with text/parameters
3. Call LLM via `_refine_with_custom_prompt()`
4. Apply `sanitize_html()` for Telegram compatibility
5. Graceful fallback to original text on errors

**Cost Optimization**:
- Variant caching prevents duplicate LLM calls
- DeepSeek V3: ~$0.0002 per 60s transcription
- Fallback strategies minimize failures

---

## Next Steps

### Immediate (Phase 10.14 Deployment)
1. ✅ Implementation complete
2. ✅ Commits created and pushed (3 commits)
3. ✅ Pull request created (PR #67)
4. ⏳ CI/CD checks running
5. ⏳ Merge to main (after checks pass)
6. ⏳ Deploy to production (automatic via CI/CD)
7. ⏳ Manual testing with real voice messages
8. ⏳ Gather user feedback on magic mode quality
9. ⏳ Monitor LLM costs and performance

### Future Considerations
- **User feedback**: Monitor magic mode adoption and quality
- **Prompt tuning**: A/B test different styles if needed
- **Cost monitoring**: Track LLM usage for magic mode
- **Phase 11+**: Analytics, quotas, billing, multi-language

---

## Important Context for Future Sessions

### Critical Configuration

**Interactive Mode** (All Features Enabled):
```bash
INTERACTIVE_MODE_ENABLED=true
ENABLE_STRUCTURED_MODE=true
ENABLE_MAGIC_MODE=true
ENABLE_SUMMARY_MODE=true
ENABLE_EMOJI_OPTION=true
ENABLE_LENGTH_VARIATIONS=true
ENABLE_TIMESTAMPS_OPTION=true
ENABLE_RETRANSCRIBE=true
FILE_THRESHOLD_CHARS=3000
```

**LLM Configuration** (Required for Interactive Features):
```bash
LLM_REFINEMENT_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_KEY=<from env>
```

**Routing Strategy**:
```bash
WHISPER_ROUTING_STRATEGY=structure  # Auto-structured transcription
STRUCTURE_PROVIDER=faster-whisper
STRUCTURE_MODEL=medium
STRUCTURE_DRAFT_THRESHOLD=20
STRUCTURE_EMOJI_LEVEL=1
```

### Key Files

**Interactive Transcription**:
- `src/bot/keyboards.py` - Keyboard generation (7 rows)
- `src/bot/callbacks.py` - Callback handlers (mode switching, emoji, length, timestamps, retranscribe)
- `src/services/text_processor.py` - LLM-powered text transformations
- `src/storage/models.py` - State, Variant, Segment models

**Prompts** (LLM-driven features):
- `prompts/structured.md` - Text structuring
- `prompts/magic.md` - Publication-ready transformation
- `prompts/summary.md` - Key points extraction
- `prompts/emoji.md` - Emoji enhancement (4 levels)
- `prompts/length_*.md` - Length adjustments

**Configuration**:
- `src/config.py` - All settings with validation
- `.env.example.short` - Brief configuration guide
- `.github/workflows/deploy.yml` - Production deployment config

### Common Pitfalls

1. **Forgetting allowed_updates**: Buttons won't work without `Update.ALL_TYPES` in `main.py:219`
2. **Repository pattern**: Always check variant existence before creating (prevents duplicates)
3. **LLM graceful fallback**: Always handle LLM failures, return original text
4. **HTML sanitization**: Apply `sanitize_html()` to all LLM outputs
5. **State management**: Create state first, then update fields via properties + flush
6. **Circular imports**: Move imports inside functions if circular dependency exists

### Active Issues & Monitoring

**Phase 10.14 (Magic Mode)**:
- PR #67 open, CI/CD checks running
- Awaiting: Merge → Deploy → User testing
- Watch: LLM quality, costs, user feedback

**Production Stability**:
- VPS: 3GB RAM, 4 CPU cores (stable)
- Queue: Sequential processing working well
- Database: SQLite migrations automated
- CI/CD: Fully automatic deployment

---

## Documentation

**Full History**: See `memory-bank/progress.md`
**Patterns**: See `memory-bank/systemPatterns.md`
**Tech Stack**: See `memory-bank/techContext.md`
**Plans**: See `memory-bank/plans/` for detailed phase implementations
