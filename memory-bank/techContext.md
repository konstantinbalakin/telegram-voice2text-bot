# Technical Context: Telegram Voice2Text Bot

## Technology Stack

**Current Status**: ✅ API-First Architecture (2025-01-09)

### Core Technologies

### Programming Language: **Python 3.11+**

**Decision Rationale**:
- ✅ Excellent Whisper integration (native Python library)
- ✅ Mature Telegram bot ecosystem
- ✅ Strong async support (asyncio)
- ✅ Rich testing and tooling ecosystem
- ✅ Best choice for AI/ML workloads

**Version**: Python 3.11 or 3.12 (3.13+ compatible)

### Telegram Bot Framework: **python-telegram-bot v22.5**

**Selected**: `python-telegram-bot` v22.5 (latest, September 2025)

**Decision Rationale**:
- ✅ Most mature Python Telegram library
- ✅ Excellent async support
- ✅ Active maintenance
- ✅ Comprehensive documentation
- ✅ Supports both polling and webhook modes

**Alternatives Considered**:
- aiogram: Good, but python-telegram-bot more established
- pytelegrambotapi: Synchronous, not suitable for our async architecture

### Transcription Stack

**Primary: OpenAI Whisper API**
- **Models**: whisper-1 (default), gpt-4o-transcribe, gpt-4o-mini-transcribe
- **Performance**: 5-10s for 1-minute audio
- **Quality**: Best-in-class for Russian speech
- **Cost**: $0.006/minute
- **Added**: 2025-12-15

**Fallback: faster-whisper v1.2.0 (local)**
- **Model**: medium/int8/beam1
- **Performance**: 20-36s for 1-minute audio
- **Quality**: Good (but not excellent like OpenAI)
- **Cost**: Free
- **Role**: Reliability fallback when OpenAI API unavailable
- **Status**: Kept for reliability, not primary

**Decision Rationale:**
- API-first provides 4-7x faster transcription
- Better quality for Russian speech
- Enables LLM-powered text processing features
- Cost acceptable for UX quality (~$0.006 per message)

### Text Processing

**Provider: DeepSeek V3**
- **Model**: deepseek-chat
- **Features**: Structuring, Magic, Summary modes
- **Performance**: 2-5s processing time
- **Cost**: ~$0.0002 per 60s audio
- **Quality**: Excellent Russian text transformation
- **Added**: 2025-12-04

**Decision Rationale:** See [architecture-evolution.md](./architecture-evolution.md)

## Complete Dependency Stack

**Package Manager**: **uv** (migrated from Poetry - 2026-01-27)
- Fast Rust-based Python package manager
- PEP 621 standard pyproject.toml format
- Lock file: `uv.lock` (95 packages)
- **Migration Complete**: All 181 tests passing, CI/CD updated

```toml
[project]
requires-python = ">=3.11,<4.0"

dependencies = [
    # Core
    "python-telegram-bot>=22.5,<23.0",  # Telegram Bot API
    
    # Database
    "sqlalchemy[asyncio]>=2.0.44,<3.0.0",
    "aiosqlite>=0.20.0,<0.21.0",        # SQLite async driver
    "alembic>=1.13,<2.0",               # Database migrations
    
    # Configuration & Utilities
    "python-dotenv>=1.0.0,<2.0.0",      # Environment variables
    "pydantic>=2.10,<3.0",              # Data validation
    "pydantic-settings>=2.6,<3.0",      # Settings management
    
    # Logging
    "python-json-logger>=4.0.0,<5.0.0", # JSON log formatting
    
    # Async HTTP & LLM Integration
    "httpx>=0.28,<0.29",                # Async HTTP client
    "tenacity>=9.0.0,<10.0.0",          # Retry logic
    
    # PDF Generation
    "weasyprint>=62.3,<63.0",           # HTML to PDF conversion
    "pydyf>=0.11.0,<0.12.0",            # PDF library
    
    # Audio Manipulation
    "pydub>=0.25.1,<0.26.0",            # Audio splitting
    
    # System Monitoring
    "psutil>=6.1,<7.0",
]

[project.optional-dependencies]
faster-whisper = ["faster-whisper>=1.2.1,<2.0.0"]
openai-api = ["openai>=1.50.0,<2.0.0"]

[dependency-groups]
dev = [
    "pytest>=8.3,<9.0",
    "pytest-asyncio>=0.24,<0.25",
    "pytest-cov>=6.0,<7.0",
    "black>=24.10,<25.0",
    "ruff>=0.8,<0.9",
    "mypy>=1.13,<2.0",
]
```

