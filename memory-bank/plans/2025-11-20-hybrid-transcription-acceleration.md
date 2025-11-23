# Implementation Plan: Hybrid Transcription Acceleration

**Date**: 2025-11-20
**Status**: Approved - Ready for Implementation
**Approach**: Option 3 (Balanced Approach)
**Estimated Time**: 3-4 days

## Executive Summary

Implement hybrid transcription strategy to dramatically reduce processing time for long audio files while maintaining quality. Achieve 6x-9x speedup (36s → 6s for 60s audio) through fast draft + LLM refinement approach.

**Key Features**:
- Duration-based routing (short: quality model, long: draft → LLM refinement)
- Selectable draft provider (faster-whisper OR openai)
- DeepSeek LLM integration for text refinement
- Audio preprocessing (mono conversion + speed adjustment)
- Staged message updates (draft → refining → final)

## Architecture Decision

**Selected**: Option 3 (Сбалансированный подход)

**Rationale**:
- ✅ Fully meets requirements (draft provider selection)
- ✅ Extensible architecture (easy to add new LLM providers)
- ✅ Reasonable complexity (not over-engineered)
- ✅ 3-4 day timeline (realistic)
- ✅ Follows existing project patterns

**Alternative Options Considered**:
- Option 1 (Minimal): Too limited, no draft provider selection
- Option 2 (Enterprise): Over-engineered for current needs

## Technical Specifications

### Current State

**VPS Configuration**:
- CPU: 4 cores
- RAM: 3GB
- Current RTF: 0.6x (medium model)
- Processing time for 60s audio: ~36 seconds

**Existing Architecture**:
- Routing strategies: Single, Fallback, Benchmark
- Providers: faster-whisper, openai
- Queue-based processing with progress tracking

### Target State

**Performance Goals**:
- Short audio (<20s): No change (~12s for 20s audio)
- Long audio (≥20s): 6x-9x faster
  - 60s audio: 36s → ~6s (draft in 3s, final in 6s)
  - 120s audio: 72s → ~9s
  - 300s audio: 180s → ~20s

**User Experience**:
```
Short audio (<20s):
  📥 Загружаю...
  🔄 Обработка...
  ✅ Готово! [text]

Long audio (≥20s):
  📥 Загружаю...
  🔄 Обработка...
  ✅ Черновик готов:
     [draft text with potential errors]

     🔄 Улучшаю текст...

  ✨ Готово!
     [refined text, corrected]
```

## Implementation Phases

### Phase 1: LLM Service Infrastructure (Day 1)

**Goal**: Create extensible LLM service with DeepSeek provider

#### Files to Create

**`src/services/llm_service.py`** (~250 lines)

