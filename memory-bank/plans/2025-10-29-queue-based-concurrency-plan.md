# Queue-Based Concurrency Control Implementation Plan

**Date**: 2025-10-29
**Status**: Approved
**Branch**: `claude/optimize-bot-performance-011CUbRo6dFSvNks9ZkKv7e7`

## Context

Bot crashed during production testing when processing a 4-minute audio file on 2 CPU / 2 GB RAM VPS. Root cause: no concurrency controls, no queue management, no duration limits.

## Objectives

1. **Prevent crashes** under concurrent load
2. **Improve UX** with clear feedback and progress tracking
3. **Add duration limits** to prevent resource exhaustion
4. **Enhance database** for better analytics and privacy
5. **Maintain quality** using existing medium/int8/beam1 model

## Configuration

- **Hardware**: Keep current 2 CPU / 2 GB RAM (no upgrade)
- **Concurrency**: `max_concurrent=1` (sequential processing)
- **Duration Limit**: `max_voice_duration_seconds=120` (2 minutes)
- **Queue Size**: `max_queue_size=50`
- **Model**: `faster-whisper/medium/int8/beam1` (RTF ~0.3x)

## Implementation Phases

### Phase 1: Database Migration (1-2 hours)

**Goal**: Add analytics tracking and remove sensitive data

**Changes to `usage` table**:
```python
class Usage:
    id: int
    user_id: int
    voice_file_id: str
    voice_duration_seconds: int | None
    model_size: str | None
    processing_time_seconds: float | None
    transcription_length: int | None  # NEW: char count instead of text
    created_at: datetime  # Stage 1: on download
    updated_at: datetime  # NEW: Stage 2, 3: on updates
```

**Migration Steps**:
1. Create Alembic migration script
2. Add `updated_at` column (timestamp)
3. Add `transcription_length` column (int, nullable)
4. Drop `transcription_text` column (privacy)
5. Test migration on dev database

**Files**:
- `alembic/versions/XXXX_add_updated_at_and_transcription_length.py` (new)

**Success Criteria**:
- ✅ Migration runs without errors
- ✅ Existing data preserved (except transcription_text)
- ✅ All tests pass

---

### Phase 2: Queue Manager Implementation (4-5 hours)

**Goal**: Implement robust request queue with concurrency control

**New Module**: `src/services/queue_manager.py`

**Key Components**:

```python
@dataclass
class TranscriptionRequest:
    """Request for transcription"""
    id: str  # unique request ID
    user_id: int
    file_path: Path
    duration_seconds: int
    context: TranscriptionContext
    status_message: Message  # Telegram message for updates

@dataclass
class TranscriptionResponse:
    """Response from transcription"""
    request_id: str
    result: TranscriptionResult | None
    error: str | None

class QueueManager:
    """Manages transcription queue with concurrency control"""

    def __init__(
        self,
        max_queue_size: int = 50,
        max_concurrent: int = 1,
    ):
        self._queue: asyncio.Queue[TranscriptionRequest] = asyncio.Queue(maxsize=max_queue_size)
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
        self._results: dict[str, TranscriptionResponse] = {}
        self._processing: set[str] = set()
        self._worker_task: asyncio.Task | None = None

    async def enqueue(self, request: TranscriptionRequest) -> int:
        """Add request to queue, return position"""
        await self._queue.put(request)
        return self._queue.qsize()

    async def start_worker(self, callback: Callable):
        """Start background worker to process queue"""
        self._worker_task = asyncio.create_task(self._process_queue(callback))

    async def _process_queue(self, callback: Callable):
        """Process queue with concurrency limit"""
        while True:
            request = await self._queue.get()
            async with self._semaphore:
                self._processing.add(request.id)
                try:
                    result = await callback(request)
                    self._results[request.id] = TranscriptionResponse(
                        request_id=request.id,
                        result=result,
                        error=None,
                    )
                except Exception as e:
                    self._results[request.id] = TranscriptionResponse(
                        request_id=request.id,
                        result=None,
                        error=str(e),
                    )
                finally:
                    self._processing.remove(request.id)
                    self._queue.task_done()

    def get_queue_depth(self) -> int:
        """Get current queue size"""
        return self._queue.qsize()

    def get_position(self, request_id: str) -> int:
        """Get position in queue for request"""
        # Implementation: track positions
        pass

    async def wait_for_result(self, request_id: str, timeout: int = 300) -> TranscriptionResponse:
        """Wait for transcription result"""
        # Poll self._results until result available or timeout
        pass
```