**Dependency Update Notes**:
- `tenacity ^9.0.0` added (2025-11-20): Provides exponential backoff retry logic for LLM API calls
  - Used in `DeepSeekProvider` for resilient API integration
  - Retry strategy: 3 attempts, exponential backoff (2-10s), retries on timeout/network errors
- `httpx ^0.28` now also used for LLM API communication (previously just for internal services)
- `pydub ^0.25.1` added (2025-12-17): Audio manipulation library for OpenAI long audio chunking
  - Source Reputation: High
  - Development Status: Production/Stable
  - License: MIT
  - Used in `OpenAIProvider` for splitting long audio files that exceed duration limits

## System Dependencies

**ffmpeg** (Required for audio preprocessing and video file support):
- **Purpose**: Audio format conversion, video-to-audio extraction, duration detection
- **Installation**:
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `apt-get install -y ffmpeg`
  - Docker: Already included in Dockerfile
- **Features using ffmpeg**:
  - `AUDIO_CONVERT_TO_MONO=true` - Convert stereo to mono for faster processing
  - `AUDIO_SPEED_MULTIPLIER` - Adjust playback speed (0.5x-2.0x)
  - **Video audio extraction** - Extract audio tracks from video files (.mp4, .mkv, .avi, .mov, .webm)
  - **Duration detection** - ffprobe for document/video duration analysis
  - **Audio stream validation** - Check if video contains audio before extraction
- **Fallback**: Bot works without ffmpeg for voice messages, but document/video support requires ffmpeg

**WeasyPrint System Dependencies** (NEW - 2025-12-09, Required for PDF generation):
- **Purpose**: HTML to PDF conversion for large transcriptions (>3000 chars)
- **Installation**:
  - Ubuntu/Debian (Dockerfile): `apt-get install -y libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info`
  - macOS: `brew install cairo pango gdk-pixbuf libffi`
- **Docker Image Impact**: ~100MB increase (acceptable for PDF quality)
- **Features**:
  - Professional PDF styling (Arial, 12pt, proper margins)
  - Cyrillic text support (FontConfiguration)
  - HTML rendering (bold, italic, lists, code blocks, links)
- **Fallback**: If PDF generation fails, automatically falls back to .txt files

## Supported File Formats (Added 2025-12-25)

### Input File Types

The bot now supports comprehensive file type handling through four message handlers:

**1. Voice Messages** (`voice_message_handler`):
- Standard Telegram voice input (recorded with microphone button)
- Format: OGG/Opus (Telegram default)
- Direct transcription, no preprocessing needed

**2. Audio Files** (`audio_message_handler`):
- Sent as Telegram "audio" messages (music files with metadata)
- Formats: .mp3, .ogg, .opus, .wav, .m4a, etc.
- Direct transcription

**3. Document Files** (`document_message_handler`):
- Audio files sent as documents
- **Supported Audio MIME Types** (17 formats):
  - `audio/aac` - AAC audio files (.aac)
  - `audio/mp4` - MP4 audio (.m4a)
  - `audio/mpeg`, `audio/mp3` - MP3 audio
  - `audio/ogg`, `audio/opus` - OGG/Opus
  - `audio/wav`, `audio/x-wav` - WAV audio
  - `audio/flac`, `audio/x-flac` - FLAC lossless
  - `audio/x-m4a`, `audio/m4a` - M4A audio
  - `audio/amr` - AMR (Adaptive Multi-Rate)
  - `audio/x-ms-wma` - Windows Media Audio
  - `audio/webm` - WebM audio
  - `audio/3gpp` - 3GP audio
- **Silent Filtering**: Non-audio documents ignored without error

**4. Video Files** (`video_message_handler`):
- Video files with audio track extraction
- **Supported Video MIME Types** (7 formats):
  - `video/mp4` - MP4 video (.mp4)
  - `video/quicktime` - QuickTime video (.mov)
  - `video/x-msvideo` - AVI video (.avi)
  - `video/x-matroska` - Matroska video (.mkv)
  - `video/webm` - WebM video
  - `video/3gpp` - 3GP video
  - `video/mpeg` - MPEG video
- **Audio Extraction**: ffmpeg extracts audio to mono Opus (16kHz, 32kbps)
- **Validation**: Checks for audio stream before extraction
- **Error Handling**: "❌ Видео не содержит аудиодорожки" if no audio

### Audio Processing Pipeline