```python
"""LLM service for text refinement."""

import logging
from abc import ABC, abstractmethod
from typing import Optional
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import Settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def refine_text(self, text: str, prompt: str) -> str:
        """
        Refine transcribed text.

        Args:
            text: Draft transcription text
            prompt: System prompt for refinement

        Returns:
            Refined text

        Raises:
            LLMError: If refinement fails
        """
        pass

    @abstractmethod
    async def close(self):
        """Cleanup resources."""
        pass


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timeout."""
    pass


class LLMAPIError(LLMError):
    """LLM API error."""
    pass


class DeepSeekProvider(LLMProvider):
    """DeepSeek V3 provider for text refinement."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 30,
    ):
        """
        Initialize DeepSeek provider.

        Args:
            api_key: DeepSeek API key
            model: Model name (e.g., deepseek-chat)
            base_url: API base URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def refine_text(self, text: str, prompt: str) -> str:
        """
        Refine text using DeepSeek API.

        Args:
            text: Draft text to refine
            prompt: System prompt

        Returns:
            Refined text

        Raises:
            LLMTimeoutError: Request timeout
            LLMAPIError: API error
        """
        if not text or not text.strip():
            return text

        # Truncate if too long (max 10,000 chars)
        if len(text) > 10000:
            logger.warning(f"Text too long ({len(text)} chars), truncating to 10,000")
            text = text[:10000]

        try:
            response = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.3,  # Low temperature for corrections
                    "max_tokens": 4000,
                },
            )

            response.raise_for_status()
            data = response.json()

            refined = data["choices"][0]["message"]["content"]

            # Log token usage
            usage = data.get("usage", {})
            logger.info(
                f"DeepSeek refinement: "
                f"input={usage.get('prompt_tokens', 0)} tokens, "
                f"output={usage.get('completion_tokens', 0)} tokens, "
                f"total={usage.get('total_tokens', 0)} tokens"
            )

            return refined.strip()

        except httpx.TimeoutException as e:
            logger.error(f"DeepSeek timeout: {e}")
            raise LLMTimeoutError(f"DeepSeek request timeout after {self.timeout}s") from e

        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API error: {e.response.status_code} - {e.response.text}")
            raise LLMAPIError(
                f"DeepSeek API error: {e.response.status_code}"
            ) from e

        except Exception as e:
            logger.error(f"DeepSeek unexpected error: {e}")
            raise LLMAPIError(f"DeepSeek error: {e}") from e

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


class LLMFactory:
    """Factory for creating LLM providers."""

    @staticmethod
    def create_provider(settings: Settings) -> Optional[LLMProvider]:
        """
        Create LLM provider from settings.

        Args:
            settings: Application settings

        Returns:
            LLM provider instance or None if disabled

        Raises:
            ValueError: Unknown provider
        """
        if not settings.llm_refinement_enabled:
            logger.info("LLM refinement disabled")
            return None

        if not settings.llm_api_key:
            logger.warning("LLM refinement enabled but no API key provided")
            return None

        provider_name = settings.llm_provider.lower()

        if provider_name == "deepseek":
            logger.info("Creating DeepSeek provider")
            return DeepSeekProvider(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout,
            )

        # Future providers: openai, gigachat
        raise ValueError(f"Unknown LLM provider: {provider_name}")


class LLMService:
    """High-level LLM service for text refinement."""

    def __init__(self, provider: Optional[LLMProvider], prompt: str):
        """
        Initialize LLM service.

        Args:
            provider: LLM provider (None = disabled)
            prompt: System prompt for refinement
        """
        self.provider = provider
        self.prompt = prompt

    async def refine_transcription(self, draft_text: str) -> str:
        """
        Refine transcribed text.

        Args:
            draft_text: Draft transcription

        Returns:
            Refined text (or draft if refinement disabled/fails)
        """
        if not self.provider:
            logger.debug("LLM refinement disabled, returning draft")
            return draft_text

        try:
            logger.info(f"Refining text ({len(draft_text)} chars)...")
            refined = await self.provider.refine_text(draft_text, self.prompt)
            logger.info("Text refinement successful")
            return refined

        except LLMTimeoutError:
            logger.warning("LLM timeout, using draft as final")
            return draft_text

        except LLMAPIError as e:
            logger.error(f"LLM API error: {e}, using draft as final")
            return draft_text

        except Exception as e:
            logger.error(f"Unexpected LLM error: {e}, using draft as final")
            return draft_text

    async def close(self):
        """Cleanup resources."""
        if self.provider:
            await self.provider.close()
```

#### Configuration Changes

**Add to `src/config.py`**:

```python
# LLM Refinement Configuration
llm_refinement_enabled: bool = Field(
    default=False,
    description="Enable LLM text refinement"
)
llm_provider: str = Field(
    default="deepseek",
    description="LLM provider: deepseek, openai, gigachat"
)
llm_api_key: str | None = Field(
    default=None,
    description="LLM API key"
)
llm_model: str = Field(
    default="deepseek-chat",
    description="LLM model name"
)
llm_base_url: str = Field(
    default="https://api.deepseek.com",
    description="LLM API base URL"
)
llm_refinement_prompt: str = Field(
    default="""Улучши транскрипцию голосового сообщения:
- Исправь орфографические и пунктуационные ошибки
- Добавь правильную пунктуацию и заглавные буквы
- Сохрани исходный смысл и стиль речи
- Верни только исправленный текст без комментариев""",
    description="System prompt for text refinement"
)
llm_timeout: int = Field(
    default=30,
    description="LLM request timeout in seconds"
)
```

#### Dependencies

Add to `pyproject.toml`:
```toml
httpx = "^0.28"  # Already in project
tenacity = "^9.0.0"  # NEW - for retry logic
```

#### Tests

**`tests/unit/test_llm_service.py`** (~150 lines):
- Test DeepSeekProvider with mocked API
- Test timeout handling
- Test API error handling
- Test retry logic
- Test LLMService fallback behavior

---

### Phase 2: Hybrid Strategy & Audio Preprocessing (Day 2)

**Goal**: Implement hybrid routing and audio preprocessing

#### Files to Modify

**`src/transcription/routing/strategies.py`** (add ~150 lines)

