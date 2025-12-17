# Active Context: Telegram Voice2Text Bot

## Current Status (2025-12-17)

**Phase**: Phase 10 - Interactive Transcription Processing 🚀
**Stage**: Phase 10.13 COMPLETE ✅ (OpenAI Long Audio Chunking)
**Branch**: feature/openai-long-audio-chunking (merged)
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

### ✅ Phase 10.13: OpenAI Long Audio Chunking COMPLETE (2025-12-17)

**Achievement**: Implemented audio chunking support for OpenAI gpt-4o models to handle audio files exceeding duration limits

**Problem Solved**:
OpenAI's gpt-4o models (gpt-4o-transcribe, gpt-4o-mini-transcribe) have duration limits of approximately 1400-1500 seconds (~23-25 minutes). Voice messages exceeding this limit fail with "duration_too_large" error. Need a solution to enable transcription of unlimited duration audio while maintaining quality.

**Implementation Complete**: ✅

**What Was Implemented**:

1. **OpenAI Provider Long Audio Handling** (`src/transcription/providers/openai_provider.py`):
   - Duration check: If audio > OPENAI_GPT4O_MAX_DURATION (1400s), route to `_handle_long_audio()`
   - Three strategies for handling long audio:
     - **Strategy 1** (default): Automatic model switch to whisper-1 (no duration limit)
     - **Strategy 2**: Audio chunking with parallel processing (2-3x faster, no context)
     - **Strategy 3**: Audio chunking with sequential processing (slower, context preservation)
   - 8 new methods implemented:
     - `_handle_long_audio()` - Main router for strategy selection
     - `_split_audio_into_chunks()` - Uses pydub to split audio with overlap
     - `_transcribe_chunks_parallel()` - Parallel processing with semaphore for rate limiting
     - `_transcribe_chunks_sequential()` - Sequential with context passing via prompt parameter
     - `_transcribe_single_file()` - Helper for chunk transcription
     - `_transcribe_single()` - Helper for model switching
     - `_cleanup_chunks()` - Cleanup temporary files
     - `_get_chunk_prompt()` - Extract last 224 tokens for context

2. **Configuration Parameters** (`src/config.py`):
   - Added 7 new parameters for OpenAI long audio handling:
     - `openai_gpt4o_max_duration: int = 1400` - Duration threshold
     - `openai_change_model: bool = True` - Enable auto model switch (default strategy)
     - `openai_chunking: bool = False` - Enable audio chunking
     - `openai_chunk_size_seconds: int = 1200` - Chunk size (300-1400s validation)
     - `openai_chunk_overlap_seconds: int = 2` - Overlap between chunks (0-10s validation)
     - `openai_parallel_chunks: bool = True` - Parallel vs sequential processing
     - `openai_max_parallel_chunks: int = 3` - Max concurrent chunk requests (1-10 validation)

3. **Dependency Addition**:
   - Added `pydub = "^0.25.1"` to pyproject.toml
   - Verified via Context7: Production/Stable, High reputation, MIT license
   - Used for audio splitting and manipulation

4. **Configuration Examples** (`.env.example`, `.env.example.short`):
   - Added comprehensive OpenAI Long Audio Handling section
   - Documented all 7 new environment variables with descriptions
   - Provided 4 usage scenarios:
     - Fast handling: Auto model switch (default)
     - Maximum quality parallel: Chunking with parallel processing
     - Maximum quality sequential: Chunking with context preservation
     - Balanced: Custom configuration

**Key Features**:

1. **Chunk Splitting with Overlap**:
   - Uses pydub AudioSegment for reliable audio manipulation
   - Default chunk size: 1200s (20 minutes)
   - Default overlap: 2 seconds (prevents word cutting)
   - Configurable chunk size (300-1400s) and overlap (0-10s)

2. **Parallel Processing**:
   - Processes multiple chunks simultaneously via asyncio.gather
   - Semaphore limits concurrent API calls (max 3) to avoid rate limiting
   - 2-3x faster than sequential processing
   - Good for independent audio segments

3. **Sequential Processing**:
   - Processes chunks one by one with context preservation
   - Uses prompt parameter with last 224 tokens from previous chunk
   - Maintains continuity for continuous speech
   - Slower but higher quality for context-dependent content

4. **Cleanup**:
   - Temporary chunk files deleted in finally block
   - Prevents disk space accumulation
   - Robust error handling

**Type Checking Fixes**:
- Added runtime checks for `self._client` in `_transcribe_single_file()` and `_transcribe_single()`
- Added `# type: ignore[import-untyped]` for pydub import (no type stubs available)
- All mypy checks passing ✅

**Testing & Quality**:
- ✅ All 204 tests passing
- ✅ Black formatting verified
- ✅ Ruff linting clean
- ✅ Mypy type checking passing
- ✅ pydub dependency verified via Context7