```
Input File (any type)
  ↓
Handler Selection (by Telegram update type)
  ↓
MIME Type Validation (for documents)
  ├─ Audio MIME → Continue
  └─ Other MIME → Silent ignore
  ↓
File Download (Bot API ≤20MB, Client API >20MB)
  ↓
Audio Extraction (for video files only)
  ├─ Check audio stream exists
  ├─ Extract to mono Opus (16kHz, 32kbps)
  └─ Cleanup original video file
  ↓
Duration Detection
  ├─ Voice/Audio: from Telegram metadata
  └─ Document/Video: ffprobe analysis
  ↓
Format Optimization (provider-aware)
  ├─ faster-whisper: Keep OGG/Opus
  └─ OpenAI gpt-4o: Convert to MP3/WAV
  ↓
Transcription (unified pipeline for all types)
  ↓
Response with text + interactive keyboard
```

### Configuration

**MIME Type Sets** (`src/config.py`):
```python
SUPPORTED_AUDIO_MIMES: set[str] = {
    "audio/aac", "audio/mp4", "audio/mpeg", "audio/mp3",
    "audio/ogg", "audio/opus", "audio/wav", "audio/x-wav",
    "audio/flac", "audio/x-flac", "audio/x-m4a", "audio/m4a",
    "audio/amr", "audio/x-ms-wma", "audio/webm", "audio/3gpp",
}

SUPPORTED_VIDEO_MIMES: set[str] = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/3gpp", "video/mpeg",
}
```

**Handler Registration** (`src/main.py`):
```python
# Existing handlers
application.add_handler(MessageHandler(filters.VOICE, bot_handlers.voice_message_handler))
application.add_handler(MessageHandler(filters.AUDIO, bot_handlers.audio_message_handler))

# NEW handlers (Phase 10.15)
application.add_handler(MessageHandler(filters.DOCUMENT, bot_handlers.document_message_handler))
application.add_handler(MessageHandler(filters.VIDEO, bot_handlers.video_message_handler))
```

### Implementation Details

**Key Methods** (added in Phase 10.15):
- `AudioHandler.extract_audio_track()` - Extract audio from video (ffmpeg)
- `AudioHandler._has_audio_stream()` - Validate audio stream exists (ffprobe)
- `AudioHandler.get_audio_duration_ffprobe()` - Detect duration for documents/video
- `BotHandlers.document_message_handler()` - Handle audio documents
- `BotHandlers.video_message_handler()` - Handle video files

**Tests** (added in Phase 10.15):
- `tests/unit/test_audio_extraction.py` - Audio stream detection, extraction success/failure

---

## Cost Structure (Added 2025-01-09)

### Per-Message Costs

**Per 60-second message:**
- OpenAI transcription: $0.006
- DeepSeek processing: ~$0.0002
- **Total: ~$0.0062 per message**

### Monthly Estimates

**Scenario: 100 messages/day**
- 100 messages/day × 30 days = 3,000 messages
- 3,000 × 60s = 180,000 seconds = 50 hours
- **Cost: 3,000 × $0.0062 = $18.60/month**

**Scenario: 1,000 messages/day**
- 1,000 messages/day × 30 days = 30,000 messages
- 30,000 × 60s = 1,800,000 seconds = 500 hours
- **Cost: 30,000 × $0.0062 = $186/month**

### Comparison: API-First vs Local-Only

| Metric | API-First | Local-Only |
|--------|-----------|------------|
| **Cost** | $18.60/month (100 daily) | $0/month |
| **Speed** | 7-15s total | 20-36s |
| **Quality** | Excellent (OpenAI) | Good (faster-whisper) |
| **Features** | Structure, Magic, Summary | Basic transcription only |
| **Memory** | <500MB RAM | ~2GB RAM |
| **UX** | Users love it | Too slow, poor UX |

**Conclusion**: API costs are acceptable for the UX quality and features provided

### Cost Optimization Strategies

**Implemented:**
- ✅ Variant caching prevents duplicate LLM calls
- ✅ Fallback to local when API unavailable
- ✅ Efficient batching (future improvement)

**Future Considerations:**
- Free tier with daily limits (e.g., 10 messages/day free)
- Paid tiers for heavy users
- Common phrase caching
- Hybrid mode: Short = local, long = API

---

## Project Structure (Updated 2025-10-29)

### Services Layer

**Location**: `src/services/`

**Purpose**: Business logic components for request management, user experience, and LLM integration

**Modules**:

1. **queue_manager.py** (296 lines)
   - `QueueManager`: FIFO queue with concurrency control
   - `TranscriptionRequest`: Request data structure
   - `TranscriptionResponse`: Response data structure
   - **Features**:
     - `asyncio.Queue` for FIFO request storage (max 50)
     - `asyncio.Semaphore` for concurrency limiting (max_concurrent=1)
     - Background worker with graceful error handling
     - Request/response tracking with timeout support
   - **Pattern**: Producer-Consumer with bounded queue

2. **progress_tracker.py** (201 lines)
   - `ProgressTracker`: Live progress updates for long-running operations
   - **Features**:
     - Background asyncio task updates Telegram message every 5s
     - Visual progress bar: `🔄 [████████░░░░] 40%`
     - RTF-based time estimation (processing_time = duration × 0.3)
     - Telegram rate limit handling (RetryAfter, TimedOut)
   - **Pattern**: Observer pattern - tracks progress without blocking

3. **llm_service.py** (263 lines) - NEW (2025-11-20)
   - `LLMProvider`: Abstract base class for LLM providers
   - `DeepSeekProvider`: DeepSeek V3 API integration
   - `LLMFactory`: Provider instantiation
   - `LLMService`: High-level LLM API
   - **Features**:
     - Async HTTP client (httpx) for API calls
     - Retry logic with exponential backoff (tenacity)
     - Text truncation (10,000 char limit)
     - Graceful error handling (timeout, API errors, network errors)
     - Automatic fallback to draft text on any failure
   - **Pattern**: Abstract provider pattern + Factory pattern + Service layer
   - **Integration**: Used for hybrid transcription refinement

4. **pdf_generator.py** (132 lines) - NEW (2025-12-09)
   - `PDFGenerator`: HTML to PDF conversion service
   - **Methods**:
     - `generate_pdf(html_content)` - Converts HTML string to PDF bytes
     - `create_styled_html(content)` - Wraps content in styled HTML template
     - `generate_pdf_from_text(text)` - Plain text to PDF with paragraph wrapping
   - **Features**:
     - WeasyPrint-based HTML to PDF conversion
     - Professional styling (Arial, 12pt, proper line height, margins)
     - Cyrillic support via FontConfiguration
     - Code blocks, lists, links rendering
     - In-memory PDF generation (io.BytesIO)
     - Graceful error handling with detailed logging
   - **Pattern**: Service layer for document generation
   - **Integration**: Used for large transcription files (>3000 chars)

5. **__init__.py**
   - Module exports: `QueueManager`, `TranscriptionRequest`, `TranscriptionResponse`, `ProgressTracker`, `LLMService`, `PDFGenerator`

6. **transcription_orchestrator.py** (792 lines) - NEW (2026-02-15)
   - `TranscriptionOrchestrator`: Core business logic extracted from BotHandlers
   - **Methods**: `_preprocess_audio`, `_run_transcription`, `_apply_structuring`, `_apply_refinement`, `_finalize_and_send`
   - **Pattern**: Service layer — handlers only route, orchestrator processes
   - **Integration**: Used by BotHandlers via `_handle_media_message()`

7. **lifecycle.py** (20 lines) - NEW (2026-02-15)
   - `AsyncService`: Runtime-checkable Protocol
   - **Methods**: `initialize()`, `shutdown()`, `is_initialized`
   - **Pattern**: Uniform async lifecycle for all services/providers

**Usage**:
```python
# In main.py
queue_manager = QueueManager(
    max_queue_size=settings.max_queue_size,
    max_concurrent=settings.max_concurrent_workers,
)

# In handlers.py
request = TranscriptionRequest(
    id=str(uuid.uuid4()),
    user_id=user.id,
    file_path=file_path,
    duration_seconds=duration_seconds,
    context=transcription_context,
    status_message=status_msg,
    usage_id=usage.id,
)
position = await self.queue_manager.enqueue(request)

# Progress tracking
progress = ProgressTracker(
    message=request.status_message,
    duration_seconds=request.duration_seconds,
    rtf=settings.progress_rtf,
    update_interval=settings.progress_update_interval,
)
await progress.start()
# ... transcription ...
await progress.stop()
```

**Added**: 2025-10-29 (Phase 6: Queue-Based Concurrency Control)

### Storage Layer Updates (2025-10-29)

**Enhanced Repository Pattern**:
- `UsageRepository.create()`: Minimal create for staged writes (Stage 1)
- `UsageRepository.update()`: Update method for lifecycle stages (Stage 2, 3)
- `UsageRepository.get_by_id()`: Retrieve usage record by ID

