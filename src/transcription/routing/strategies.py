"""Routing strategies for transcription provider selection."""

from abc import ABC, abstractmethod
from typing import Optional

from src.transcription.models import BenchmarkConfig, TranscriptionContext
from src.transcription.providers.base import TranscriptionProvider


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