**Strategy Selection Logic**:
```python
if OPENAI_CHANGE_MODEL:
    # Strategy 1: Switch to whisper-1 (default)
    return await self._transcribe_single(audio_path, context, model="whisper-1")
elif OPENAI_CHUNKING:
    # Strategy 2 or 3: Chunk audio
    if OPENAI_PARALLEL_CHUNKS:
        # Strategy 2: Parallel (fast)
        return await self._transcribe_chunks_parallel(chunks, context)
    else:
        # Strategy 3: Sequential (context)
        return await self._transcribe_chunks_sequential(chunks, context)
else:
    # No strategy: Return error
    raise ValueError("Audio exceeds duration limit and no handling strategy enabled")
```

**Files Modified**:
- `src/config.py` (+7 configuration parameters)
- `src/transcription/providers/openai_provider.py` (+8 methods, 500+ lines)
- `pyproject.toml` (+pydub dependency)
- `.env.example` (+comprehensive documentation)
- `.env.example.short` (+brief configuration example)

**Key Patterns Established**:

1. **Three-Strategy Approach**: Provide multiple options for different use cases
   - Model switch: Fast, simple, no extra API calls
   - Parallel chunking: Maximum speed for independent segments
   - Sequential chunking: Maximum quality with context preservation

2. **Semaphore-Based Rate Limiting**: Prevent API rate limits during parallel processing
   - Pattern: `asyncio.Semaphore(max_parallel_chunks)` wraps each API call
   - Ensures controlled concurrency

3. **Overlap for Context**: Small overlap between chunks prevents word cutting
   - Critical for seamless transcription
   - Configurable (0-10s) based on audio characteristics

4. **Cleanup in Finally Block**: Always clean up temporary files
   - Prevents disk space leaks
   - Robust even if errors occur during processing

**Next Steps**: Ready for production deployment when needed

---

### ✅ Phase 10.12: StructureStrategy - Auto-Structured Transcription COMPLETE (2025-12-16)

**Achievement**: New routing strategy for automatic text structuring with duration-based workflows and configurable emoji levels

**Problem Solved**:
Users wanted automatic text structuring without manual button clicks. The hybrid strategy worked well, but required manual selection of structured mode after transcription. Need a new strategy that automatically structures text while preserving draft preview for longer audio.

**Implementation Complete**: ✅

**What Was Implemented**:

1. **StructureStrategy Class** (`src/transcription/routing/strategies.py`):
   - New routing strategy: Automatic structured transcription
   - Dual workflow based on duration:
     - Short audio (<20s): Transcription → Direct structured result
     - Long audio (≥20s): Transcription → Draft preview → Structured result
   - Methods implemented:
     - `select_provider()` - Choose transcription provider (faster-whisper or openai)
     - `get_model_name()` - Select appropriate model
     - `requires_structuring(duration_seconds)` - Duration-based logic
     - `should_show_draft(duration_seconds)` - Show draft only for ≥20s
     - `get_emoji_level()` - Configurable emoji levels (0-3)
   - Configuration parameters:
     - `structure_provider` - Provider choice (faster-whisper, openai)
     - `structure_model` - Model selection (medium, gpt-4o-transcribe, etc.)
     - `structure_draft_threshold` - Duration threshold for draft preview (default: 20s)
     - `structure_emoji_level` - Emoji density (0=none, 1=few, 2=moderate, 3=many)

2. **Configuration Updates** (`src/config.py`):
   - Added 4 new parameters with validation:
     - `structure_provider: str = "faster-whisper"`
     - `structure_model: str = "medium"`
     - `structure_draft_threshold: int = 20` (0-3600 validation)
     - `structure_emoji_level: int = 1` (0-3 validation)
   - Environment variable examples documented

3. **Factory Integration** (`src/transcription/factory.py`):
   - Added StructureStrategy creation in factory
   - Validation: Requires `LLM_REFINEMENT_ENABLED=true`
   - Automatic provider creation if not already initialized
   - Comprehensive logging for initialization steps

4. **Handler Processing** (`src/bot/handlers.py`):
   - Full workflow implementation:
     - Short audio: Transcription → Structure → Save structured variant
     - Long audio: Transcription → Save original variant → Show draft → Structure → Save structured variant → Update message
   - Intelligent variant management:
     - Checks for existing variants before creation (prevents duplicates)
     - Creates structured variant with active_mode="structured"
   - State management:
     - Updates state after creation (not during, due to repository limitations)
     - Sets active_mode and emoji_level correctly
   - Fallback on errors: Returns original text if structuring fails

5. **TextProcessor Enhancement** (`src/services/text_processor.py`):
   - `create_structured()` now accepts `emoji_level` parameter
   - Dynamic prompt modification based on emoji level:
     - Level 0: Removes emoji instruction entirely
     - Level 1: "минимальное количество эмодзи"
     - Level 2: "умеренное количество эмодзи" (default)
     - Level 3: "щедрое количество эмодзи"
   - Graceful fallback if LLM refinement fails

6. **Configuration Examples** (`.env.example`, `.env.example.short`):
   - Added StructureStrategy to list of available strategies
   - Documented all 4 new environment variables
   - Provided usage examples with descriptions
   - Updated strategy list: single, fallback, benchmark, hybrid, structure