**Database Model Changes**:
- `Usage.updated_at`: Added for lifecycle tracking
- `Usage.transcription_length`: Added (int) for privacy-friendly analytics
- `Usage.transcription_text`: Removed (privacy improvement)
- `Usage.voice_duration_seconds`: Now nullable for staged writes
- `Usage.model_size`: Now nullable for staged writes

**Migration**: `alembic/versions/a9f3b2c8d1e4_add_updated_at_and_transcription_length.py`

### Configuration Updates

**Queue & Progress Settings** (2025-10-29):
```python
# Queue Configuration
max_queue_size: int = 50  # Changed from 100
max_concurrent_workers: int = 1  # Changed from 3
transcription_timeout: int = 120

# Progress Tracking
progress_update_interval: int = 5
progress_rtf: float = 0.3

# Quotas
max_voice_duration_seconds: int = 120  # Changed from 300 (2 minutes)
```

**LLM & Hybrid Settings** (NEW - 2025-11-20):
```python
# LLM Refinement Configuration
llm_refinement_enabled: bool = Field(default=False)  # Disabled by default
llm_provider: str = Field(default="deepseek")
llm_api_key: str | None = Field(default=None)
llm_model: str = Field(default="deepseek-chat")
llm_base_url: str = Field(default="https://api.deepseek.com")
llm_refinement_prompt: str = Field(default="Улучши транскрипцию...")
llm_timeout: int = Field(default=30)

# Hybrid Strategy Configuration
hybrid_short_threshold: int = Field(default=20)  # seconds
hybrid_draft_provider: str = Field(default="faster-whisper")
hybrid_draft_model: str = Field(default="small")
hybrid_quality_provider: str = Field(default="faster-whisper")
hybrid_quality_model: str = Field(default="medium")

# Audio Preprocessing Configuration
audio_convert_to_mono: bool = Field(default=False)
audio_target_sample_rate: int = Field(default=16000)
audio_speed_multiplier: float = Field(default=1.0)

# Provider-Aware Audio Format Configuration (NEW - 2025-12-15)
openai_4o_transcribe_preferred_format: str = Field(default="mp3")  # or "wav"
OPENAI_FORMAT_REQUIREMENTS = {
    "gpt-4o-transcribe": ["mp3", "wav"],         # Requires conversion
    "gpt-4o-mini-transcribe": ["mp3", "wav"],    # Requires conversion
    "whisper-1": None,                            # Supports OGA
}

# OpenAI Long Audio Handling Configuration (NEW - 2025-12-17)
openai_gpt4o_max_duration: int = Field(default=1400)              # Max duration for gpt-4o models
openai_change_model: bool = Field(default=True)                   # Auto-switch to whisper-1
openai_chunking: bool = Field(default=False)                      # Enable audio chunking
openai_chunk_size_seconds: int = Field(default=1200, ge=300, le=1400)  # Chunk size
openai_chunk_overlap_seconds: int = Field(default=2, ge=0, le=10)      # Chunk overlap
openai_parallel_chunks: bool = Field(default=True)                # Parallel processing
openai_max_parallel_chunks: int = Field(default=3, ge=1, le=10)   # Max concurrent chunks
```

**Environment Variables**:
```bash
# Existing
MAX_VOICE_DURATION_SECONDS=120
MAX_QUEUE_SIZE=50
MAX_CONCURRENT_WORKERS=1
PROGRESS_UPDATE_INTERVAL=5
PROGRESS_RTF=0.3

# NEW - Hybrid Transcription (2025-11-20)
LLM_REFINEMENT_ENABLED=false
LLM_PROVIDER=deepseek
LLM_API_KEY=your_api_key_here
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com
LLM_TIMEOUT=30

HYBRID_SHORT_THRESHOLD=20
HYBRID_DRAFT_PROVIDER=faster-whisper
HYBRID_DRAFT_MODEL=small
HYBRID_QUALITY_PROVIDER=faster-whisper
HYBRID_QUALITY_MODEL=medium

AUDIO_CONVERT_TO_MONO=false
AUDIO_TARGET_SAMPLE_RATE=16000
AUDIO_SPEED_MULTIPLIER=1.0

# NEW - Provider-Aware Audio Format (2025-12-15)
OPENAI_4O_TRANSCRIBE_PREFERRED_FORMAT=mp3  # Options: mp3, wav

# NEW - OpenAI Long Audio Handling (2025-12-17)
OPENAI_GPT4O_MAX_DURATION=1400             # Maximum duration for gpt-4o models (seconds)
OPENAI_CHANGE_MODEL=true                   # Auto-switch to whisper-1 for long audio
OPENAI_CHUNKING=false                      # Enable audio chunking for long files
OPENAI_CHUNK_SIZE_SECONDS=1200             # Size of each chunk (300-1400s)
OPENAI_CHUNK_OVERLAP_SECONDS=2             # Overlap between chunks (0-10s)
OPENAI_PARALLEL_CHUNKS=true                # Process chunks in parallel (faster)
OPENAI_MAX_PARALLEL_CHUNKS=3               # Max concurrent chunk requests (1-10)
```