```python
class HybridStrategy(RoutingStrategy):
    """
    Hybrid transcription strategy with duration-based routing.

    - Short audio (<threshold): Use quality model directly
    - Long audio (≥threshold): Use fast draft model, then LLM refinement

    Supports different providers for draft (faster-whisper OR openai).
    """

    def __init__(
        self,
        short_threshold: int,
        draft_provider_name: str,
        draft_model: str,
        quality_provider_name: str,
        quality_model: str,
    ):
        """
        Initialize hybrid strategy.

        Args:
            short_threshold: Duration threshold in seconds
            draft_provider_name: Provider for draft (faster-whisper, openai)
            draft_model: Model for draft (e.g., small, tiny)
            quality_provider_name: Provider for quality (usually faster-whisper)
            quality_model: Model for quality (e.g., medium)
        """
        self.short_threshold = short_threshold
        self.draft_provider = draft_provider_name
        self.draft_model = draft_model
        self.quality_provider = quality_provider_name
        self.quality_model = quality_model

    async def select_provider(
        self,
        context: TranscriptionContext,
        providers: dict[str, TranscriptionProvider],
    ) -> str:
        """
        Select provider based on audio duration.

        Args:
            context: Transcription context with duration
            providers: Available providers

        Returns:
            Provider name to use
        """
        duration = context.duration_seconds

        if duration < self.short_threshold:
            # Short audio: use quality provider
            logger.info(
                f"Short audio ({duration}s), using quality provider: "
                f"{self.quality_provider}/{self.quality_model}"
            )
            return self.quality_provider
        else:
            # Long audio: use draft provider
            logger.info(
                f"Long audio ({duration}s), using draft provider: "
                f"{self.draft_provider}/{self.draft_model}"
            )
            return self.draft_provider

    def get_model_for_duration(self, duration: float) -> str:
        """
        Get model name based on duration.

        Args:
            duration: Audio duration in seconds

        Returns:
            Model name (e.g., small, medium)
        """
        if duration < self.short_threshold:
            return self.quality_model
        return self.draft_model

    def requires_refinement(self, duration: float) -> bool:
        """
        Check if transcription result needs LLM refinement.

        Args:
            duration: Audio duration in seconds

        Returns:
            True if refinement needed (long audio)
        """
        return duration >= self.short_threshold
```

**`src/transcription/audio_handler.py`** (add ~120 lines)

```python
def preprocess_audio(self, audio_path: Path) -> Path:
    """
    Apply audio preprocessing pipeline.

    Applies transformations in order:
    1. Mono conversion (if enabled)
    2. Speed adjustment (if enabled)

    Args:
        audio_path: Original audio file

    Returns:
        Path to preprocessed audio (or original if no preprocessing)

    Raises:
        FFmpegError: If preprocessing fails
    """
    path = audio_path

    # Mono conversion
    if settings.audio_convert_to_mono:
        try:
            path = self._convert_to_mono(path)
            logger.info(f"Converted to mono: {path.name}")
        except Exception as e:
            logger.warning(f"Mono conversion failed: {e}, using original")
            path = audio_path

    # Speed adjustment
    if settings.audio_speed_multiplier != 1.0:
        try:
            path = self._adjust_speed(path)
            logger.info(
                f"Adjusted speed {settings.audio_speed_multiplier}x: {path.name}"
            )
        except Exception as e:
            logger.warning(f"Speed adjustment failed: {e}, using original")
            path = audio_path if path == audio_path else path

    return path

def _convert_to_mono(self, input_path: Path) -> Path:
    """
    Convert audio to mono.

    Args:
        input_path: Input audio file

    Returns:
        Path to mono audio file

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
    """
    output_path = input_path.parent / f"{input_path.stem}_mono.wav"

    subprocess.run(
        [
            "ffmpeg",
            "-y",  # Overwrite
            "-i", str(input_path),
            "-ac", "1",  # Mono channel
            "-ar", str(settings.audio_target_sample_rate),
            "-acodec", "pcm_s16le",  # Uncompressed PCM
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return output_path

def _adjust_speed(self, input_path: Path) -> Path:
    """
    Adjust audio playback speed.

    Args:
        input_path: Input audio file

    Returns:
        Path to speed-adjusted audio file

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
    """
    multiplier = settings.audio_speed_multiplier
    output_path = input_path.parent / f"{input_path.stem}_speed{multiplier}x.wav"

    # Note: atempo filter only supports 0.5-2.0 range
    # For values outside, need to chain multiple filters
    if not (0.5 <= multiplier <= 2.0):
        raise ValueError(f"Speed multiplier must be 0.5-2.0, got {multiplier}")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-filter:a", f"atempo={multiplier}",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return output_path
```

#### Configuration Changes

**Add to `src/config.py`**:

```python
# Hybrid Strategy Configuration
hybrid_short_threshold: int = Field(
    default=20,
    description="Duration threshold for hybrid strategy (seconds)"
)
hybrid_draft_provider: str = Field(
    default="faster-whisper",
    description="Provider for draft: faster-whisper, openai"
)
hybrid_draft_model: str = Field(
    default="small",
    description="Model for draft (e.g., tiny, small)"
)
hybrid_quality_provider: str = Field(
    default="faster-whisper",
    description="Provider for quality transcription"
)
hybrid_quality_model: str = Field(
    default="medium",
    description="Model for quality transcription"
)

# Audio Preprocessing Configuration
audio_convert_to_mono: bool = Field(
    default=False,
    description="Convert audio to mono before transcription"
)
audio_target_sample_rate: int = Field(
    default=16000,
    description="Target sample rate for mono conversion (Hz)"
)
audio_speed_multiplier: float = Field(
    default=1.0,
    description="Audio speed multiplier (0.5-2.0, 1.0=original)"
)
```

#### Docker Changes

**`Dockerfile`** - Add ffmpeg:

```dockerfile
# Already has ffmpeg in current Dockerfile, verify it's there
# If not, add:
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
```

#### Tests

**`tests/unit/test_hybrid_strategy.py`** (~200 lines):
- Test short audio routing (quality model)
- Test long audio routing (draft model)
- Test threshold boundary
- Test refinement requirement logic

**`tests/unit/test_audio_preprocessing.py`** (~100 lines):
- Test mono conversion
- Test speed adjustment
- Test pipeline (both transformations)
- Test error handling (ffmpeg failures)

---

### Phase 3: Handler Integration & Staged Messages (Day 3)

**Goal**: Integrate hybrid strategy into handlers with staged updates

#### Files to Modify

**`src/bot/handlers.py`** (modify voice_message_handler, add ~150 lines)

Key changes:
1. Call `preprocess_audio()` before transcription
2. Detect hybrid strategy
3. Implement staged message updates (draft → refining → final)
4. Fallback handling (LLM failures)

```python
async def voice_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle voice message transcription with hybrid strategy support.

    Flow:
    1. Download audio
    2. Preprocess (mono, speed)
    3. Transcribe (draft for long audio)
    4. Send draft (if hybrid + long)
    5. Refine with LLM (if enabled)
    6. Send final result
    """
    # ... existing setup code ...

    # === NEW: Preprocess audio ===
    try:
        processed_path = self.audio_handler.preprocess_audio(file_path)
        logger.info(f"Audio preprocessed: {processed_path.name}")
    except Exception as e:
        logger.warning(f"Preprocessing failed: {e}, using original")
        processed_path = file_path

    # === Transcribe (draft or final) ===
    transcription_context = TranscriptionContext(
        duration_seconds=duration_seconds,
        language="ru",
    )

    result = await self.transcription_router.transcribe(
        processed_path,
        transcription_context,
    )

    # === Check if hybrid strategy with long audio ===
    is_hybrid = isinstance(
        self.transcription_router.strategy,
        HybridStrategy
    )
    needs_refinement = (
        is_hybrid
        and self.transcription_router.strategy.requires_refinement(duration_seconds)
    )

    if needs_refinement and self.llm_service:
        # === Send draft ===
        draft_text = result.text
        await status_msg.edit_text(
            f"✅ Черновик готов:\n\n{draft_text}\n\n"
            f"🔄 Улучшаю текст..."
        )

        # === Refine with LLM ===
        try:
            refined_text = await self.llm_service.refine_transcription(draft_text)

            # === Send final ===
            await status_msg.edit_text(
                f"✨ Готово!\n\n{refined_text}"
            )

            final_text = refined_text

        except Exception as e:
            logger.error(f"LLM refinement failed: {e}")
            # Fallback: draft is final
            await status_msg.edit_text(
                f"✅ Готово:\n\n{draft_text}\n\n"
                f"ℹ️ (улучшение текста недоступно)"
            )
            final_text = draft_text
    else:
        # === Direct result (short audio or non-hybrid) ===
        await status_msg.edit_text(
            f"✅ Готово!\n\n{result.text}"
        )
        final_text = result.text

    # === Update usage record ===
    await self.usage_repo.update(
        usage.id,
        voice_duration_seconds=duration_seconds,
        model_size=result.model_name,
        processing_time_seconds=result.processing_time,
        transcription_length=len(final_text),
        updated_at=datetime.now(timezone.utc),
    )
```

**`src/main.py`** (initialization, add ~50 lines)

