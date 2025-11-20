# Quick Implementation Checklist

**Feature**: Hybrid Transcription Acceleration
**Date**: 2025-11-20
**Estimated Time**: 3-4 days

## Pre-Implementation

- [ ] Review full plan: `memory-bank/plans/2025-11-20-hybrid-transcription-acceleration.md`
- [ ] Create feature branch: `git checkout -b feature/hybrid-transcription`
- [ ] Verify current VPS config: 4 CPU + 3GB RAM ✅
- [ ] Note: DeepSeek API key will be added later (OK to test without LLM first)

---

## Day 1: LLM Service

### Files to Create
- [ ] `src/services/llm_service.py` (~250 lines)
  - [ ] `LLMProvider` (ABC)
  - [ ] `DeepSeekProvider` (implementation)
  - [ ] `LLMFactory` (factory)
  - [ ] `LLMService` (high-level interface)
  - [ ] Error classes: `LLMError`, `LLMTimeoutError`, `LLMAPIError`

### Configuration
- [ ] Add to `src/config.py`:
  - [ ] `llm_refinement_enabled: bool = False`
  - [ ] `llm_provider: str = "deepseek"`
  - [ ] `llm_api_key: str | None = None`
  - [ ] `llm_model: str = "deepseek-chat"`
  - [ ] `llm_base_url: str = "https://api.deepseek.com"`
  - [ ] `llm_refinement_prompt: str = "..."`
  - [ ] `llm_timeout: int = 30`

### Dependencies
- [ ] Add to `pyproject.toml`: `tenacity = "^9.0.0"`
- [ ] Run: `poetry install`

### Tests
- [ ] Create `tests/unit/test_llm_service.py` (~150 lines)
  - [ ] Test DeepSeekProvider with mocked API
  - [ ] Test timeout handling
  - [ ] Test API error handling
  - [ ] Test retry logic
  - [ ] Test LLMService fallback

### Commit
- [ ] `git add src/services/llm_service.py src/config.py pyproject.toml tests/unit/test_llm_service.py`
- [ ] `git commit -m "feat: add LLM service for text refinement"`
- [ ] `git push origin feature/hybrid-transcription`

---

## Day 2: Hybrid Strategy & Preprocessing

### Hybrid Strategy
- [ ] Add to `src/transcription/routing/strategies.py` (+150 lines)
  - [ ] `HybridStrategy` class
  - [ ] `select_provider()` method (duration-based)
  - [ ] `get_model_for_duration()` helper
  - [ ] `requires_refinement()` check

### Audio Preprocessing
- [ ] Add to `src/transcription/audio_handler.py` (+120 lines)
  - [ ] `preprocess_audio()` method (pipeline)
  - [ ] `_convert_to_mono()` helper (ffmpeg)
  - [ ] `_adjust_speed()` helper (ffmpeg)

### Configuration
- [ ] Add to `src/config.py`:
  - [ ] Hybrid: `hybrid_short_threshold`, `hybrid_draft_provider`, `hybrid_draft_model`, `hybrid_quality_provider`, `hybrid_quality_model`
  - [ ] Audio: `audio_convert_to_mono`, `audio_target_sample_rate`, `audio_speed_multiplier`

### Docker
- [ ] Verify ffmpeg in `Dockerfile` (should be there already)
- [ ] If missing: `RUN apt-get install -y ffmpeg`

### Tests
- [ ] Create `tests/unit/test_hybrid_strategy.py` (~200 lines)
  - [ ] Test short audio routing (quality model)
  - [ ] Test long audio routing (draft model)
  - [ ] Test threshold boundary
  - [ ] Test refinement requirement
- [ ] Create `tests/unit/test_audio_preprocessing.py` (~100 lines)
  - [ ] Test mono conversion
  - [ ] Test speed adjustment
  - [ ] Test pipeline (both)
  - [ ] Test error handling

### Commit
- [ ] `git add src/transcription/routing/strategies.py src/transcription/audio_handler.py src/config.py tests/unit/test_*.py`
- [ ] `git commit -m "feat: add hybrid strategy and audio preprocessing"`
- [ ] `git push`

---

## Day 3: Handler Integration

### Handler Updates
- [ ] Modify `src/bot/handlers.py` (voice_message_handler)
  - [ ] Call `preprocess_audio()` before transcription
  - [ ] Detect hybrid strategy: `isinstance(..., HybridStrategy)`
  - [ ] Check refinement needed: `strategy.requires_refinement(duration)`
  - [ ] Staged messages:
    - [ ] Send draft: `✅ Черновик готов:\n\n{text}\n\n🔄 Улучшаю текст...`
    - [ ] Refine with LLM: `await llm_service.refine_transcription(draft)`
    - [ ] Send final: `✨ Готово!\n\n{refined}`
  - [ ] Fallback: if LLM fails → `draft is final`
  - [ ] Update usage record with final text length