### Logging Configuration (2025-11-03)

**New Module**: `src/utils/logging_config.py` (233 lines)

**Purpose**: Centralized logging with version tracking, structured JSON format, and size-based rotation

**Components**:
1. **VersionEnrichmentFilter**: Adds version and container_id to all log records
2. **CustomJsonFormatter**: JSON formatter with ISO timestamps and structured context
3. **setup_logging()**: Configures file handlers with rotation and optional remote syslog
4. **log_deployment_event()**: Records deployment lifecycle events

**Log Files** (in `/app/logs/` or `LOG_DIR`):
- `app.log`: All INFO+ logs, 10MB per file, 5 backups (60MB max)
- `errors.log`: ERROR/CRITICAL only, 5MB per file, 5 backups (30MB max)
- `deployments.jsonl`: Deployment events, never rotated (~1KB per deployment)

**Environment Variables**:
```bash
# Required
APP_VERSION=v0.1.0  # Set by CI/CD from git tag
LOG_DIR=/app/logs
LOG_LEVEL=INFO

# Optional (remote syslog)
SYSLOG_ENABLED=false
SYSLOG_HOST=logs.papertrailapp.com
SYSLOG_PORT=514
```

**Integration**:
- Called from `src/main.py` at startup
- Volume mount: `./logs:/app/logs` in docker-compose
- All log entries automatically include version (short form: 09f9af8)

**Log Format Example**:
```json
{
  "timestamp": "2025-11-03T15:00:05.123Z",
  "level": "INFO",
  "logger": "src.bot.handlers",
  "version": "09f9af8",
  "container_id": "e3f297d9fe90",
  "message": "Processing voice message",
  "context": {
    "user_id": 123456,
    "duration": 45.2,
    "file_size": 128000
  }
}
```

**Key Design Decision**: Size-based rotation ONLY (not time-based) per user request: "Если мало логов, то пусть хранятся долго". Logs persist longer when generation is low, predictable disk usage (~90MB max).

## Development Environment

### Setup Requirements

✅ **Python 3.11+**
```bash
# Check version
python3 --version

# Recommended: pyenv for version management
pyenv install 3.11.9
pyenv local 3.11.9
```

✅ **uv** (dependency management)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

✅ **Git**
```bash
git init
git config user.name "Your Name"
git config user.email "pass@localhost"
```

✅ **Environment Variables**
```bash
cp .env.example .env
# Edit .env with your Telegram Bot Token
```

### Development Tools

**IDE/Editor**: VS Code recommended
- Extensions: Python, Pylance, Ruff, GitLens

**Package Manager**: uv
- Installation: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Commands: `uv sync`, `uv run`, `uv add`, `uv remove`
- Lock file: `uv.lock` (committed to repository)

**Code Quality**:
- `black` - auto-formatting
- `ruff` - fast linting
- `mypy` - type checking
- `pre-commit` / `pre-push` hooks (ruff, black, mypy, pytest)

**Testing**:
- `pytest` - test runner (590 tests: 579 unit + 11 integration)
- `pytest-asyncio` - async tests
- `pytest-cov` - coverage reports

## Infrastructure

### Development Environment (Current Phase)

**Mode**: Local development with polling

**Requirements**:
- Python 3.11+ installed
- Telegram Bot Token from @BotFather
- 4GB+ RAM (for Whisper model)
- ~2GB disk space (for model cache)

**Data Storage**: SQLite database (`./data/bot.db`)

### Production/Deployment (Current Status)

**Deployment Approach**: Docker + docker-compose ✅ IMPLEMENTED (2025-10-16)

**Current Phase**: Local Docker deployment complete, ready for VPS