7. **Comprehensive Testing** (`tests/unit/test_structure_strategy.py`):
   - 24 unit tests covering all functionality:
     - Initialization with different configurations
     - Provider selection logic
     - Model name retrieval
     - Structuring requirements (duration-based)
     - Draft preview logic (duration-based)
     - Emoji level handling (4 levels)
     - Edge cases (zero duration, very long audio)
   - All 24 tests passing ✅

**Bug Fixes During Implementation**:

1. **Repository Method Names**:
   - Fixed: `save_variant()` → `create()` for TranscriptionVariantRepository
   - Updated both original and structured variant saving

2. **State Creation Parameters**:
   - Fixed: `active_mode` and `emoji_level` not accepted by `create()`
   - Solution: Create state first, then update fields via state properties
   - Pattern: `state.active_mode = value; await session.flush()`

3. **Variant Duplication Prevention**:
   - Problem: `_create_interactive_state_and_keyboard()` always created original variant
   - Solution: Check existence first via `get_variant()` before creating
   - Impact: Prevents UNIQUE constraint violations

4. **Duration-Based Structuring Logic**:
   - Problem: `requires_structuring()` always returned True
   - Solution: Added `duration_seconds` parameter and threshold check
   - Behavior: Short audio (<20s) bypasses structuring, long audio (≥20s) structures

**Testing & Quality**:
- ✅ All 24 unit tests passing (was 21, added 3 more during fixes)
- ✅ Black formatting verified
- ✅ Ruff linting clean
- ✅ Manual testing completed with both short and long audio
- ✅ Structured text generation working
- ✅ Interactive buttons appearing correctly
- ✅ Emoji levels functioning as expected

**User Experience**:

Short audio (<20 seconds):
```
User sends 10s voice message
  ↓
Transcription → Structured text → Result displayed
(No draft, direct to final)
```

Long audio (≥20 seconds):
```
User sends 60s voice message
  ↓
Transcription → Draft preview
  ↓
"✨ Улучшаю текст..."
  ↓
Structured text → Result displayed with buttons
```

**Files Created**:
- `tests/unit/test_structure_strategy.py` (NEW, 24 tests)

**Files Modified**:
- `src/transcription/routing/strategies.py` (+StructureStrategy class)
- `src/config.py` (+4 configuration parameters)
- `src/transcription/factory.py` (+StructureStrategy creation)
- `src/bot/handlers.py` (+workflow implementation)
- `src/services/text_processor.py` (+emoji_level support)
- `.env.example` (+StructureStrategy documentation)
- `.env.example.short` (+brief configuration example)

**Key Patterns Established**:

1. **Duration-Based Workflow**: Use duration threshold to determine whether to show intermediate results
   - Short audio: Direct to final result (fast UX)
   - Long audio: Show draft then refine (progressive disclosure)

2. **Configurable Emoji Levels**: LLM-based feature with user control (0-3 scale)
   - Builds on Phase 10.5 relative emoji instruction pattern
   - Enables personalization without code changes

3. **Variant Existence Checking**: Always check before creating to prevent duplicates
   - Critical for workflows that may create variants at multiple stages
   - Pattern: `get_variant() → if not exists → create()`

4. **State Update After Creation**: Repository limitations require two-step process
   - First: Create base state
   - Second: Update additional fields via model properties
   - Always flush after property updates

**Configuration**:
```bash
# Enable StructureStrategy
WHISPER_ROUTING_STRATEGY=structure
LLM_REFINEMENT_ENABLED=true  # Required!

# Strategy configuration
STRUCTURE_PROVIDER=faster-whisper
STRUCTURE_MODEL=medium
STRUCTURE_DRAFT_THRESHOLD=20  # seconds
STRUCTURE_EMOJI_LEVEL=1  # 0=none, 1=few, 2=moderate, 3=many
```

**Impact**:
- ✅ Automatic structured transcription without manual buttons
- ✅ Smart draft preview for longer audio
- ✅ Configurable emoji levels for personalization
- ✅ Maintains all interactive mode features (buttons work)
- ✅ Fallback to original text on any errors

**Status**: ✅ COMPLETE - Tested, documented, ready for deployment
**Completion Date**: 2025-12-16
**Next**: Commit changes, create PR, merge, deploy to production
**Branch**: feature/structure-strategy

---

### ✅ Phase 10.10: HTML Formatting & PDF Generation COMPLETE (2025-12-09)

**Achievement**: Professional text formatting in Telegram with HTML rendering and PDF file generation for large transcriptions

**Problem Identified**:
LLM returns text with Markdown formatting (`**текст**`), but Telegram displays it literally without rendering. Users see raw Markdown syntax instead of formatted text (bold, italic, lists). For large transcriptions (>3000 chars), `.txt` files are generated without formatting preservation.

**Implementation Complete**: ✅

**What Was Implemented**:

1. **HTML Parse Mode** (`src/bot/callbacks.py`, `src/bot/handlers.py`):
   - Added `parse_mode="HTML"` to ALL message sending methods (11 locations)
   - Text messages now render HTML formatting properly
   - Captions support HTML formatting
   - Benchmark reports switched from Markdown to HTML

2. **PDF Generator Service** (`src/services/pdf_generator.py`, NEW FILE, 132 lines):
   - `PDFGenerator` class using WeasyPrint for HTML-to-PDF conversion
   - `generate_pdf(html_content)` - Converts HTML string to PDF bytes
   - `create_styled_html(content)` - Wraps content in styled HTML template
   - `generate_pdf_from_text(text)` - Plain text to PDF with paragraph wrapping
   - Professional styling: Arial, 12pt, proper line height, margins, code blocks
   - FontConfiguration for Cyrillic support
   - Graceful error handling with detailed logging

3. **LLM Prompt Updates** (4 prompt files):
   - `prompts/structured.md` - Now instructs HTML tags (<b>, <i>, <ul>, <li>, <code>)
   - `prompts/summary.md` - HTML formatting for headers and lists
   - `prompts/length_shorter.md` - Preserve HTML tags when shortening
   - `prompts/length_longer.md` - Preserve HTML tags when expanding

4. **PDF Integration** (`src/bot/callbacks.py`, `src/bot/handlers.py`):
   - Files >3000 chars now generated as PDF instead of TXT
   - Fallback to TXT if PDF generation fails
   - PDF filenames: `transcription_{usage_id}_{mode}.pdf` or `draft_{usage_id}.pdf`
   - Captions show file format: "📄 {mode} ({length} символов, PDF)"
   - Applies to: initial results, drafts, interactive variants, retranscription

5. **Dependency Management**:
   - Added `weasyprint ^62.3` to pyproject.toml
   - Added `pydyf ^0.11.0` (compatibility fix for transform method)
   - Updated Dockerfile with system dependencies:
     - libcairo2, libpango-1.0-0, libpangocairo-1.0-0
     - libgdk-pixbuf2.0-0, libffi-dev, shared-mime-info
   - Docker image increase: ~100MB (expected, necessary for PDF rendering)

6. **Testing** (`tests/unit/test_pdf_generator.py`, NEW FILE, 183 lines):
   - 13 comprehensive unit tests covering all functionality
   - Tests: HTML conversion, Cyrillic text, formatting tags, code blocks
   - Tests: Special characters, links, nested structures, large texts
   - All 13 tests passing ✅

**User Experience**:
```
User receives transcription:
  ↓
Short text (<3000 chars):
Telegram message with HTML formatting:
<b>Важный момент</b> в начале
<ul><li>Первый пункт</li><li>Второй пункт</li></ul>
Текст с <i>курсивом</i> и <code>кодом</code>
  ↓
Long text (>3000 chars):
PDF file with professional formatting:
📄 transcription_123_structured.pdf
Caption: "📄 Структурированный (4567 символов, PDF)"
```

**Files Created**:
- `src/services/pdf_generator.py` (132 lines)
- `tests/unit/test_pdf_generator.py` (183 lines)
- `memory-bank/plans/2025-12-09-html-formatting-pdf-plan.md` (228 lines)

**Files Modified**:
- `src/bot/callbacks.py` (+90 lines) - HTML parse_mode + PDF generation
- `src/bot/handlers.py` (+60 lines) - HTML parse_mode + PDF generation
- `prompts/structured.md` (+8 lines) - HTML formatting instructions
- `prompts/summary.md` (+4 lines) - HTML list formatting
- `prompts/length_shorter.md` (+1 line) - Preserve HTML tags
- `prompts/length_longer.md` (+1 line) - Preserve HTML tags
- `Dockerfile` (+6 lines) - System dependencies for WeasyPrint
- `pyproject.toml` (+2 lines) - weasyprint, pydyf dependencies
- `poetry.lock` (updated)

**Key Patterns Established**:
1. **Consistent Parse Mode**: Use `parse_mode="HTML"` consistently across ALL message sending
2. **Graceful PDF Fallback**: Try PDF first, fallback to TXT on error (never fail silently)
3. **Template-Based HTML Generation**: Styled HTML wrapper for consistent PDF appearance
4. **FontConfiguration Pattern**: Use WeasyPrint's FontConfiguration for Unicode/Cyrillic
5. **In-Memory PDF Generation**: Use io.BytesIO for Telegram file API (no temp files)
6. **Comprehensive Testing**: Test all HTML features (tags, Cyrillic, special chars, large texts)

**Edge Cases Handled**:
- Empty content (generates valid PDF)
- Special characters properly escaped
- Large texts (10KB+) handled efficiently
- PDF generation failure doesn't crash bot (TXT fallback)
- Cyrillic text renders correctly in PDFs
- HTML tags work in all Telegram contexts (messages, captions, files)

