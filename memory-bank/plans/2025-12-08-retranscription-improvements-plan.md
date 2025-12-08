# Retranscription Improvements Plan

**Date**: 2025-12-08
**Status**: Approved
**Estimated Time**: 4-6 hours

## Problem Statement

After implementing interactive transcription mode with buttons (Phase 10), the retranscription logic has issues:

1. **No Progress Bar**: Users don't see how long retranscription will take
   - Free method uses better model (medium, RTF 0.5)
   - Paid method uses OpenAI (fast, ~30s fixed)

2. **Statistics Lost**: Usage record is overwritten, losing original transcription data
   - Can't track retranscription history
   - Analytics limited (no parent-child relationship)

3. **Refinement Not Disabled**: Retranscription might run refinement unnecessarily
   - Wastes time since we're already using good model
   - Should use single-mode processing

## Selected Approach

**Option 1: Progress Bar + Parent-Child Usage Tracking**

Preserves complete history with parent-child relationships in usage table.

## Technical Implementation

### 1. Database Migration

**File**: `alembic/versions/{timestamp}_add_parent_usage_id.py`

Add `parent_usage_id` column to `usage` table:
```python
def upgrade():
    op.add_column('usage',
        sa.Column('parent_usage_id', sa.Integer(), nullable=True)
    )
    op.create_index('ix_usage_parent_usage_id', 'usage', ['parent_usage_id'])
    op.create_foreign_key(
        'fk_usage_parent_usage_id', 'usage', 'usage',
        ['parent_usage_id'], ['id'], ondelete='CASCADE'
    )

def downgrade():
    op.drop_constraint('fk_usage_parent_usage_id', 'usage')
    op.drop_index('ix_usage_parent_usage_id', 'usage')
    op.drop_column('usage', 'parent_usage_id')
```

### 2. Update Usage Model

**File**: `src/storage/models.py:59-117`

Add parent_usage_id field:
```python
class Usage(Base):
    # ... existing fields ...

    # Retranscription support (Phase 8)
    original_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    parent_usage_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usage.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # ... relationships ...
```

### 3. Update UsageRepository

**File**: `src/storage/repositories.py:124-159`

Add parent_usage_id parameter to create():
```python
async def create(
    self,
    user_id: int,
    voice_file_id: str,
    voice_duration_seconds: Optional[int] = None,
    model_size: Optional[str] = None,
    processing_time_seconds: Optional[float] = None,
    transcription_length: Optional[int] = None,
    language: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_processing_time_seconds: Optional[float] = None,
    parent_usage_id: Optional[int] = None,  # NEW
) -> Usage:
```

### 4. Add disable_refinement to TranscriptionContext

**File**: `src/transcription/models.py`

Add optional parameter:
```python
@dataclass
class TranscriptionContext:
    language: str = "ru"
    provider_preference: Optional[str] = None
    disable_refinement: bool = False  # NEW
```

**File**: `src/transcription/router.py`

Respect disable_refinement flag in routing logic:
```python
async def transcribe(...):
    # ... existing code ...

    # Skip refinement if disabled
    if context.disable_refinement:
        # Return result without refinement
        return result

    # ... existing refinement logic ...
```

### 5. Implement Progress Bar in Retranscribe Handler

**File**: `src/bot/retranscribe_handlers.py:108-289`

**Changes at line 188-207** (configure transcription context):
```python
# Configure transcription context based on method
if method == "free":
    provider_name = f"faster-whisper-{settings.retranscribe_free_model}"
    transcription_context = TranscriptionContext(
        language="ru",
        provider_preference=provider_name,
        disable_refinement=True,  # NEW: Skip refinement
    )
    # Calculate progress duration based on RTF
    progress_duration = int(usage.voice_duration_seconds * settings.retranscribe_free_model_rtf)
else:
    transcription_context = TranscriptionContext(
        language="ru",
        provider_preference=settings.retranscribe_paid_provider,
        disable_refinement=True,  # NEW: Skip refinement
    )
    # Use fixed duration for paid method
    progress_duration = settings.llm_processing_duration
```

**Insert before line 208** (start progress tracker):
```python
# Start progress tracker
progress = ProgressTracker(
    message=cast(Message, query.message),
    duration_seconds=progress_duration,
    rtf=1.0,  # Duration already calculated above
    update_interval=settings.progress_update_interval,
)
await progress.start()

logger.info(
    f"Progress tracker started: duration={progress_duration}s, method={method}"
)
```

**Update line 208-215** (perform retranscription):
```python
# Perform retranscription
try:
    result = await bot_handlers.transcription_router.transcribe(
        audio_path,
        transcription_context,
    )

    # Stop progress tracker
    await progress.stop()

    logger.info(...)
except Exception as e:
    # Stop progress tracker on error
    await progress.stop()
    logger.error(...)
    # ... existing error handling ...
```

### 6. Implement Parent-Child Usage Record Creation

**File**: `src/bot/retranscribe_handlers.py:221-230`