**Files**:
- `src/services/queue_manager.py` (new)
- `tests/unit/test_queue_manager.py` (new)

**Success Criteria**:
- ✅ Queue enforces max_queue_size
- ✅ Semaphore limits concurrent processing
- ✅ Results correctly stored and retrieved
- ✅ All unit tests pass (15+ test cases)

---

### Phase 3: Staged Database Writes (2 hours)

**Goal**: Track request lifecycle for analytics

**Stages**:

1. **Stage 1**: On file download
   ```python
   usage = await usage_repo.create(
       user_id=db_user.id,
       voice_file_id=voice.file_id,
       voice_duration_seconds=None,  # Not yet known
       created_at=datetime.utcnow(),
       updated_at=datetime.utcnow(),
   )
   ```

2. **Stage 2**: After file download
   ```python
   await usage_repo.update(
       usage_id=usage.id,
       voice_duration_seconds=duration_seconds,
       updated_at=datetime.utcnow(),
   )
   ```

3. **Stage 3**: After transcription
   ```python
   await usage_repo.update(
       usage_id=usage.id,
       model_size=result.model_name,
       processing_time_seconds=result.processing_time,
       transcription_length=len(result.text),
       updated_at=datetime.utcnow(),
   )
   ```

**Benefits**:
- Track failed downloads (Stage 1 only)
- Track failed transcriptions (Stage 1-2 only)
- Calculate real processing times (Stage 3 - Stage 2)
- Privacy: no transcription text stored

**Files**:
- `src/storage/repositories.py` (modify: add update methods)
- `src/bot/handlers.py` (modify: staged writes)

---

### Phase 4: Smart Progress Bar (2-3 hours)

**Goal**: Live progress updates every 5 seconds

**Implementation**:

```python
class ProgressTracker:
    """Tracks and displays transcription progress"""

    def __init__(
        self,
        message: Message,
        duration_seconds: int,
        rtf: float = 0.3,
        update_interval: int = 5,
    ):
        self.message = message
        self.duration_seconds = duration_seconds
        self.estimated_total = duration_seconds * rtf
        self.start_time = time.time()
        self.update_interval = update_interval
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start progress updates"""
        self._task = asyncio.create_task(self._update_loop())

    async def stop(self):
        """Stop progress updates"""
        if self._task:
            self._task.cancel()

    async def _update_loop(self):
        """Update progress every N seconds"""
        while True:
            await asyncio.sleep(self.update_interval)
            elapsed = time.time() - self.start_time
            progress_pct = min(int(elapsed / self.estimated_total * 100), 99)
            remaining = max(int(self.estimated_total - elapsed), 0)

            # Generate progress bar
            bar = self._generate_bar(progress_pct)

            text = (
                f"🔄 Обработка {bar} {progress_pct}%\n"
                f"⏱️ Прошло: {int(elapsed)}с | Осталось: ~{remaining}с"
            )

            try:
                await self.message.edit_text(text)
            except Exception as e:
                logger.warning(f"Failed to update progress: {e}")

    def _generate_bar(self, percent: int) -> str:
        """Generate visual progress bar"""
        filled = int(percent / 5)  # 20 blocks (5% each)
        empty = 20 - filled
        return f"[{'█' * filled}{'░' * empty}]"
```

**Usage in handler**:
```python
# Start progress tracking
progress = ProgressTracker(
    message=processing_msg,
    duration_seconds=duration_seconds,
)
await progress.start()

try:
    # Run transcription
    result = await transcription_router.transcribe(file_path, context)
finally:
    await progress.stop()

# Show final result
await processing_msg.edit_text(f"✅ Готово!\n\n{result.text[:200]}...")
```

**Files**:
- `src/services/progress_tracker.py` (new)
- `src/bot/handlers.py` (integrate progress tracker)
- `tests/unit/test_progress_tracker.py` (new)

**Success Criteria**:
- ✅ Progress updates every 5 seconds
- ✅ Visual bar shows incremental progress
- ✅ Time estimates reasonably accurate
- ✅ Handles early completion gracefully