```python
async def main():
    # ... existing code ...

    # === Initialize LLM Service ===
    llm_service = None
    if settings.llm_refinement_enabled:
        try:
            llm_provider = LLMFactory.create_provider(settings)
            if llm_provider:
                llm_service = LLMService(
                    provider=llm_provider,
                    prompt=settings.llm_refinement_prompt,
                )
                logger.info("LLM service initialized")
            else:
                logger.warning("LLM service disabled (no API key)")
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")

    # === Create routing strategy ===
    strategy: RoutingStrategy

    if settings.whisper_routing_strategy == "hybrid":
        logger.info("Using hybrid routing strategy")
        strategy = HybridStrategy(
            short_threshold=settings.hybrid_short_threshold,
            draft_provider_name=settings.hybrid_draft_provider,
            draft_model=settings.hybrid_draft_model,
            quality_provider_name=settings.hybrid_quality_provider,
            quality_model=settings.hybrid_quality_model,
        )
    elif settings.whisper_routing_strategy == "single":
        strategy = SingleProviderStrategy(settings.primary_provider)
    elif settings.whisper_routing_strategy == "fallback":
        strategy = FallbackStrategy(
            primary=settings.primary_provider,
            fallback=settings.fallback_provider,
        )
    else:
        raise ValueError(f"Unknown strategy: {settings.whisper_routing_strategy}")

    # === Create transcription router ===
    transcription_router = TranscriptionRouter(providers, strategy)
    await transcription_router.initialize_all()

    # === Pass llm_service to handlers ===
    handlers = VoiceHandlers(
        queue_manager=queue_manager,
        transcription_router=transcription_router,
        audio_handler=audio_handler,
        usage_repo=usage_repo,
        user_repo=user_repo,
        llm_service=llm_service,  # NEW
    )

    # ... rest of initialization ...
```

#### Handler Constructor Update

```python
class VoiceHandlers:
    def __init__(
        self,
        queue_manager: QueueManager,
        transcription_router: TranscriptionRouter,
        audio_handler: AudioHandler,
        usage_repo: UsageRepository,
        user_repo: UserRepository,
        llm_service: Optional[LLMService] = None,  # NEW
    ):
        self.queue_manager = queue_manager
        self.transcription_router = transcription_router
        self.audio_handler = audio_handler
        self.usage_repo = usage_repo
        self.user_repo = user_repo
        self.llm_service = llm_service  # NEW
```

#### Tests

**`tests/integration/test_hybrid_flow.py`** (~200 lines):
- Test short audio (no refinement)
- Test long audio (with refinement)
- Test LLM failure fallback
- Test preprocessing integration

---

### Phase 4: Testing, Documentation & Deployment (Day 4)

**Goal**: Comprehensive testing and documentation

#### Testing Checklist

**Unit Tests**:
- ✅ LLM Service (DeepSeekProvider, retry logic, errors)
- ✅ Hybrid Strategy (routing logic, threshold)
- ✅ Audio Preprocessing (mono, speed, errors)

**Integration Tests**:
- ✅ End-to-end short audio (quality model)
- ✅ End-to-end long audio (draft + refinement)
- ✅ Preprocessing + transcription pipeline
- ✅ LLM failure fallback
- ✅ ffmpeg failure fallback

**Manual Testing**:
- ✅ Test with real audio files (7s, 24s, 60s, 120s)
- ✅ Verify draft quality (small model)
- ✅ Verify refinement quality (DeepSeek)
- ✅ Test different speeds (1.0, 1.2, 1.5)
- ✅ Test mono conversion
- ✅ Check Telegram message updates (draft → final)

#### Documentation Updates