**Docker Implementation**:
- **Dockerfile**: Single-stage python:3.11-slim-bookworm
  - ffmpeg for audio processing
  - Build cache mounting for faster rebuilds
  - Non-root user (appuser) for security
  - Health checks (30s interval)
  - Image size: ~1GB (acceptable for ML workload)
  - Build time: ~4 minutes (with cache)

- **docker-compose.yml**: Production-ready orchestration
  - Service: telegram-voice2text-bot
  - Restart policy: unless-stopped
  - Environment: .env file support
  - Volumes:
    - ./data:/app/data (SQLite persistence)
    - ./logs:/app/logs (log persistence)
    - whisper-models (named volume for model cache)
  - Resource limits: 2 CPUs, 2GB RAM
  - PostgreSQL service ready (commented out)

- **Makefile**: Workflow automation
  - `make deps` - Export uv dependencies to requirements.txt
  - `make build` - Build Docker image
  - `make up` - Start container
  - `make down` - Stop container
  - `make logs` - View logs
  - `make rebuild` - Full rebuild
  - `make clean` - Docker cleanup

**Phase Progression**:
- ✅ **Phase 1 (Current)**: Local Docker with polling
- ⏳ **Phase 2**: VPS deployment (polling mode)
- ⏳ **Phase 3**: Webhook mode with SSL
- ⏳ **Phase 4**: PostgreSQL migration
- ⏳ **Phase 5**: CI/CD pipeline

## Technical Constraints

### Known Constraints

- Must work with Telegram Bot API
- Voice message format: OGG/Opus (Telegram standard)
- Rate limiting: Telegram API limits to consider
- (Others to be identified)

### Performance Requirements

(To be defined based on use case)
- Response time expectations
- Concurrent user handling
- Message processing throughput

### Resource Constraints

- Budget considerations (if using paid APIs)
- Server/compute resources
- Storage requirements

## Configuration Management

**Approach**: Environment variables + Pydantic Settings