---

### Phase 5: Duration Validation & Queue Integration (2 hours)

**Goal**: Integrate all components into bot handlers

**Changes to `src/bot/handlers.py`**:

```python
class BotHandlers:
    def __init__(
        self,
        whisper_service: TranscriptionRouter,
        audio_handler: AudioHandler,
        queue_manager: QueueManager,
    ):
        self.transcription_router = whisper_service
        self.audio_handler = audio_handler
        self.queue_manager = queue_manager

        # Start queue worker
        asyncio.create_task(
            self.queue_manager.start_worker(self._process_transcription)
        )

    async def voice_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages with queue"""

        # ... user and voice validation ...

        # 1. Validate duration
        if duration_seconds > settings.max_voice_duration_seconds:
            await update.message.reply_text(
                f"⚠️ Максимальная длительность: {settings.max_voice_duration_seconds}с "
                f"({settings.max_voice_duration_seconds // 60} мин)\n"
                f"Ваш файл: {duration_seconds}с ({duration_seconds // 60} мин)"
            )
            return

        # 2. Check queue capacity
        queue_depth = self.queue_manager.get_queue_depth()
        if queue_depth >= settings.max_queue_size:
            await update.message.reply_text(
                "⚠️ Очередь переполнена. Пожалуйста, попробуйте через несколько минут."
            )
            return

        # 3. Send initial status
        status_msg = await update.message.reply_text("📥 Загружаю файл...")

        # 4. Download file
        voice_file = await context.bot.get_file(voice.file_id)
        file_path = await self.audio_handler.download_voice_message(
            voice_file, voice.file_id
        )

        # 5. Create usage record (Stage 1)
        async with get_session() as session:
            usage_repo = UsageRepository(session)
            usage = await usage_repo.create(
                user_id=db_user.id,
                voice_file_id=voice.file_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            # Update with duration (Stage 2)
            await usage_repo.update(
                usage_id=usage.id,
                voice_duration_seconds=duration_seconds,
                updated_at=datetime.utcnow(),
            )

        # 6. Create transcription request
        request = TranscriptionRequest(
            id=str(uuid.uuid4()),
            user_id=user.id,
            file_path=file_path,
            duration_seconds=duration_seconds,
            context=transcription_context,
            status_message=status_msg,
            usage_id=usage.id,
        )

        # 7. Enqueue request
        position = await self.queue_manager.enqueue(request)

        if position > 1:
            await status_msg.edit_text(
                f"📋 В очереди: позиция {position}\n"
                f"⏱️ Примерное время ожидания: ~{(position - 1) * 20}с"
            )
        else:
            await status_msg.edit_text("⚙️ Начинаю обработку...")

        # 8. Wait for result (non-blocking for handler)
        # Result will be processed in _process_transcription callback

    async def _process_transcription(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Process transcription (called by queue worker)"""

        # Update status
        await request.status_message.edit_text("⚙️ Начинаю обработку...")

        # Start progress tracker
        progress = ProgressTracker(
            message=request.status_message,
            duration_seconds=request.duration_seconds,
        )
        await progress.start()

        try:
            # Transcribe
            result = await self.transcription_router.transcribe(
                request.file_path,
                request.context,
            )

            # Stop progress
            await progress.stop()

            # Update database (Stage 3)
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=request.usage_id,
                    model_size=result.model_name,
                    processing_time_seconds=result.processing_time,
                    transcription_length=len(result.text),
                    updated_at=datetime.utcnow(),
                )

            # Send result
            await request.status_message.edit_text(f"✅ Готово!\n\n{result.text}")

            # Cleanup
            self.audio_handler.cleanup_file(request.file_path)

            return result

        except Exception as e:
            await progress.stop()
            logger.error(f"Transcription failed: {e}", exc_info=True)
            await request.status_message.edit_text(
                "❌ Произошла ошибка при обработке. Пожалуйста, попробуйте еще раз."
            )
            self.audio_handler.cleanup_file(request.file_path)
            raise
```

**Configuration Updates** (`src/config.py`):
```python
# Queue settings
max_queue_size: int = Field(default=50, description="Maximum queue size")
max_concurrent_workers: int = Field(default=1, description="Max concurrent transcriptions")

# Duration limits
max_voice_duration_seconds: int = Field(
    default=120,  # Changed from 300 to 120
    description="Maximum voice message duration (2 minutes)",
)
```

