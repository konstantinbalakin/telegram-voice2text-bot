"""Transcription router with provider management and benchmarking."""

import logging
from pathlib import Path
from typing import Optional

from src.transcription.models import (
    BenchmarkConfig,
    BenchmarkReport,
    TranscriptionContext,
    TranscriptionResult,
)
from src.transcription.providers.base import TranscriptionProvider
from src.transcription.providers.faster_whisper_provider import FastWhisperProvider
from src.transcription.providers.openai_provider import OpenAIProvider
from src.transcription.routing.strategies import BenchmarkStrategy, RoutingStrategy

logger = logging.getLogger(__name__)


class TranscriptionRouter:
    """Routes transcription requests to appropriate provider based on strategy."""

    def __init__(
        self,
        providers: dict[str, TranscriptionProvider],
        strategy: RoutingStrategy,
    ):
        """
        Initialize transcription router.

        Args:
            providers: Available providers by name
            strategy: Routing strategy to use
        """
        self.providers = providers
        self.strategy = strategy
        self._benchmark_providers: dict[str, TranscriptionProvider] = {}

        # Metrics tracking
        self.metrics: dict[str, dict[str, float]] = {
            provider_name: {
                "requests": 0,
                "errors": 0,
                "total_duration": 0.0,
            }
            for provider_name in providers.keys()
        }

        logger.info(f"TranscriptionRouter initialized with strategy: {strategy.__class__.__name__}")

    def get_active_provider_name(self) -> Optional[str]:
        """
        Get name of the active provider for preprocessing.

        For strategies that can determine provider without context (SingleProviderStrategy,
        FallbackStrategy, StructureStrategy), returns the primary provider name.
        For context-dependent strategies (HybridStrategy), returns None.

        Returns:
            Provider name or None if determination requires runtime context
        """
        from src.transcription.routing.strategies import (
            FallbackStrategy,
            SingleProviderStrategy,
            StructureStrategy,
        )

        # For simple strategies, we can determine the provider synchronously
        if isinstance(self.strategy, SingleProviderStrategy):
            return self.strategy.provider_name
        elif isinstance(self.strategy, FallbackStrategy):
            return self.strategy.primary
        elif isinstance(self.strategy, StructureStrategy):
            return self.strategy.provider_name
        else:
            # For complex strategies (HybridStrategy, BenchmarkStrategy),
            # provider selection depends on runtime context
            # Return None to skip provider-specific optimization
            return None

    def get_active_provider_model(self) -> Optional[str]:
        """
        Get model name of the active provider for preprocessing.

        For strategies that can determine model without context (SingleProviderStrategy,
        StructureStrategy), returns the model name.
        For other strategies, returns None.

        Returns:
            Model name or None if determination requires runtime context
        """
        from src.transcription.routing.strategies import (
            SingleProviderStrategy,
            StructureStrategy,
        )

        # For strategies with fixed model, we can determine it synchronously
        if isinstance(self.strategy, StructureStrategy):
            return self.strategy.model
        elif isinstance(self.strategy, SingleProviderStrategy):
            # Try to get model from provider if available
            provider_name = self.strategy.provider_name
            if provider_name in self.providers:
                provider = self.providers[provider_name]
                # Check if provider has model attribute (e.g., OpenAIProvider)
                if hasattr(provider, "model"):
                    return provider.model
        return None

    async def transcribe(
        self,
        audio_path: Path,
        context: TranscriptionContext,
    ) -> TranscriptionResult:
        """
        Transcribe audio using strategy-selected provider.

        Args:
            audio_path: Path to audio file
            context: Context information for transcription

        Returns:
            TranscriptionResult with text and metrics

        Raises:
            RuntimeError: If transcription fails
        """
        # Select provider using strategy
        provider_name = await self.strategy.select_provider(context, self.providers)
        provider = self.providers[provider_name]

        self.metrics[provider_name]["requests"] += 1

        logger.info(f"Routing to provider: {provider_name}")

        try:
            result = await provider.transcribe(audio_path, context)
            self.metrics[provider_name]["total_duration"] += result.processing_time
            return result

        except Exception as e:
            self.metrics[provider_name]["errors"] += 1
            logger.error(f"Provider {provider_name} failed: {e}")

            # Try fallback if supported
            if self.strategy.supports_fallback():
                fallback_name = await self.strategy.get_fallback(provider_name)
                if fallback_name and fallback_name in self.providers:
                    logger.info(f"Attempting fallback to: {fallback_name}")
                    fallback_provider = self.providers[fallback_name]

                    try:
                        result = await fallback_provider.transcribe(audio_path, context)
                        self.metrics[fallback_name]["requests"] += 1
                        self.metrics[fallback_name]["total_duration"] += result.processing_time
                        logger.info(f"Fallback successful: {fallback_name}")
                        return result
                    except Exception as fallback_error:
                        self.metrics[fallback_name]["errors"] += 1
                        logger.error(
                            f"Fallback provider {fallback_name} also failed: {fallback_error}"
                        )

            raise

    async def run_benchmark(
        self,
        audio_path: Path,
        context: TranscriptionContext,
    ) -> BenchmarkReport:
        """
        Run transcription through all benchmark configurations.

        This method tests all configured provider/model combinations
        on the same audio file and generates a comprehensive comparison report.

        Args:
            audio_path: Path to audio file
            context: Context information for transcription

        Returns:
            BenchmarkReport with results from all configurations

        Raises:
            ValueError: If strategy is not BenchmarkStrategy
        """
        if not isinstance(self.strategy, BenchmarkStrategy):
            raise ValueError("run_benchmark() requires BenchmarkStrategy")

        results: list[TranscriptionResult] = []
        reference_text: Optional[str] = None

        logger.info(f"🔬 Starting benchmark with {len(self.strategy.configs)} configurations...")

        for i, config in enumerate(self.strategy.configs, 1):
            logger.info(f"[{i}/{len(self.strategy.configs)}] Testing: {config.display_name}")

            try:
                # Get or create provider with specific config
                provider = await self._get_provider_for_config(config)

                # Run transcription
                result = await provider.transcribe(audio_path, context)
                result.config = config

                # Store reference (OpenAI result)
                if config.provider_name == "openai" and reference_text is None:
                    reference_text = result.text

                results.append(result)

                logger.info(
                    f"✓ {config.display_name}: "
                    f"{result.processing_time:.2f}s "
                    f"(RTF: {result.realtime_factor:.2f}x)"
                )

            except Exception as e:
                logger.error(f"✗ {config.display_name} failed: {e}")
                # Create failed result
                error_result = TranscriptionResult(
                    text="",
                    language="unknown",
                    error=str(e),
                    config=config,
                    provider_used=config.provider_name,
                    model_name=config.model_size or "unknown",
                )
                results.append(error_result)

        # Generate comparison report
        report = BenchmarkReport(
            results=results,
            reference_text=reference_text,
            audio_path=audio_path,
            audio_duration=context.duration_seconds,
        )

        logger.info("✅ Benchmark complete")

        return report

    async def _get_provider_for_config(self, config: BenchmarkConfig) -> TranscriptionProvider:
        """
        Get or create provider with specific configuration.

        For benchmark mode, we may need to create multiple instances
        of same provider type with different settings.

        Args:
            config: Benchmark configuration

        Returns:
            Configured provider instance
        """
        # Generate unique key for this configuration
        provider_key = self._get_provider_key(config)

        # Check if provider already exists
        if provider_key in self._benchmark_providers:
            return self._benchmark_providers[provider_key]

        # Create new provider instance with specific config
        logger.info(f"Creating provider for benchmark: {config.display_name}")

        provider: TranscriptionProvider
        if config.provider_name == "faster-whisper":
            provider = FastWhisperProvider(
                model_size=config.model_size,
                compute_type=config.compute_type,
                beam_size=config.beam_size,
                device=config.device or "cpu",
            )
        elif config.provider_name == "openai":
            provider = OpenAIProvider()
        else:
            raise ValueError(f"Unknown provider: {config.provider_name}")

        # Initialize provider
        provider.initialize()
        self._benchmark_providers[provider_key] = provider

        return provider

    def _get_provider_key(self, config: BenchmarkConfig) -> str:
        """
        Generate unique key for provider configuration.

        Args:
            config: Benchmark configuration

        Returns:
            Unique key string
        """
        return (
            f"{config.provider_name}:"
            f"{config.model_size or 'default'}:"
            f"{config.compute_type or 'default'}:"
            f"{config.beam_size or 'default'}:"
            f"{config.device or 'default'}"
        )

    async def initialize_all(self) -> None:
        """Initialize all enabled providers."""
        logger.info("Initializing all providers...")
        for name, provider in self.providers.items():
            try:
                if not provider.is_initialized():
                    provider.initialize()
                    logger.info(f"✓ Provider '{name}' initialized successfully")
            except Exception as e:
                logger.error(f"✗ Failed to initialize provider '{name}': {e}")
                raise

    async def shutdown_all(self) -> None:
        """Shutdown all providers and cleanup resources."""
        logger.info("Shutting down all providers...")

        # Shutdown main providers
        for name, provider in self.providers.items():
            try:
                await provider.shutdown()
                logger.info(f"✓ Provider '{name}' shut down")
            except Exception as e:
                logger.error(f"✗ Error shutting down provider '{name}': {e}")

        # Shutdown benchmark providers
        for provider in self._benchmark_providers.values():
            try:
                await provider.shutdown()
            except Exception as e:
                logger.error(f"✗ Error shutting down benchmark provider: {e}")

        self._benchmark_providers.clear()
        logger.info("All providers shut down")

    def get_metrics(self) -> dict[str, dict[str, float]]:
        """
        Get usage statistics for all providers.

        Returns:
            Dictionary with metrics per provider
        """
        return {
            name: {
                **stats,
                "avg_duration": (
                    stats["total_duration"] / stats["requests"] if stats["requests"] > 0 else 0
                ),
                "error_rate": (stats["errors"] / stats["requests"] if stats["requests"] > 0 else 0),
            }
            for name, stats in self.metrics.items()
        }
