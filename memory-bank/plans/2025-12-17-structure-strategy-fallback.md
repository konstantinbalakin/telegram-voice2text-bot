# Plan: Add Fallback Support to StructureStrategy

**Date**: 2025-12-17
**Status**: Approved
**Complexity**: Low
**Estimated Time**: 30-45 minutes

## Problem Statement

StructureStrategy does not support automatic fallback to alternative provider when primary provider fails. This caused user request failure when OpenAI rejected 31-minute audio (1885s > 1400s limit) despite having faster-whisper available as backup.

**Error from logs** (2025-12-17_01-50-36/app.log:90-92):
```
OpenAI API error: audio duration 1885.851812 seconds is longer than 1400 seconds
which is the maximum for this model
```

Router attempted fallback check but StructureStrategy returned `supports_fallback() = False`.

## Current State

- ✅ Router has fallback logic (router.py:146-165)
- ✅ Both providers enabled (openai + faster-whisper)
- ❌ StructureStrategy doesn't implement `supports_fallback()` / `get_fallback()`
- ❌ Factory doesn't pass fallback provider to StructureStrategy

**Reference implementation**: FallbackStrategy (strategies.py:104-140) shows correct pattern.

## Selected Approach: Automatic Fallback Detection

**Strategy**: StructureStrategy auto-detects fallback provider from available providers.

**Logic**:
- If primary = openai → fallback = faster-whisper (if available)
- If primary = faster-whisper → fallback = None (local model shouldn't fail)

## Implementation Plan

### 1. Update StructureStrategy (strategies.py)

**Changes**:
```python
# Add optional fallback parameter to __init__
def __init__(
    self,
    provider_name: str,
    model: str,
    draft_threshold_seconds: int = 20,
    emoji_level: int = 1,
    fallback_provider_name: Optional[str] = None,  # NEW
):
    self.fallback_provider = fallback_provider_name  # NEW

# Override base class methods
def supports_fallback(self) -> bool:
    return bool(self.fallback_provider)

async def get_fallback(self, failed_provider: str) -> Optional[str]:
    if failed_provider == self.provider_name:
        return self.fallback_provider
    return None
```

### 2. Update Factory (factory.py)

**Changes in structure strategy creation block** (~line 390):
```python
# Auto-detect fallback provider
fallback_provider = None
if provider_name == "openai" and "faster-whisper" in providers:
    fallback_provider = "faster-whisper"
    logger.info(f"✓ Fallback configured: {fallback_provider}")

strategy = StructureStrategy(
    provider_name=provider_name,
    model=model_name,
    draft_threshold_seconds=settings.structure_draft_threshold,
    emoji_level=settings.structure_emoji_level,
    fallback_provider_name=fallback_provider,  # NEW
)
```

### 3. Update Tests (test_structure_strategy.py)

**New test cases**:
- `test_structure_strategy_supports_fallback_when_configured`
- `test_structure_strategy_no_fallback_by_default`
- `test_structure_strategy_get_fallback_returns_configured_provider`
- `test_structure_strategy_get_fallback_returns_none_for_different_provider`

## Edge Cases Handled

1. **Fallback provider unavailable**: Router checks `if fallback_name in providers` (router.py:149)
2. **Both providers fail**: Router logs fallback error and raises original exception (router.py:161-165)
3. **No fallback needed**: `fallback_provider = None` → `supports_fallback()` returns False
4. **Different provider models**: Each provider uses its own configuration independently
5. **Backward compatibility**: Optional parameter ensures existing code works unchanged

## Success Criteria

- ✅ All existing tests pass without modifications
- ✅ New fallback tests pass
- ✅ OpenAI errors (>1400s audio) automatically fallback to faster-whisper
- ✅ faster-whisper primary strategy continues without fallback (fallback=None)
- ✅ Backward compatible with existing configurations

## Risk Mitigation

- **Low risk**: Isolated change, optional parameter
- **No performance impact**: Fallback only triggers on error
- **Backward compatible**: Existing code without fallback continues working
- **Pattern consistency**: Follows FallbackStrategy implementation pattern

## Files Modified

1. `src/transcription/routing/strategies.py` - StructureStrategy class
2. `src/transcription/factory.py` - create_transcription_router() function
3. `tests/unit/test_structure_strategy.py` - Add fallback test cases

## Validation Steps

1. Run unit tests: `poetry run pytest tests/unit/test_structure_strategy.py -v`
2. Run full test suite: `poetry run pytest tests/unit/ -v`
3. Manual test with long audio (>1400s) to verify fallback behavior
4. Check logs for fallback messages

## Related Issues

- Resolves: User audio >1400s failing with OpenAI
- Improves: System reliability and provider flexibility
- Aligns with: Existing fallback pattern in FallbackStrategy