### Handler Constructor
- [ ] Add parameter: `llm_service: Optional[LLMService] = None`
- [ ] Store: `self.llm_service = llm_service`

### Main Initialization
- [ ] Modify `src/main.py`
  - [ ] Create LLM service:
    ```python
    llm_service = None
    if settings.llm_refinement_enabled:
        llm_provider = LLMFactory.create_provider(settings)
        if llm_provider:
            llm_service = LLMService(llm_provider, settings.llm_refinement_prompt)
    ```
  - [ ] Create strategy based on `whisper_routing_strategy`:
    ```python
    if settings.whisper_routing_strategy == "hybrid":
        strategy = HybridStrategy(
            short_threshold=settings.hybrid_short_threshold,
            draft_provider_name=settings.hybrid_draft_provider,
            draft_model=settings.hybrid_draft_model,
            quality_provider_name=settings.hybrid_quality_provider,
            quality_model=settings.hybrid_quality_model,
        )
    ```
  - [ ] Pass llm_service to handlers

### Tests
- [ ] Create `tests/integration/test_hybrid_flow.py` (~200 lines)
  - [ ] Test short audio (no refinement)
  - [ ] Test long audio (with refinement)
  - [ ] Test LLM failure fallback
  - [ ] Test preprocessing integration

### Commit
- [ ] `git add src/bot/handlers.py src/main.py tests/integration/test_hybrid_flow.py`
- [ ] `git commit -m "feat: integrate hybrid strategy into handlers"`
- [ ] `git push`

---

## Day 4: Testing & Documentation

### Testing
- [ ] Run all unit tests: `poetry run pytest tests/unit/ -v`
- [ ] Run integration tests: `poetry run pytest tests/integration/ -v`
- [ ] Run code quality: `poetry run black src/ tests/`
- [ ] Run linting: `poetry run ruff check src/`
- [ ] Run type checking: `poetry run mypy src/`

### Manual Testing (Conservative Mode)
- [ ] Set environment:
  ```bash
  WHISPER_ROUTING_STRATEGY=hybrid
  HYBRID_SHORT_THRESHOLD=20
  HYBRID_DRAFT_MODEL=small
  LLM_REFINEMENT_ENABLED=false
  AUDIO_SPEED_MULTIPLIER=1.0
  ```
- [ ] Test short audio (<20s): Should use medium model
- [ ] Test long audio (≥20s): Should use small model (faster)
- [ ] Verify speedup: compare processing times

### Manual Testing (With LLM - Later)
- [ ] Get DeepSeek API key from https://platform.deepseek.com/api_keys
- [ ] Set: `LLM_REFINEMENT_ENABLED=true`, `LLM_API_KEY=sk-...`
- [ ] Test long audio: verify draft → refined flow
- [ ] Check message updates work
- [ ] Verify refinement quality

### Manual Testing (Preprocessing)
- [ ] Test speed: `AUDIO_SPEED_MULTIPLIER=1.5`
  - [ ] Compare quality: 1.0x vs 1.5x vs 2.0x
- [ ] Test mono: `AUDIO_CONVERT_TO_MONO=true`
  - [ ] Compare quality with mono conversion

### Documentation
- [ ] `.env.example` - Already updated ✅
- [ ] Update `docs/getting-started/configuration.md`:
  - [ ] Add "Hybrid Transcription Strategy" section
  - [ ] Add "LLM Text Refinement" section
  - [ ] Add "Audio Preprocessing" section
  - [ ] Add usage examples
- [ ] Update `README.md`:
  - [ ] Features: Add hybrid mode
  - [ ] Performance: Update with speedup numbers
- [ ] Verify plan: `memory-bank/plans/2025-11-20-hybrid-transcription-acceleration.md` ✅

### Commit
- [ ] `git add docs/ README.md`
- [ ] `git commit -m "docs: add hybrid transcription documentation"`
- [ ] `git push`

---

## Pull Request

### Create PR
- [ ] `gh pr create --title "feat: hybrid transcription acceleration" --body "..."`
- [ ] PR body should include:
  - [ ] Summary of changes
  - [ ] Performance improvements (before/after)
  - [ ] Configuration examples
  - [ ] Testing notes
  - [ ] Screenshots of staged messages (if possible)