Replace update logic with create child record:
```python
# Create child usage record (preserves original)
async with get_session() as session:
    usage_repo = UsageRepository(session)

    # Create child usage record
    child_usage = await usage_repo.create(
        user_id=usage.user_id,
        voice_file_id=usage.voice_file_id,
        voice_duration_seconds=usage.voice_duration_seconds,
        model_size=result.model_name or result.provider_used,
        processing_time_seconds=result.processing_time,
        transcription_length=len(result.text),
        language="ru",
        parent_usage_id=usage_id,  # Link to parent
        original_file_path=usage.original_file_path,  # Preserve file path
    )

    logger.info(
        f"Created child usage record: child_id={child_usage.id}, "
        f"parent_id={usage_id}, method={method}"
    )

    # Update state to point to new child usage
    state_repo = TranscriptionStateRepository(session)
    state = await state_repo.get_by_usage_id(usage_id)
    if state:
        state.usage_id = child_usage.id
        await state_repo.update(state)
        logger.info(f"Updated state.usage_id: {usage_id} -> {child_usage.id}")

    await session.commit()

    # Update usage_id variable for subsequent code
    usage_id = child_usage.id
```

### 7. Update Subsequent Code References

**File**: `src/bot/retranscribe_handlers.py:236-289`

All subsequent references to `usage_id` now correctly point to child_usage.id due to variable reassignment.

## Edge Cases & Mitigations

### 1. Multiple Retranscriptions
- **Behavior**: Creates chain (original → child1 → child2)
- **Implementation**: Each retranscription sets previous child as parent

### 2. State Management After Retranscription
- **Risk**: Other code might rely on state.usage_id staying constant
- **Mitigation**: Comprehensive testing of all interactive features
- **Test cases**:
  - Retranscribe → change mode (original/structured/summary)
  - Retranscribe → adjust length (shorter/longer)
  - Retranscribe → toggle emoji
  - Retranscribe → toggle timestamps

### 3. Orphaned Children
- **Solution**: CASCADE delete on foreign key
- **Behavior**: If parent usage deleted, children are also deleted

### 4. Progress Bar Accuracy
- **Free method**: RTF 0.5 is estimate, actual time may vary
- **Paid method**: Fixed 30s is estimate, OpenAI might be faster/slower
- **Mitigation**: Progress bar shows "~" (approximately) in estimates

### 5. Concurrent Retranscriptions
- **Risk**: User clicks retranscribe multiple times quickly
- **Current mitigation**: Button is in callback, only one callback at a time
- **Future enhancement**: Add explicit locking if needed

### 6. Segments and Variants Cleanup
- **Current**: Code deletes old variants/segments before retranscription (lines 164-186)
- **Impact**: This still works correctly, uses original usage_id
- **Note**: After state.usage_id update, new variants will link to child_usage

## Validation Steps

### Functional Testing
1. Test free retranscription:
   - [ ] Progress bar appears with realistic time estimate
   - [ ] Progress updates every 5 seconds
   - [ ] Retranscription completes successfully
   - [ ] Original usage record preserved in database
   - [ ] Child usage record created with parent_usage_id

2. Test paid retranscription:
   - [ ] Progress bar shows fixed 30s duration
   - [ ] OpenAI retranscription completes
   - [ ] Parent-child relationship correct

3. Test interactive modes after retranscription:
   - [ ] Switch to structured mode (generates new variant)
   - [ ] Switch back to original mode (works correctly)
   - [ ] Adjust length (shorter/longer)
   - [ ] Toggle emoji (add/remove)
   - [ ] Toggle timestamps (if segments exist)

4. Test multiple retranscriptions:
   - [ ] Retranscribe twice (creates chain: original → child1 → child2)
   - [ ] Database shows correct parent_usage_id chain
   - [ ] State.usage_id points to latest child

### Database Testing
5. Verify database structure:
   - [ ] parent_usage_id column exists
   - [ ] Index created on parent_usage_id
   - [ ] Foreign key constraint with CASCADE delete
   - [ ] Query parent-child relationships works

6. Test analytics queries:
   ```sql
   -- Count retranscriptions per user
   SELECT user_id, COUNT(*)
   FROM usage
   WHERE parent_usage_id IS NOT NULL
   GROUP BY user_id;

   -- Find retranscription chains
   SELECT u1.id as original_id, u2.id as child_id, u2.model_size
   FROM usage u1
   LEFT JOIN usage u2 ON u2.parent_usage_id = u1.id
   WHERE u1.parent_usage_id IS NULL;
   ```

### Error Handling Testing
7. Test error scenarios:
   - [ ] Network error during retranscription (progress bar stops)
   - [ ] OpenAI API error (paid method fails gracefully)
   - [ ] File not found error (audio deleted)

## Rollback Plan

If issues arise:

1. **Database rollback**:
   ```bash
   alembic downgrade -1
   ```

2. **Code rollback**:
   - Revert changes to retranscribe_handlers.py
   - Revert changes to models.py
   - Revert changes to repositories.py

3. **Disable feature**:
   ```bash
   ENABLE_RETRANSCRIBE=false
   ```

## Success Criteria

- ✅ Progress bar visible during retranscription
- ✅ Original usage statistics preserved
- ✅ Child usage record created with parent_usage_id
- ✅ All interactive modes work after retranscription
- ✅ No breaking changes to existing functionality
- ✅ Database migration successful

## Future Enhancements

1. **Retranscription History UI**: Show user their retranscription history
2. **Analytics Dashboard**: Track retranscription usage patterns
3. **Cost Tracking**: Track paid retranscription costs per user
4. **Optimization**: Cache retranscriptions to avoid duplicate processing
