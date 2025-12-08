"""Routing strategies for transcription provider selection."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from src.transcription.models import BenchmarkConfig, TranscriptionContext
from src.transcription.providers.base import TranscriptionProvider

logger = logging.getLogger(__name__)


class RoutingStrategy(ABC):
    """Abstract base for routing strategies."""

    @abstractmethod
    async def select_provider(
        self,
        context: TranscriptionContext,
        providers: dict[str, TranscriptionProvider],
    ) -> str:
        """
        Select provider to use for transcription.

        Args:
            context: Transcription context with metadata
            providers: Available providers by name

        Returns:
            Provider name to use

        Raises:
            ValueError: If no suitable provider found
        """
        pass

    def supports_fallback(self) -> bool:
        """Check if strategy supports fallback to alternative provider."""
        return False

    async def get_fallback(self, failed_provider: str) -> Optional[str]:
        """
        Get fallback provider name after failure.

        Args:
            failed_provider: Name of provider that failed

        Returns:
            Fallback provider name or None
        """
        return None

    def is_benchmark_mode(self) -> bool:
        """Check if this is benchmark strategy (special handling)."""
        return False


class SingleProviderStrategy(RoutingStrategy):
    """Always use one configured provider."""

    def __init__(self, provider_name: str):
        """
        Initialize single provider strategy.

        Args:
            provider_name: Name of provider to always use
        """
        self.provider_name = provider_name

    async def select_provider(
        self,
        context: TranscriptionContext,
        providers: dict[str, TranscriptionProvider],
    ) -> str:
        """Always return configured provider."""
        if self.provider_name not in providers:
            raise ValueError(
                f"Provider '{self.provider_name}' not available. "
                f"Available: {list(providers.keys())}"
            )
        return self.provider_name


class FallbackStrategy(RoutingStrategy):
    """Use primary provider with fallback to secondary on failure."""

    def __init__(self, primary: str, fallback: str):
        """
        Initialize fallback strategy.

        Args:
            primary: Primary provider name
            fallback: Fallback provider name
        """
        self.primary = primary
        self.fallback_provider = fallback

    async def select_provider(
        self,
        context: TranscriptionContext,
        providers: dict[str, TranscriptionProvider],
    ) -> str:
        """Return primary provider."""
        if self.primary not in providers:
            raise ValueError(
                f"Primary provider '{self.primary}' not available. "
                f"Available: {list(providers.keys())}"
            )
        return self.primary

    def supports_fallback(self) -> bool:
        """This strategy supports fallback."""
        return True

    async def get_fallback(self, failed_provider: str) -> Optional[str]:
        """Return fallback provider name."""
        if failed_provider == self.primary:
            return self.fallback_provider
        return None


class BenchmarkStrategy(RoutingStrategy):
    """
    Special strategy that runs transcription through ALL configured
    provider/model combinations and returns comprehensive comparison report.

    WARNING: This is for testing only! One voice message will trigger
    multiple transcriptions (can be expensive with OpenAI API).
    """

    def __init__(self, benchmark_configs: list[BenchmarkConfig]):
        """
        Initialize benchmark strategy.

        Args:
            benchmark_configs: List of provider/model combinations to test
        """
        self.configs = benchmark_configs

    async def select_provider(
        self,
        context: TranscriptionContext,
        providers: dict[str, TranscriptionProvider],
    ) -> str:
        """
        Not used in benchmark mode.

        Benchmark mode uses router.run_benchmark() instead of regular transcribe().
        """
        raise NotImplementedError("BenchmarkStrategy requires using router.run_benchmark() method")

    def is_benchmark_mode(self) -> bool:
        """This is benchmark strategy."""
        return True


class HybridStrategy(RoutingStrategy):
    """
    Hybrid transcription strategy with duration-based routing.

    - Short audio (<threshold): Use quality model directly
    - Long audio (>=threshold): Use fast draft model, then LLM refinement

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
        Select provider based on audio duration or explicit preference.

        Args:
            context: Transcription context with duration and optional provider_preference
            providers: Available providers

        Returns:
            Provider name to use
        """
        # Check if explicit provider preference is set (for retranscription)
        if context.provider_preference:
            preferred = context.provider_preference
            # Check if it's a provider name or model name
            if preferred in providers:
                logger.info(f"Using explicit provider preference: {preferred}")
                return preferred
            else:
                # Try to find provider by model name (e.g., "openai" for retranscription)
                # Look for provider that contains the preference in its name
                for provider_name in providers.keys():
                    if preferred.lower() in provider_name.lower():
                        logger.info(f"Using provider {provider_name} matching preference: {preferred}")
                        return provider_name
                logger.warning(
                    f"Provider preference '{preferred}' not found, falling back to strategy"
                )

        duration = context.duration_seconds

        if duration < self.short_threshold:
            # Short audio: use quality provider
            if self.quality_provider not in providers:
                raise ValueError(
                    f"Quality provider '{self.quality_provider}' not available. "
                    f"Available: {list(providers.keys())}"
                )
            logger.info(
                f"Short audio ({duration}s < {self.short_threshold}s), "
                f"using quality provider: {self.quality_provider} (model={self.quality_model})"
            )
            return self.quality_provider
        else:
            # Long audio: use draft provider
            if self.draft_provider not in providers:
                raise ValueError(
                    f"Draft provider '{self.draft_provider}' not available. "
                    f"Available: {list(providers.keys())}"
                )
            logger.info(
                f"Long audio ({duration}s >= {self.short_threshold}s), "
                f"using draft provider: {self.draft_provider} (model={self.draft_model})"
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