**`.env.example`** (add hybrid configuration):
```bash
# =============================================================================
# Hybrid Transcription Strategy
# =============================================================================

# Enable hybrid strategy
WHISPER_ROUTING_STRATEGY=hybrid

# Duration threshold (seconds)
# Audio < threshold: quality model directly
# Audio >= threshold: fast draft → LLM refinement
HYBRID_SHORT_THRESHOLD=20

# Draft provider (for long audio)
# Options: faster-whisper, openai
HYBRID_DRAFT_PROVIDER=faster-whisper

# Draft model (if using faster-whisper)
# Recommended: small (good balance of speed/quality)
# Alternatives: tiny (faster, lower quality), base
HYBRID_DRAFT_MODEL=small

# Quality provider (for short audio and reference)
HYBRID_QUALITY_PROVIDER=faster-whisper

# Quality model
# Recommended: medium (production default)
HYBRID_QUALITY_MODEL=medium

# =============================================================================
# LLM Text Refinement
# =============================================================================

# Enable LLM refinement (improves draft transcriptions)
LLM_REFINEMENT_ENABLED=true

# LLM provider
# Options: deepseek (recommended, cheap), openai, gigachat
LLM_PROVIDER=deepseek

# DeepSeek API key
# Get from: https://platform.deepseek.com/api_keys
# Cost: ~$0.0002 per 60s audio transcription
LLM_API_KEY=sk-your-deepseek-api-key-here

# DeepSeek model
LLM_MODEL=deepseek-chat

# DeepSeek API base URL
LLM_BASE_URL=https://api.deepseek.com

# Refinement system prompt
# Customize to adjust refinement behavior
LLM_REFINEMENT_PROMPT="Улучши транскрипцию голосового сообщения: исправь ошибки, добавь пунктуацию, сохрани смысл"

# LLM request timeout (seconds)
LLM_TIMEOUT=30

# =============================================================================
# Audio Preprocessing
# =============================================================================

# Convert to mono before transcription
# Pros: Faster, smaller files
# Cons: May reduce quality for stereo recordings
AUDIO_CONVERT_TO_MONO=false

# Target sample rate for mono conversion (Hz)
# 16000 Hz sufficient for speech
AUDIO_TARGET_SAMPLE_RATE=16000

# Audio speed multiplier
# 1.0 = original speed
# 1.5 = 50% faster (recommended for testing)
# 2.0 = 2x faster (may reduce quality)
# Range: 0.5-2.0
AUDIO_SPEED_MULTIPLIER=1.0

# =============================================================================
# Usage Example: Hybrid Mode (Recommended)
# =============================================================================
# WHISPER_ROUTING_STRATEGY=hybrid
# HYBRID_SHORT_THRESHOLD=20
# HYBRID_DRAFT_PROVIDER=faster-whisper
# HYBRID_DRAFT_MODEL=small
# HYBRID_QUALITY_MODEL=medium
# LLM_REFINEMENT_ENABLED=true
# LLM_PROVIDER=deepseek
# LLM_API_KEY=sk-...
# AUDIO_SPEED_MULTIPLIER=1.5
```

**`docs/getting-started/configuration.md`** - Add hybrid section

**`README.md`** - Update features section

**`memory-bank/activeContext.md`** - Update with Phase 8 completion

#### Deployment Preparation

**Docker**:
- ✅ Verify ffmpeg in Dockerfile
- ✅ Add tenacity to requirements.txt
- ✅ Test Docker build locally

**VPS**:
- ✅ Set environment variables (without LLM_API_KEY initially)
- ✅ Test without refinement first (LLM_REFINEMENT_ENABLED=false)
- ✅ Add DeepSeek API key when ready
- ✅ Enable refinement (LLM_REFINEMENT_ENABLED=true)

**CI/CD**:
- ✅ Update GitHub Actions secrets (LLM_API_KEY)
- ✅ Test workflow with new dependencies

---

## Configuration Reference

### Complete ENV Configuration

```bash
# Hybrid Strategy
WHISPER_ROUTING_STRATEGY=hybrid
HYBRID_SHORT_THRESHOLD=20
HYBRID_DRAFT_PROVIDER=faster-whisper
HYBRID_DRAFT_MODEL=small
HYBRID_QUALITY_PROVIDER=faster-whisper
HYBRID_QUALITY_MODEL=medium

# LLM Refinement
LLM_REFINEMENT_ENABLED=true
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-your-key-here  # Add later
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com
LLM_REFINEMENT_PROMPT="Улучши транскрипцию..."
LLM_TIMEOUT=30

# Audio Preprocessing
AUDIO_CONVERT_TO_MONO=false
AUDIO_TARGET_SAMPLE_RATE=16000
AUDIO_SPEED_MULTIPLIER=1.5  # Start with 1.5x
```

### Testing Configurations

**Conservative (Start Here)**:
```bash
WHISPER_ROUTING_STRATEGY=hybrid
HYBRID_DRAFT_MODEL=small
LLM_REFINEMENT_ENABLED=false  # Test without LLM first
AUDIO_SPEED_MULTIPLIER=1.0    # Original speed
```

**Aggressive (After Testing)**:
```bash
WHISPER_ROUTING_STRATEGY=hybrid
HYBRID_DRAFT_MODEL=small
LLM_REFINEMENT_ENABLED=true
AUDIO_SPEED_MULTIPLIER=1.5    # 50% faster
AUDIO_CONVERT_TO_MONO=true    # If quality OK
```

---

## Risk Mitigation

### High-Priority Risks

**1. DeepSeek API Availability**
- **Risk**: API down, rate limits
- **Mitigation**:
  - Retry with exponential backoff (3 attempts)
  - Fallback to draft as final
  - Clear user messaging
  - Monitor API status

