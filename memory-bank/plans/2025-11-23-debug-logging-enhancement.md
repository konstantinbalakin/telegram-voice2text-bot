# Implementation Plan: Enhanced DEBUG Logging

**Date**: 2025-11-23
**Status**: Approved - Implementation in progress
**Owner**: Development team

## Overview

Add comprehensive DEBUG logging to enable detailed local development debugging with SQL query visibility, method parameters, and request/response bodies.

## User Requirement

> "Я включил DEBUG режим и увидел, что у меня в проекте нет особо таких логов... Хочу в дебаг режиме видеть более подробную информацию о том, что вызывается в SQL, что передается в методы (в том числе и body), чтобы посмотреть что происходило. Полезно при локальной отладке."

**Translation**: "I enabled DEBUG mode and saw that my project doesn't have many such logs... I want to see more detailed information in debug mode about what SQL is being called, what is passed to methods (including body), to see what was happening. Useful for local debugging."

## Selected Approach

**Option 1: Comprehensive DEBUG Logging with SQLAlchemy Echo**

## Implementation Phases

### Phase 1: Logging Infrastructure (30 min)

#### 1.1 Update `src/utils/logging_config.py`

**Changes**:
- Make `app_handler` respect `log_level` parameter (currently hardcoded to INFO)
- Make `console_handler` respect `log_level` parameter (currently hardcoded to INFO)
- Add new `debug_handler` for separate `debug.log` file (DEBUG+, 5MB, 3 backups)
- Keep `error_handler` at ERROR level (unchanged)

**Implementation**:
```python
# app_handler: respect log_level instead of hardcoded INFO
app_handler.setLevel(getattr(logging, log_level.upper()))

# console_handler: respect log_level for development
console_handler.setLevel(getattr(logging, log_level.upper()))

# NEW: debug_handler for separate debug.log
if log_level.upper() == "DEBUG":
    debug_log_file = log_dir / "debug.log"
    debug_handler = logging.handlers.RotatingFileHandler(
        debug_log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8",
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(json_formatter)
    debug_handler.addFilter(version_filter)
    root_logger.addHandler(debug_handler)
```

#### 1.2 Update `src/storage/database.py`

**Changes**:
- Change hardcoded `echo=False` to dynamic based on log level
- Add `echo_pool=True` in DEBUG mode for connection pool debugging

**Implementation**:
```python
# Line 27-32 (get_engine function)
is_debug = settings.log_level.upper() == "DEBUG"
_engine = create_async_engine(
    settings.database_url,
    echo=is_debug,  # Show SQL queries in DEBUG mode
    echo_pool=is_debug,  # Show connection pool activity in DEBUG mode
    future=True,
    pool_pre_ping=True,
)
```

### Phase 2: Strategic DEBUG Logs (90-120 min)

#### 2.1 Bot Handlers - `src/bot/handlers.py` (30 min)

**Priority**: High (request flow visibility)

**Locations**:
1. `start_command()` - Log user registration/lookup
2. `help_command()` - Log help requests
3. `stats_command()` - Log stats queries
4. `voice_message_handler()` / `audio_message_handler()`:
   - Handler entry with user_id, file_id, duration
   - Queue position and estimated wait time
   - Transcription request details
   - Result sending (chunk count, message IDs)

**Example DEBUG logs**:
```python
logger.debug(f"Handler entry: user_id={user.id}, file_id={file.file_id}, "
             f"duration={duration}s, file_size={file.file_size}")
logger.debug(f"Queue position: {position}, queue_depth={queue_depth}, "
             f"estimated_wait={wait_time}s")
logger.debug(f"Transcription request: id={request.id}, "
             f"duration={request.duration_seconds}s, "
             f"file_path={request.file_path}")
logger.debug(f"Sending result: text_length={len(text)}, chunks={num_chunks}")
```

#### 2.2 Storage Repositories - `src/storage/repositories.py` (20 min)

**Priority**: High (database operations visibility)

**UserRepository**:
- `get_by_telegram_id()`: Log query parameter
- `create()`: Log user creation with telegram_id
- `update_usage()`: Log user_id and duration
- `reset_daily_quota()`: Log user_id

**UsageRepository**:
- `create()`: Log usage record creation
- `update()`: Log update stage and fields
- `get_by_id()`: Log query parameter

**Example DEBUG logs**:
```python
logger.debug(f"UserRepository.get_by_telegram_id(telegram_id={telegram_id})")
logger.debug(f"UserRepository.create(telegram_id={telegram_id}, username={username})")
logger.debug(f"UserRepository.update_usage(user_id={user.id}, duration={duration_seconds}s)")
logger.debug(f"UsageRepository.create(user_id={user_id}, voice_file_id={voice_file_id})")
logger.debug(f"UsageRepository.update(usage_id={usage_id}, stage=transcription_complete)")
```