**Files**:
- `src/bot/handlers.py` (major refactor)
- `src/config.py` (update defaults)
- `src/main.py` (initialize queue_manager)

---

### Phase 6: Testing (3-4 hours)

**Unit Tests**:
- `test_queue_manager.py`: Queue operations, concurrency, overflow
- `test_progress_tracker.py`: Progress calculation, bar generation, updates
- `test_repositories.py`: Update methods, staged writes

**Integration Tests**:
- `test_concurrent_requests.py`: 3 simultaneous requests, queue ordering
- `test_duration_validation.py`: Reject long files, accept valid files
- `test_queue_overflow.py`: Handle full queue gracefully

**Manual Testing**:
1. Single 60s audio → verify progress bar updates
2. Single 130s audio → verify rejection
3. 3 concurrent 30s audios → verify queue positions
4. 5 concurrent 60s audios → verify sequential processing
5. Database records → verify staged writes (created_at, updated_at)

**Load Testing**:
```bash
# Simulate 10 concurrent users
python scripts/load_test.py --users 10 --duration 30
```

**Success Criteria**:
- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ Bot handles 10 concurrent requests without crash
- ✅ CPU usage stays under 90%
- ✅ Memory usage stays under 2GB
- ✅ Users see clear feedback at all stages

---

## Risk Assessment

### High Risks

**Risk 1: Queue deadlock**
- **Mitigation**: Timeout on each transcription (120s max)
- **Monitoring**: Log queue depth, processing times

**Risk 2: Message edit rate limits (Telegram)**
- **Mitigation**: Respect 5-second minimum interval between edits
- **Fallback**: Skip update if rate limited

**Risk 3: Database connection pool exhaustion**
- **Mitigation**: Use context managers, proper session cleanup
- **Monitoring**: Track open connections

### Medium Risks

**Risk 4: Memory leak with long-running queue**
- **Mitigation**: Bounded queue size, cleanup completed requests
- **Monitoring**: Track _results dict size

**Risk 5: Progress estimation inaccuracy**
- **Mitigation**: Use actual RTF from benchmarks (0.3x)
- **Accept**: Some variance expected

## Rollback Plan

If production issues:

1. **Immediate** (< 5 min): Revert to main branch
2. **Short-term** (< 1 hour): Analyze logs, identify root cause
3. **Medium-term** (< 4 hours): Fix issue, redeploy
4. **Fallback**: Keep reverted if unfixable

## Success Metrics

**Must Have**:
- ✅ Zero crashes under concurrent load (5+ users)
- ✅ Duration limit enforced (reject >120s)
- ✅ Progress bar updates every 5s
- ✅ Users see queue positions
- ✅ 95%+ success rate

**Nice to Have**:
- ⭐ Average wait time < 30s for short files
- ⭐ Queue depth rarely exceeds 10
- ⭐ Database analytics enable insights

## Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| 1. DB Migration | 1-2 hours | None |
| 2. Queue Manager | 4-5 hours | Phase 1 |
| 3. Staged DB Writes | 2 hours | Phase 1, 2 |
| 4. Progress Bar | 2-3 hours | Phase 2 |
| 5. Integration | 2 hours | Phase 2, 3, 4 |
| 6. Testing | 3-4 hours | All phases |
| **Total** | **14-18 hours** | |

**Estimated Calendar Time**: 2 days

## Implementation Notes

- Use feature branch: `claude/optimize-bot-performance-011CUbRo6dFSvNks9ZkKv7e7`
- Commit incrementally after each phase
- Run tests before each commit
- Update Memory Bank after completion

## Approved Configuration

✅ **Hardware**: 2 CPU / 2 GB RAM (no change)
✅ **Concurrency**: max_concurrent = 1
✅ **Progress Bar**: Variant 2 (visual bar with emoji)
✅ **Privacy**: Replace transcription_text with transcription_length
✅ **Duration Limit**: max_voice_duration_seconds = 120
✅ **Draft Mode**: Not implemented (performance overhead)

---

**Status**: Ready for implementation
**Next Step**: Execute via `/workflow:execute`