**2. ffmpeg Missing/Failing**
- **Risk**: Docker build fails, preprocessing errors
- **Mitigation**:
  - Verify ffmpeg in Dockerfile
  - Test Docker build before deployment
  - Fallback to original audio if preprocessing fails
  - Log warnings, don't crash

**3. Draft Quality Insufficient**
- **Risk**: small model produces poor draft
- **Mitigation**:
  - A/B test small vs tiny
  - Adjustable threshold (ENV)
  - Monitor draft vs refined comparison
  - Can switch to base model if needed

### Medium-Priority Risks

**4. LLM Changes Meaning**
- **Risk**: Refinement alters content
- **Mitigation**:
  - Low temperature (0.3) for corrections
  - Clear prompt: "preserve meaning"
  - User sees draft first (can stop if wrong)
  - Log draft + refined for comparison

**5. Increased Costs**
- **Risk**: LLM usage exceeds budget
- **Mitigation**:
  - DeepSeek is very cheap (~$0.0002/audio)
  - Log token usage
  - Max text length (10,000 chars)
  - Can disable refinement anytime

---

## Success Metrics

### Performance Targets

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| 20s audio | 12s | 12s (no change) | Direct quality model |
| 60s audio | 36s | 6-8s | 3s draft + 3-5s refinement |
| 120s audio | 72s | 9-12s | 6s draft + 3-6s refinement |
| 300s audio | 180s | 20-25s | 15s draft + 5-10s refinement |

### Quality Targets

- ✅ Draft understandable (user can read while waiting)
- ✅ Refined text has fewer errors than draft
- ✅ Meaning preserved in refinement
- ✅ No crashes if LLM fails

### Cost Targets

- ✅ Cost < $0.001 per transcription (vs $0.006 for OpenAI Whisper)
- ✅ Stay within budget (monitoring required)

---

## Implementation Checklist

### Pre-Implementation

- [ ] Review this plan thoroughly
- [ ] Set up DeepSeek API account (later)
- [ ] Prepare test audio files (have examples)
- [ ] Create feature branch: `feature/hybrid-transcription`

### Phase 1: LLM Service (Day 1)

- [ ] Create `src/services/llm_service.py`
- [ ] Add LLM config to `src/config.py`
- [ ] Add tenacity dependency to `pyproject.toml`
- [ ] Run `poetry install`
- [ ] Write unit tests: `tests/unit/test_llm_service.py`
- [ ] Test with mocked DeepSeek API
- [ ] Commit: `feat: add LLM service for text refinement`

### Phase 2: Hybrid Strategy (Day 2)

- [ ] Add `HybridStrategy` to `src/transcription/routing/strategies.py`
- [ ] Add hybrid config to `src/config.py`
- [ ] Add preprocessing to `src/transcription/audio_handler.py`
- [ ] Add audio preprocessing config to `src/config.py`
- [ ] Verify ffmpeg in Dockerfile
- [ ] Write tests: `test_hybrid_strategy.py`, `test_audio_preprocessing.py`
- [ ] Commit: `feat: add hybrid strategy and audio preprocessing`

### Phase 3: Integration (Day 3)

- [ ] Update `src/bot/handlers.py` (voice_message_handler)
- [ ] Update `src/main.py` (LLM service init, strategy selection)
- [ ] Update handler constructor with llm_service parameter
- [ ] Write integration tests: `test_hybrid_flow.py`
- [ ] Test locally without LLM (LLM_REFINEMENT_ENABLED=false)
- [ ] Commit: `feat: integrate hybrid strategy into handlers`

### Phase 4: Testing & Docs (Day 4)

- [ ] Run all unit tests: `poetry run pytest tests/unit/`
- [ ] Run integration tests: `poetry run pytest tests/integration/`
- [ ] Test with real audio files (various durations)
- [ ] Update `.env.example`
- [ ] Update `docs/getting-started/configuration.md`
- [ ] Update README.md
- [ ] Update `memory-bank/activeContext.md`
- [ ] Commit: `docs: add hybrid transcription documentation`

### Deployment

- [ ] Create PR: `feat: hybrid transcription acceleration`
- [ ] Review changes
- [ ] Merge to main
- [ ] CI/CD builds and deploys
- [ ] Test on VPS without LLM first
- [ ] Add DeepSeek API key to environment
- [ ] Enable LLM refinement
- [ ] Monitor performance and costs
- [ ] Adjust settings based on results

---

## Quick Start (After Implementation)

### 1. Basic Setup (No LLM)