### Configuration Structure

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    bot_mode: str = "polling"  # polling or webhook

    # Whisper
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    # Processing
    max_queue_size: int = 100
    max_concurrent_workers: int = 3
    transcription_timeout: int = 120

    # Quotas
    default_daily_quota_seconds: int = 60
    max_voice_duration_seconds: int = 300

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```

### Environment Files

**.env.example** (template):
```bash
TELEGRAM_BOT_TOKEN=your_token_here
BOT_MODE=polling
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
LOG_LEVEL=INFO
```

**.env** (actual, gitignored):
- Contains real bot token
- Environment-specific overrides

## Development Workflow

### Version Control

**Setup**: Git repository
**Branching**: trunk-based (main branch)
**Commit Style**: Conventional Commits preferred

### Testing Strategy

**Framework**: pytest + pytest-asyncio

**Coverage Goals**:
- Unit tests: >70% coverage
- Integration tests for critical paths
- End-to-end tests for main user flows

**Test Structure**:
```
tests/
├── unit/
│   ├── test_whisper_service.py
│   ├── test_quota_manager.py
│   └── test_queue_manager.py
├── integration/
│   ├── test_bot_workflow.py
│   └── test_database.py
└── conftest.py  # Fixtures
```

### CI/CD (Future - Phase 4) ✅ IMPLEMENTED (2025-10-19)

**Platform**: GitHub Actions ✅

**Workflows Operational**:

1. **CI Workflow** (`.github/workflows/ci.yml`) ✅
   - **Trigger**: Pull requests to main branch
   - **Quality Gates**:
     - pytest with coverage reporting
     - mypy type checking (strict mode)
     - ruff linting
     - black formatting verification
   - **Caching**: uv dependencies cached by uv.lock hash
   - **Coverage**: Reports uploaded to Codecov

2. **Build & Deploy Workflow** (`.github/workflows/build-and-deploy.yml`) ✅
   - **Trigger**: Push to main branch (after PR merge)
   - **Build Stage**:
     - Export uv dependencies to requirements.txt
     - Build Docker image with Docker Buildx
     - Push to Docker Hub with dual tags (latest + SHA)
     - GitHub Actions cache for Docker layers
   - **Deploy Stage** (ready, awaiting VPS):
     - SSH to VPS server
     - Pull latest code
     - Create .env from GitHub Secrets
     - Pull and deploy new Docker image
     - Rolling update with health checks
     - Automatic image cleanup

**Protection**:
- ✅ Main branch protected on GitHub
- ✅ Requires PR for all changes
- ✅ CI checks must pass before merge

**Secrets Configured**:
- ✅ TELEGRAM_BOT_TOKEN
- ✅ DOCKER_USERNAME
- ✅ DOCKER_PASSWORD
- ⏳ VPS_HOST (pending VPS purchase)
- ⏳ VPS_USER (pending VPS purchase)
- ⏳ VPS_SSH_KEY (pending VPS purchase)

**Status**: ✅ Fully operational, awaiting VPS infrastructure only

## Tool Usage Patterns

### Telegram Bot API

Key APIs to use:
- `getUpdates` or webhook?
- `sendMessage`
- `getFile` (for voice messages)
- Others as needed

### Voice Processing

(Integration patterns to be documented once approach is chosen)

## Technical Decisions Log

**Recent Updates (2026-02-16): Code Audit & Refactoring**

| Date | Area | Decision | Status | Rationale |
|------|------|----------|--------|-----------|
| 2026-02 | Architecture | **TranscriptionOrchestrator** | ✅ Active | Extract business logic from handlers (God Object elimination) |
| 2026-02 | Architecture | **MediaInfo dataclass** | ✅ Active | Unified media handling for voice/audio/document/video |
| 2026-02 | Architecture | **AsyncService Protocol** | ✅ Active | Uniform async lifecycle for services |
| 2026-02 | Security | **IDOR protection** | ✅ Active | Callback query ownership verification |
| 2026-02 | Quality | **Pre-commit hooks** | ✅ Active | Automated gates: ruff, black, mypy, pytest |
| 2026-01-27 | Package Manager | **uv (from Poetry)** | ✅ Active | Faster builds, PEP 621 standard, Rust-based |
| 2025-12-25 | Transcription | **OpenAI API primary** | ✅ Active | 4-7x faster, better quality |
| 2025-12-25 | Text Processing | **DeepSeek V3** | ✅ Active | Cost-effective LLM |
| 2025-12-25 | Fallback | **Local model** | ✅ Active | Reliability |
| 2025-12-15 | OpenAI Provider | **gpt-4o-transcribe** | ✅ Active | Even better quality |
| 2025-12-04 | LLM Integration | **DeepSeek V3** | ✅ Active | Intelligent text processing |
| 2025-11-20 | Hybrid Strategy | **Draft + LLM** | ⚠️ Replaced | Superseded by API-first |

**Historical Decisions (2025-10-12 → 2025-12-25): Local-First Architecture**

| Date | Area | Decision | Status | Rationale |
|------|------|----------|--------|-----------|
| 2025-10-12 | Language | Python 3.11+ | ✅ Active | Best Whisper integration, mature ecosystem |
| 2025-10-12 | Bot Framework | python-telegram-bot 22.5 | ✅ Active | Most mature, async support, both polling/webhook |
| 2025-10-12 | Voice Processing | faster-whisper 1.2.0 | ⚠️ Fallback | 4x faster, less memory, no API costs (too slow) |
| 2025-10-12 | Architecture | Hybrid Queue (Option 3) | ✅ Active | Balance simplicity/scalability |
| 2025-10-12 | Database | SQLAlchemy + SQLite/PostgreSQL | ✅ Active | Async ORM, migration support |
| 2025-10-12 | Deployment | Docker + VPS | ✅ Active | Full control, cost-effective |
| 2025-10-16 | Docker Base Image | python:3.11-slim-bookworm | ✅ Active | Good balance of size and compatibility |
| 2025-10-16 | Dockerfile Strategy | Single-stage | ✅ Active | Simpler, adequate optimization for use case |
| 2025-10-16 | Build Optimization | Build cache mounting | ✅ Active | Significantly faster rebuilds (minutes vs tens of minutes) |
| 2025-10-19 | CI/CD Platform | GitHub Actions | ✅ Active | Free for public repos, native GitHub integration, excellent caching |
| 2025-10-19 | Branch Protection | Protected main branch | ✅ Active | Enforces code review, prevents direct commits |
| 2025-10-19 | Deployment Strategy | Automated via SSH | ✅ Active | Simple, reliable, zero-downtime rolling updates |
| 2025-10-19 | Docker Registry | Docker Hub | ✅ Active | Free for public images, widely used, reliable |

**For complete evolution story:** See [architecture-evolution.md](./architecture-evolution.md)

## Learning Resources

(Document useful resources discovered during development)

- Telegram Bot API Documentation
- Chosen framework documentation
- Voice processing service docs
- Relevant tutorials/guides

## Notes

This document should be updated as technology decisions are made and technical patterns emerge. It's especially important to document the "why" behind technology choices for future reference.