#### 2.3 Queue Manager - `src/services/queue_manager.py` (20 min)

**Priority**: High (queue state visibility)

**Locations**:
- `enqueue()`: Log request enqueue with position
- `_process_request()`: Log request processing start/end
- `get_estimated_wait_time_by_id()`: Log calculation details
- `stop_worker()`: Log worker shutdown

**Example DEBUG logs**:
```python
logger.debug(f"Enqueue: request_id={request.id}, position={position}, "
             f"queue_depth={self._queue.qsize()}, pending={self._total_pending}")
logger.debug(f"Processing request: id={request.id}, user_id={request.user_id}, "
             f"duration={request.duration_seconds}s")
logger.debug(f"Queue state: pending={len(self._pending_requests)}, "
             f"processing={len(self._processing_requests)}")
logger.debug(f"Wait time calculation: request_id={request_id}, "
             f"processing_duration={processing_duration}s, "
             f"pending_duration={pending_duration}s, wait_time={wait_time}s")
```

#### 2.4 Audio Handler - `src/transcription/audio_handler.py` (15 min)

**Priority**: Medium (file operations visibility)

**Locations**:
- `download_voice_message()`: Log download with file details
- `download_from_url()`: Log URL download
- `preprocess_audio()`: Log preprocessing steps
- `_convert_to_mono()`: Log conversion details
- `_adjust_speed()`: Log speed adjustment

**Example DEBUG logs**:
```python
logger.debug(f"Download voice: file_id={file_id}, extension={extension}, "
             f"unique_suffix={unique_suffix}, path={audio_file}")
logger.debug(f"Preprocess audio: input={audio_file}, mono={self.convert_to_mono}, "
             f"speed={self.speed_multiplier}")
logger.debug(f"Convert to mono: input={input_path}, output={output_path}, "
             f"sample_rate={self.target_sample_rate}")
```

#### 2.5 Transcription Providers - `src/transcription/providers/*` (20 min)

**Priority**: Medium (transcription details)

**FasterWhisperProvider** (`faster_whisper_provider.py`):
- `initialize()`: Log model initialization
- `transcribe()`: Log transcription request and result

**OpenAIProvider** (`openai_provider.py`):
- `transcribe()`: Log API request (sanitize API key) and response

**Example DEBUG logs**:
```python
# FasterWhisper
logger.debug(f"FasterWhisper.initialize: model={self.model_size}, "
             f"device={self.device}, compute_type={self.compute_type}")
logger.debug(f"FasterWhisper.transcribe: audio={audio_path.name}, "
             f"language={context.language}, beam_size={self.beam_size}")
logger.debug(f"FasterWhisper.result: text_length={len(text)}, "
             f"segments={len(list(segments))}, duration={info.duration}s")

# OpenAI
logger.debug(f"OpenAI.transcribe: model={self.model}, file={audio_path.name}, "
             f"size={audio_path.stat().st_size}, language={context.language}")
logger.debug(f"OpenAI.result: text_length={len(result.text)}")
```

#### 2.6 LLM Service - `src/services/llm_service.py` (10 min)

**Priority**: Low (LLM details)

**Locations**:
- `refine_transcription()`: Log LLM request and response
- `DeepSeekProvider.refine_text()`: Log API call details (sanitize API key)

**Example DEBUG logs**:
```python
logger.debug(f"LLM.refine_transcription: enabled={self.enabled}, "
             f"text_length={len(draft_text)}")
logger.debug(f"DeepSeek.refine_text: model={self.model}, "
             f"text_length={len(text)}, prompt_length={len(prompt)}")
logger.debug(f"DeepSeek.result: refined_length={len(refined)}, "
             f"tokens_used={response.get('usage', {})}")
```

### Phase 3: Documentation & Testing (30 min)

#### 3.1 Update `.env.example`

**Add DEBUG section**:
```bash
# =============================================================================
# Logging Configuration
# =============================================================================

# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
# DEBUG: Verbose logging for local development
#   - Shows all SQL queries with parameters
#   - Logs method entry/exit with parameters
#   - Includes request/response bodies (sanitized)
#   - Creates separate debug.log file (5MB × 3 backups)
# INFO: Standard production logging (default)
#   - Application events and important operations
#   - No SQL queries or detailed parameters
# WARNING/ERROR/CRITICAL: Production error tracking
LOG_LEVEL=INFO
```