### Review
- [ ] Review all changed files
- [ ] Check tests passing
- [ ] Verify no regressions

### Merge
- [ ] Merge PR: `gh pr merge --squash`
- [ ] Delete feature branch: `git branch -d feature/hybrid-transcription`

---

## Deployment

### VPS Preparation
- [ ] SSH to VPS
- [ ] Pull latest code: `git pull origin main`
- [ ] Set environment variables (conservative):
  ```bash
  WHISPER_ROUTING_STRATEGY=hybrid
  HYBRID_SHORT_THRESHOLD=20
  HYBRID_DRAFT_MODEL=small
  LLM_REFINEMENT_ENABLED=false
  AUDIO_SPEED_MULTIPLIER=1.0
  ```
- [ ] Restart bot: `docker compose up -d --build`

### Verification
- [ ] Check logs: `docker logs telegram-voice2text-bot`
- [ ] Verify hybrid strategy loaded
- [ ] Test with real audio
- [ ] Monitor processing times

### Enable LLM (Later)
- [ ] Add DeepSeek API key to GitHub Secrets: `LLM_API_KEY`
- [ ] Update deployment config: `LLM_REFINEMENT_ENABLED=true`
- [ ] Redeploy
- [ ] Test refinement flow
- [ ] Monitor costs

### Enable Preprocessing (Optional)
- [ ] After testing quality impact:
  ```bash
  AUDIO_SPEED_MULTIPLIER=1.5
  # or
  AUDIO_CONVERT_TO_MONO=true
  ```

---

## Post-Deployment Monitoring

### Metrics to Watch
- [ ] Processing times (short vs long audio)
- [ ] Draft quality (manual inspection)
- [ ] Refinement quality (comparison)
- [ ] LLM API costs (token usage)
- [ ] Error rates (LLM failures, ffmpeg errors)
- [ ] User feedback

### Performance Validation
- [ ] 20s audio: ~12s (no change expected)
- [ ] 60s audio: ~6-8s (vs 36s before) = **6x faster**
- [ ] 120s audio: ~9-12s (vs 72s before) = **6-8x faster**

### Optimization Iteration
- [ ] Based on results, adjust:
  - [ ] Threshold (20s → ?)
  - [ ] Draft model (small → tiny/base?)
  - [ ] Speed multiplier (1.0 → 1.5 → ?)
  - [ ] Mono conversion (enable if quality OK)

---

## Troubleshooting Reference

### Common Issues

**"LLM refinement disabled (no API key)"**
- Add `LLM_API_KEY` to environment
- Verify `LLM_REFINEMENT_ENABLED=true`

**"ffmpeg: command not found"**
- Verify ffmpeg in Dockerfile
- Rebuild Docker image

**"DeepSeek timeout"**
- Check network connectivity
- Increase `LLM_TIMEOUT` (default 30s)

**"Unknown strategy: hybrid"**
- Verify `WHISPER_ROUTING_STRATEGY=hybrid`
- Check for typos

---

## Quick Commands

```bash
# Create branch
git checkout -b feature/hybrid-transcription

# Run tests
poetry run pytest tests/unit/ -v
poetry run pytest tests/integration/ -v

# Code quality
poetry run black src/ tests/
poetry run ruff check src/
poetry run mypy src/

# Commit pattern
git add <files>
git commit -m "feat: <description>"
git push

# Create PR
gh pr create --title "feat: hybrid transcription acceleration"

# Merge
gh pr merge --squash

# Deploy
docker compose up -d --build

# Check logs
docker logs telegram-voice2text-bot -f
```

---

## Quick Configuration Snippets

**Conservative (Start):**
```bash
WHISPER_ROUTING_STRATEGY=hybrid
HYBRID_SHORT_THRESHOLD=20
HYBRID_DRAFT_MODEL=small
LLM_REFINEMENT_ENABLED=false
AUDIO_SPEED_MULTIPLIER=1.0
```

**Full Hybrid (After Testing):**
```bash
WHISPER_ROUTING_STRATEGY=hybrid
LLM_REFINEMENT_ENABLED=true
LLM_API_KEY=sk-your-key
AUDIO_SPEED_MULTIPLIER=1.5
```

**Back to Original:**
```bash
WHISPER_ROUTING_STRATEGY=single
PRIMARY_PROVIDER=faster-whisper
FASTER_WHISPER_MODEL_SIZE=medium
```

---

**Ready to implement!** 🚀

Full details in: `memory-bank/plans/2025-11-20-hybrid-transcription-acceleration.md`