**Testing Status**:
- ✅ All 13 PDF generator unit tests passing
- ✅ Type checking (mypy) passing
- ✅ Linting (ruff) passing
- ✅ Formatting (black) passing
- ✅ WeasyPrint compatibility verified (pydyf 0.11.0)
- ⏳ Manual testing required:
  - Send short voice message → Check HTML formatting in Telegram
  - Send long voice message → Check PDF file generation
  - Test all interactive modes (structured, summary, emoji, etc.)
  - Test retranscription with PDF generation
  - Verify Cyrillic rendering in PDFs

**Impact**:
- ✅ Professional text formatting without raw Markdown syntax
- ✅ Large transcriptions preserve formatting via PDF
- ✅ Improved readability with bold, italic, lists, code blocks
- ✅ All Telegram-supported HTML tags now work properly
- ✅ Graceful fallback ensures reliability
- ✅ ~100MB Docker image increase acceptable for quality improvement

**Implementation Plan**: Documented in `memory-bank/plans/2025-12-09-html-formatting-pdf-plan.md`

**Status**: ✅ COMPLETE - Code implemented, tests passing, ready for manual testing
**Completion Date**: 2025-12-09
**Next**: Manual testing with real bot, merge to main, deploy to production
**Branch**: feature/html-formatting-pdf
**Commit**: 5772da3

---

### ✅ Phase 10.11: Provider-Aware Audio Format Conversion COMPLETE (2025-12-15)

**Achievement**: Enable support for OpenAI's new gpt-4o-transcribe and gpt-4o-mini-transcribe models through intelligent provider-aware audio format conversion