#### 3.2 Local Testing

**Test with DEBUG mode**:
```bash
# Set DEBUG level
export LOG_LEVEL=DEBUG

# Start bot locally
poetry run python -m src.main

# Send test voice message via Telegram
# Check logs/debug.log for:
# - SQL queries
# - Method parameters
# - Queue operations
# - Transcription details
```

**Expected output in `logs/debug.log`**:
```
{"timestamp": "...", "level": "DEBUG", "logger": "sqlalchemy.engine.Engine", "message": "SELECT users.id, users.telegram_id FROM users WHERE users.telegram_id = ?"}
{"timestamp": "...", "level": "DEBUG", "logger": "src.bot.handlers", "message": "Handler entry: user_id=123, file_id=AgADBAAD..."}
{"timestamp": "...", "level": "DEBUG", "logger": "src.services.queue_manager", "message": "Enqueue: request_id=abc-123, position=1, queue_depth=0"}
```

#### 3.3 Validate Production Behavior

**Test with INFO mode**:
```bash
# Set INFO level (production default)
export LOG_LEVEL=INFO

# Start bot
poetry run python -m src.main

# Send test voice message
# Verify:
# - No debug.log created
# - app.log contains only INFO+ logs
# - No SQL queries in logs
# - No excessive detail
```

## Sensitive Data Sanitization

**Rules**:
1. **API Keys**: Log only first/last 4 chars: `sk-****...****xyz`
2. **Bot Token**: Never log, use placeholder: `TELEGRAM_BOT_TOKEN=<hidden>`
3. **User Personal Data**:
   - ✅ Log: user_id, telegram_id
   - ❌ Don't log: username, first_name, last_name in DEBUG
4. **File Content**: Log metadata (size, duration), not content

**Implementation**:
```python
# Sanitize API key
api_key_sanitized = f"{api_key[:4]}****{api_key[-4:]}" if len(api_key) > 8 else "****"
logger.debug(f"API request: key={api_key_sanitized}, ...")

# Log user by ID, not name
logger.debug(f"User lookup: telegram_id={telegram_id}")  # ✅
logger.debug(f"User: {username}")  # ❌
```

## Performance Considerations

1. **DEBUG logs only execute when log level is DEBUG**:
   - Python logging checks level before evaluating f-string
   - Zero overhead in production (INFO level)

2. **Lazy evaluation**:
   ```python
   # Efficient: f-string only evaluated if DEBUG enabled
   logger.debug(f"Complex calculation: {expensive_func()}")

   # Alternative: extra argument (not needed with f-strings)
   logger.debug("Result: %s", expensive_func())
   ```

3. **Disk usage**:
   - debug.log: 5MB × 3 backups = 15MB max
   - Total: app.log (60MB) + errors.log (30MB) + debug.log (15MB) = **105MB max**

## Success Criteria

✅ **Infrastructure**:
- [ ] app_handler respects log_level parameter
- [ ] console_handler respects log_level parameter
- [ ] debug.log created only in DEBUG mode
- [ ] SQLAlchemy echo enabled in DEBUG mode

✅ **DEBUG Logs Added**:
- [ ] Bot handlers: method entry, parameters, queue info
- [ ] Repositories: query parameters, user operations
- [ ] Queue manager: enqueue/dequeue, queue state
- [ ] Audio handler: file operations, preprocessing
- [ ] Transcription providers: model config, results
- [ ] LLM service: API requests, responses

✅ **Testing**:
- [ ] DEBUG mode shows SQL queries in debug.log
- [ ] DEBUG mode shows method parameters
- [ ] DEBUG mode shows request/response bodies
- [ ] INFO mode behavior unchanged (no debug.log, no SQL)
- [ ] Sensitive data properly sanitized

✅ **Documentation**:
- [ ] .env.example updated with DEBUG section
- [ ] Implementation plan documented in memory-bank/plans/

## Rollback Plan

If issues arise:
1. Revert `src/utils/logging_config.py` changes
2. Revert `src/storage/database.py` echo parameter
3. Remove DEBUG log statements (safe to leave, just set LOG_LEVEL=INFO)

## Future Enhancements

Potential future improvements (not in scope):
1. Structured context propagation (Option 3 from planning)
2. Performance profiling logs (timing decorators)
3. Request tracing with correlation IDs
4. Integration with APM tools (Datadog, New Relic)

## References

- User requirement: "DEBUG режим для локальной отладки"
- Planning document: Option 1 - Comprehensive DEBUG Logging
- Existing patterns: `src/utils/logging_config.py`, JSON logging, version enrichment