Test hybrid strategy without refinement first:

```bash
WHISPER_ROUTING_STRATEGY=hybrid
HYBRID_SHORT_THRESHOLD=20
HYBRID_DRAFT_PROVIDER=faster-whisper
HYBRID_DRAFT_MODEL=small
LLM_REFINEMENT_ENABLED=false
```

Send audio, verify:
- Short audio (<20s): Uses medium model
- Long audio (≥20s): Uses small model (faster)

### 2. Add LLM Refinement

Once comfortable:

```bash
# Get API key from https://platform.deepseek.com/api_keys
LLM_REFINEMENT_ENABLED=true
LLM_API_KEY=sk-your-key-here
```

Send long audio, verify:
- Draft appears quickly (~3s)
- Refined version follows (~3-5s later)

### 3. Enable Preprocessing (Optional)

Test audio preprocessing:

```bash
AUDIO_SPEED_MULTIPLIER=1.5  # 50% faster
```

Compare quality with 1.0x vs 1.5x vs 2.0x.

### 4. Production Settings

After testing:

```bash
WHISPER_ROUTING_STRATEGY=hybrid
HYBRID_SHORT_THRESHOLD=20
HYBRID_DRAFT_MODEL=small
LLM_REFINEMENT_ENABLED=true
LLM_API_KEY=sk-...
AUDIO_SPEED_MULTIPLIER=1.5
```

---

## Troubleshooting

### LLM Service Issues

**"LLM refinement disabled (no API key)"**
- Add `LLM_API_KEY` to environment
- Verify `LLM_REFINEMENT_ENABLED=true`

**"DeepSeek timeout"**
- Check network connectivity
- Increase `LLM_TIMEOUT` (default 30s)
- Verify API key is valid

**"LLM API error: 401"**
- Invalid API key
- Check key format: `sk-...`

### Audio Preprocessing Issues

**"ffmpeg: command not found"**
- Verify ffmpeg in Dockerfile
- Rebuild Docker image

**"Speed multiplier must be 0.5-2.0"**
- Check `AUDIO_SPEED_MULTIPLIER` value
- Must be in range [0.5, 2.0]

### Strategy Issues

**"Unknown strategy: hybrid"**
- Verify `WHISPER_ROUTING_STRATEGY=hybrid`
- Check for typos

**Both short and long audio use same model**
- Check `HYBRID_SHORT_THRESHOLD` setting
- Verify audio duration detection

---

## Future Enhancements

### Phase 2 Additions (After Initial Release)

1. **Additional LLM Providers**
   - OpenAI (GPT-4)
   - GigaChat (Sber)
   - Anthropic Claude

2. **Advanced Preprocessing**
   - Noise reduction
   - Volume normalization
   - Automatic gain control

3. **Quality Metrics**
   - Automatic comparison: draft vs refined
   - User feedback on quality
   - A/B testing framework

4. **Cost Optimization**
   - Adaptive threshold (adjust based on queue load)
   - Cache refinements (same audio)
   - Batch processing for multiple users

---

## Appendix

### Dependencies Summary

**New**:
- `tenacity = "^9.0.0"` - Retry logic for LLM API

**Existing (Verified)**:
- `httpx = "^0.28"` - HTTP client for LLM API
- ffmpeg - System dependency (Docker)

### File Changes Summary

**New Files** (~650 lines):
- `src/services/llm_service.py` (~250 lines)
- `tests/unit/test_llm_service.py` (~150 lines)
- `tests/unit/test_hybrid_strategy.py` (~200 lines)
- `tests/unit/test_audio_preprocessing.py` (~100 lines)
- `tests/integration/test_hybrid_flow.py` (~200 lines)

**Modified Files** (~500 lines added):
- `src/transcription/routing/strategies.py` (+150 lines)
- `src/transcription/audio_handler.py` (+120 lines)
- `src/bot/handlers.py` (+150 lines)
- `src/main.py` (+50 lines)
- `src/config.py` (+80 lines)
- `.env.example` (+50 lines)

**Total**: ~1,150 lines (new + modified)

### Testing Summary

- Unit tests: ~600 lines
- Integration tests: ~200 lines
- Manual testing: ~2-3 hours

---

## Sign-off

**Plan Status**: ✅ APPROVED
**Ready for Implementation**: YES
**Next Step**: Create feature branch and begin Phase 1
**Estimated Completion**: 3-4 days
**Documentation**: Complete

---

*This implementation plan serves as the comprehensive guide for implementing hybrid transcription acceleration. All architectural decisions, technical specifications, and success criteria are documented for reference during implementation and future maintenance.*