**Problem Solved**:
OpenAI's new transcription models don't support `.oga` format (Telegram's default), causing `"Unsupported file format oga"` errors. The bot needs to convert audio to MP3/WAV for gpt-4o models while keeping OGA for whisper-1 and faster-whisper (optimal).

**Implementation Complete**: ✅

**What Was Implemented**:

1. **Configuration** (`src/config.py`):
   - Added `openai_4o_transcribe_preferred_format` (renamed for clarity)
   - Added `OPENAI_FORMAT_REQUIREMENTS` mapping models to supported formats

2. **Provider Interface** (`src/transcription/providers/base.py`):
   - Added `provider_name` abstract property
   - Added `get_preferred_format()` method

3. **Provider Implementations**:
   - OpenAI: Returns MP3/WAV for gpt-4o models, None for whisper-1
   - FasterWhisper: Returns None (accepts all formats)

4. **Audio Handler** (`src/transcription/audio_handler.py`):
   - Updated `preprocess_audio()` with `target_provider` parameter
   - Added `_optimize_for_provider()` - smart format selection
   - Added `_convert_to_mp3()` - 16kHz mono, 64kbps, speech-optimized
   - Added `_convert_to_wav()` - 16kHz mono, PCM 16-bit, lossless

5. **Integration** (`src/bot/handlers.py`):
   - Detects active provider before preprocessing
   - Passes provider name to audio handler
   - Completely transparent to users

**Smart Logic**:
- OpenAI + gpt-4o-*: OGA → MP3/WAV
- OpenAI + whisper-1: Keep OGA
- FasterWhisper: Keep OGA (optimal)
- Unknown provider: No optimization

**Key Features**:
- ✅ Enables OpenAI's latest models (gpt-4o-transcribe, gpt-4o-mini-transcribe)
- ✅ Each provider gets optimal format
- ✅ Only converts when necessary
- ✅ Backward compatible
- ✅ Configurable (MP3 or WAV)
- ✅ Robust error handling

**Files Modified**: 7 code files + 3 config files

**Testing**:
- ✅ All 172 tests passing
- ✅ Type checking (mypy) clean
- ✅ Configuration loads correctly

**Impact**:
- ✅ Unlocks OpenAI's most advanced transcription models
- ✅ Future-proof for new providers/models
- ✅ Zero user-facing changes
- ✅ Maintains optimal performance per provider

**Status**: ✅ COMPLETE
**Completion Date**: 2025-12-15
**Next**: Commit changes, create PR, merge, deploy
**Branch**: feature/provider-aware-audio-format

---

### ✅ Phase 10.9: Retranscription Progress Bar & Parent-Child Usage Tracking COMPLETE (2025-12-09)

**Achievement**: Enhanced retranscription UX with progress feedback and preserved statistics through parent-child relationship tracking

**Problem Identified**:
After implementing interactive mode buttons (Phase 10.8), retranscription logic had critical UX and data integrity issues:
1. **No Progress Bar**: Users waited without feedback during retranscription (could take 30-90s)
   - Free method uses better model (RTF 0.5)
   - Paid method uses OpenAI (~30s fixed)
2. **Lost Statistics**: Usage record was overwritten, losing original transcription data
   - No retranscription history tracking
   - Analytics limited (no parent-child relationship)
3. **Unnecessary Refinement**: Retranscription ran LLM refinement despite already using good model

**Implementation Complete**: ✅

**What Was Implemented**:

1. **Database Migration** (`alembic/versions/f0514e20f750_add_parent_usage_id_to_usage_table.py`):
   - Added `parent_usage_id` column to `usage` table (nullable, indexed)
   - Foreign key constraint with CASCADE delete
   - SQLite batch mode for safe migration
   - Migration applied successfully: verified in production database

2. **Usage Model Update** (`src/storage/models.py:97-99`):
   - Added `parent_usage_id` field to Usage model
   - Enables parent-child relationship tracking for retranscriptions
   - Supports retranscription chains (original → child1 → child2)

3. **Repository Enhancement** (`src/storage/repositories.py:124-158`):
   - Updated `UsageRepository.create()` to accept `parent_usage_id` and `original_file_path` parameters
   - Enables creation of child usage records linked to parent

4. **TranscriptionContext Extension** (`src/transcription/models.py:28`):
   - Added `disable_refinement` flag to TranscriptionContext
   - Allows skipping LLM refinement for retranscription (saves time)

5. **Progress Bar Implementation** (`src/bot/retranscribe_handlers.py`):
   - **Free retranscription**: Duration = `voice_duration * RETRANSCRIBE_FREE_MODEL_RTF` (RTF 0.5)
   - **Paid retranscription**: Duration = `LLM_PROCESSING_DURATION` (fixed 30 seconds)
   - ProgressTracker starts before transcription, stops on completion or error
   - Visual feedback: `🔄 [████████░░░░] 40% (~45с осталось)`

6. **Parent-Child Usage Record Creation** (`src/bot/retranscribe_handlers.py:221-260`):
   - Creates NEW child usage record instead of overwriting
   - Links to original via `parent_usage_id`
   - Preserves original statistics (model, time, length)
   - Updates `state.usage_id` to point to child usage for continued interaction
   - All subsequent operations (variants, segments, mode changes) link to child usage

7. **Refinement Control** (`src/bot/handlers.py:1268-1271`):
   - Handler respects `disable_refinement` flag from context
   - Skips LLM refinement when `disable_refinement=True`
   - Logged for debugging: "LLM refinement disabled by context"

**User Experience**:
```
User clicks [⚡ Могу лучше] button
  ↓
Menu appears:
[🆓 Бесплатно (лучше, ~1м 30с)]
[💰 Платно (~2.0₽) - OpenAI]
[◀️ Назад]
  ↓
User selects free method
  ↓
Progress bar appears:
🔄 Ретранскрибирую...
[████████░░░░] 40% (~54с осталось)
  ↓
Retranscription completes
✨ Готово!
[New transcription with improved quality]
  ↓
Database:
- Original usage record preserved (id=123, model=small/beam1, time=10s)
- Child usage record created (id=456, parent_usage_id=123, model=medium/int8, time=45s)
- State updated to child (state.usage_id=456)
```

**Files Modified**:
- `alembic/versions/f0514e20f750_add_parent_usage_id_to_usage_table.py` (NEW, 54 lines)
- `src/storage/models.py` (+3 lines) - parent_usage_id field
- `src/storage/repositories.py` (+2 params, +2 fields in create())
- `src/transcription/models.py` (+1 line) - disable_refinement flag
- `src/bot/retranscribe_handlers.py` (+60 lines) - progress bar + parent-child logic
- `src/bot/handlers.py` (+4 lines) - refinement control

**Files Created**:
- `memory-bank/plans/2025-12-08-retranscription-improvements-plan.md` (detailed implementation plan)

**Key Patterns Established**:
1. **Progress Bar with Dynamic Duration**: Use RTF for free method, fixed duration for paid method
2. **Parent-Child Usage Tracking**: Preserve history through database relationships instead of overwriting
3. **State Migration on Retranscription**: Update state.usage_id to child for seamless continuation
4. **Refinement Control via Context**: Pass flags through TranscriptionContext for behavior modification
5. **Cascading Deletes**: Parent deletion removes children (prevents orphaned records)

**Edge Cases Handled**:
- Multiple retranscriptions: Creates chain (original → child1 → child2)
- State management: state.usage_id updated to latest child
- Progress bar errors: Stopped on exception, no hanging progress
- Orphaned children: CASCADE delete on foreign key

**Testing Status**:
- ✅ Database migration applied successfully (f0514e20f750)
- ✅ parent_usage_id column verified in production database
- ✅ Code changes complete and ready for testing
- ⏳ Manual testing required:
  - Free retranscription with progress bar (RTF 0.5)
  - Paid retranscription with progress bar (30s fixed)
  - Parent-child relationship in database
  - State.usage_id update verification
  - Interactive modes after retranscription (mode switch, length, emoji, timestamps)
  - Multiple retranscriptions (chain creation)

**Impact**:
- ✅ Users now see progress during retranscription (major UX improvement)
- ✅ Original statistics preserved for analytics
- ✅ Retranscription history tracked via parent_usage_id
- ✅ Faster processing (no unnecessary refinement)
- ✅ Enables future features (retranscription history UI, cost tracking, usage patterns)

**Implementation Plan**: Documented in `memory-bank/plans/2025-12-08-retranscription-improvements-plan.md`

**Status**: ✅ COMPLETE - Code implemented, migration applied, ready for testing
**Completion Date**: 2025-12-09
**Next**: Manual testing with real bot, verify all scenarios work correctly

---

### 🔄 Phase 10.8: Interactive Transcription - Phase 8 (Retranscription) COMPLETE (2025-12-08)

**Achievement**: Allow users to retranscribe audio with improved quality settings

**Implementation Status**: ✅ Complete, ⏳ Testing in progress

**What Was Implemented**:

1. **Database Schema** (`src/storage/models.py`):
   - Added `original_file_path` field to Usage model for storing audio files
   - Migration: `4a34681766dc_add_original_file_path_to_usage.py`

2. **Audio File Persistence** (`src/bot/handlers.py:107-141`):
   - `save_audio_file_for_retranscription()` - Saves files to `./data/audio_files/`
   - Naming: `{usage_id}_{file_id}{extension}`
   - Only saves when `ENABLE_RETRANSCRIBE=true`

3. **Retranscription Handlers** (`src/bot/retranscribe_handlers.py` NEW, 257 lines):
   - `handle_retranscribe_menu()` - Shows two options:
     - Free: "🆓 Бесплатно (лучше, ~Xм Yс)" with wait time (RTF 0.5)
     - Paid: "💰 Платно (~X.X₽) - OpenAI" with cost calculation
   - `handle_retranscribe()` - Complete retranscription flow:
     - Validates file existence
     - Deletes old variants/segments
     - Resets state
     - Calls TranscriptionRouter with new settings
     - Updates message with new result

4. **Architecture Integration**:
   - Added `bot_handlers` parameter to CallbackHandlers
   - Pass TranscriptionRouter through callback chain
   - Used TYPE_CHECKING to avoid circular imports

5. **Repository Methods** (`src/storage/repositories.py`):
   - Extended UsageRepository.update() with original_file_path
   - Added cleanup_old_audio_files() for TTL-based deletion
   - Added delete_by_usage_id() for variants and segments

6. **Configuration** (`src/config.py:206-222`):
   - persistent_audio_dir, persistent_audio_ttl_days
   - retranscribe_free_model, retranscribe_paid_provider
   - retranscribe_paid_cost_per_minute, enable_retranscribe

**User Experience**:
```
[Transcription with keyboard buttons]
[⚡ Могу лучше]  ← New button (Row 6)
  ↓
Menu:
[🆓 Бесплатно (лучше, ~1м 30с)]
[💰 Платно (~2.0₽) - OpenAI]
[◀️ Назад]
  ↓
Retranscription with improved quality
All state reset, keyboard restored
```

**Bug Fixes**:
- Import error: Fixed `from src.transcription.context` → `from src.transcription.models`
  - TranscriptionContext is in models.py, not context.py

**Files Created**:
- `src/bot/retranscribe_handlers.py` (257 lines)
- `alembic/versions/4a34681766dc_add_original_file_path_to_usage.py`

**Files Modified**:
- `src/storage/models.py`, `src/bot/handlers.py`, `src/config.py`
- `src/bot/keyboards.py`, `src/bot/callbacks.py`, `src/main.py`
- `src/storage/repositories.py`

**Testing**:
- ✅ All 136 unit tests passing
- ✅ Type checking, linting, formatting - all pass
- ⏳ Manual testing in progress by user

**Key Patterns**:
1. Audio file persistence only when feature enabled
2. TTL-based cleanup for storage management
3. Full state reset on retranscription for clean start
4. TranscriptionRouter reuse for consistency
5. Transparent wait time and cost estimates

**Current Status**:
- Implementation: ✅ COMPLETE
- Testing: ⏳ IN PROGRESS
- User feedback: Awaiting test results

**Next**: Complete testing, merge, deploy to production

---

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

---

### ✅ Phase 10.7.1: File Handling Bug Fixes & Extensions COMPLETE (2025-12-08)

**Achievement**: Extended file handling to initial results, drafts, and retranscription - fixed critical bugs preventing feature from working

**Root Problem**: Phase 10.7 only implemented file handling for interactive variants (`_send_variant_message()`), but initial transcription results still split into multiple parts despite `FILE_THRESHOLD_CHARS=3000` configuration.

**Bug Fixes Implemented**:

1. **Initial Transcription File Handling** (`src/bot/handlers.py`):
   - Created `_send_transcription_result()` method (~50 lines)
   - Two-message pattern: info message with keyboard + file message
   - Threshold: 3000 characters (configurable via `FILE_THRESHOLD_CHARS`)
   - Integrated into both LLM refined and direct result paths

2. **Draft Message File Handling** (`src/bot/handlers.py`):
   - Updated `_send_draft_messages()` to send files for long drafts
   - Removed old `split_text()` logic
   - Draft files: `draft_{usage_id}.txt`

3. **Retranscription Display Update** (`src/bot/callbacks.py`):
   - Created `update_transcription_display()` method (~130 lines)
   - Handles 4 transition scenarios:
     - Text → Text (simple edit)
     - File → File (delete old, send new)
     - Text → File (convert to file)
     - File → Text (delete file, edit message)
   - Integrated into `src/bot/retranscribe_handlers.py`

4. **Circular Import Fix** (`src/bot/retranscribe_handlers.py`):
   - Moved `from src.bot.callbacks import CallbackHandlers` inside function
   - Prevents circular dependency during module initialization
   - Critical fix: bot wouldn't start without this

5. **State Tracking** (`src/storage/models.py` + handlers):
   - Added `is_file_message` and `file_message_id` to TranscriptionState
   - Tracks whether current display is text or file
   - Enables seamless transitions between formats

**User Experience**:
```
Long audio (4500 chars result)
  ↓
Bot sends file: transcription_123.txt
+ keyboard in info message
  ↓
User clicks "📝 Структурировать" (6000 chars)
  ↓
Bot deletes old file, sends new file
  ↓
User clicks "Retranscribe" (2500 chars)
  ↓
Bot deletes file, updates to text message
```

**Files Modified**:
- `src/bot/handlers.py` (+100 lines) - File handling for initial/draft
- `src/bot/callbacks.py` (+150 lines) - Display update method
- `src/bot/retranscribe_handlers.py` (~5 lines) - Circular import fix
- `src/storage/models.py` (state tracking fields)

**Key Patterns Established**:
1. **Consistent File Handling**: Same threshold logic for ALL message types (initial, draft, variant, retranscription)
2. **Two-Message Pattern**: Info with keyboard + file message for long texts
3. **State Tracking**: `is_file_message` enables dynamic format switching
4. **Circular Import Resolution**: Move imports inside functions
5. **io.BytesIO Pattern**: In-memory file objects for Telegram

**Testing**:
- ✅ User confirmed file sent instead of split messages
- ✅ Retranscription working without Message_too_long error
- ✅ Bot starts successfully (circular import fixed)
- ✅ All interactive features work with files

**Impact**:
- ✅ File threshold NOW WORKS for all transcription paths
- ✅ No more split messages for long transcriptions
- ✅ Retranscription supports large texts
- ✅ Seamless format switching in interactive mode

**Status**: ✅ COMPLETE - All bugs fixed, feature fully operational
**Completion Date**: 2025-12-08
**Next**: Phase 10.8 - Retranscription with quality settings

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

**7. File Handling Patterns (Phase 10.7-10.7.1)**
- Consistent threshold logic: `FILE_THRESHOLD_CHARS=3000`
- Two-message pattern: info with keyboard + file message
- State tracking: `is_file_message`, `file_message_id`
- 4 transition scenarios supported (text↔text, file↔file, text↔file, file↔text)
- io.BytesIO for in-memory file creation

**8. Circular Import Resolution**
- Move imports inside functions when circular dependency exists
- Pattern: Import at function level instead of module level
- Example: `src/bot/retranscribe_handlers.py` importing CallbackHandlers
- Prevents initialization cycle while maintaining functionality

**9. Parent-Child Usage Tracking** (Phase 10.9)
- Preserve statistics through database relationships instead of overwriting
- Pattern: Create child usage record with `parent_usage_id` foreign key
- Enables retranscription chains: original → child1 → child2
- State migration: Update `state.usage_id` to child for continued interaction
- CASCADE delete: Parent deletion removes children automatically

**10. Progress Bar with Dynamic Duration** (Phase 10.9)
- RTF-based duration for compute methods (free retranscription)
- Fixed duration for API methods (paid retranscription)
- Pattern: `duration = voice_duration * RTF` vs `duration = FIXED_DURATION`
- Provides accurate time estimates based on processing method

**11. Refinement Control via Context** (Phase 10.9)
- Pass behavior flags through TranscriptionContext
- Pattern: `disable_refinement=True` skips LLM processing
- Reusable for testing, user preferences, quality vs speed trade-offs
- Clean separation: context dictates behavior, handler executes

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

### Immediate (Phase 10.12 Deployment)
1. ✅ Implementation complete
2. ✅ Testing complete (24 unit tests + manual testing)
3. ⏳ Update Memory Bank documentation (in progress)
4. ⏳ Create commit with conventional commit message
5. ⏳ Create pull request
6. ⏳ Merge to main
7. ⏳ Deploy to production
8. ⏳ Monitor structured text generation in production
9. ⏳ Gather user feedback on emoji levels and draft threshold

### Future Phases (Post Phase 10)
- **Phase 10.13** (optional): Custom CSS styling for PDFs (user feedback: "Может потом улучшим")
- **Phase 10.14** (optional): Retranscription history UI (show user their retranscription chain)
- **Phase 11**: Analytics dashboard for usage metrics
- **Phase 12**: User quotas and billing system
- **Phase 13**: Multi-language support
- **Phase 14**: Custom vocabulary/terminology support

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
