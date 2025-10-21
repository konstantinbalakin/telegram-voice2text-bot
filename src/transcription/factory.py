"""Factory for creating transcription router with configured providers and strategy."""

import logging
from typing import Optional

from src.config import settings
from src.transcription.models import BenchmarkConfig
from src.transcription.providers.base import TranscriptionProvider
from src.transcription.providers.faster_whisper_provider import FastWhisperProvider
from src.transcription.providers.openai_provider import OpenAIProvider
from src.transcription.providers.whisper_provider import WhisperProvider
from src.transcription.routing.router import TranscriptionRouter
from src.transcription.routing.strategies import (
    BenchmarkStrategy,
    FallbackStrategy,
    RoutingStrategy,
    SingleProviderStrategy,
)

logger = logging.getLogger(__name__)


def create_transcription_router() -> TranscriptionRouter:
    """
    Create transcription router with configured providers and strategy.

    Returns:
        Configured TranscriptionRouter instance

    Raises:
        ValueError: If configuration is invalid
    """
    logger.info("Creating transcription router...")

    # Initialize enabled providers
    providers: dict[str, TranscriptionProvider] = {}

    for provider_name in settings.whisper_providers:
        try:
            if provider_name == "faster-whisper":
                providers["faster-whisper"] = FastWhisperProvider(
                    model_size=settings.faster_whisper_model_size,
                    device=settings.faster_whisper_device,
                    compute_type=settings.faster_whisper_compute_type,
                    beam_size=settings.faster_whisper_beam_size,
                    vad_filter=settings.faster_whisper_vad_filter,
                )
                logger.info(
                    f"✓ Configured provider: faster-whisper "
                    f"(model={settings.faster_whisper_model_size})"
                )

            elif provider_name == "openai":
                if not settings.openai_api_key:
                    logger.warning(
                        "OpenAI provider enabled but OPENAI_API_KEY not set. "
                        "Provider will fail at initialization."
                    )
                providers["openai"] = OpenAIProvider(
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    timeout=settings.openai_timeout,
                )
                logger.info(f"✓ Configured provider: openai (model={settings.openai_model})")

            elif provider_name == "whisper":
                providers["whisper"] = WhisperProvider(
                    model_size=settings.whisper_model_size,
                    device=settings.whisper_device,
                )
                logger.info(f"✓ Configured provider: whisper (model={settings.whisper_model_size})")

            else:
                logger.warning(f"Unknown provider: {provider_name}")

        except ImportError as e:
            logger.warning(f"Skipping provider '{provider_name}': {e}")
            continue
        except Exception as e:
            logger.error(f"Failed to configure provider '{provider_name}': {e}")
            raise

    if not providers:
        raise ValueError("No providers configured. Check WHISPER_PROVIDERS setting.")

    logger.info(f"Successfully configured {len(providers)} provider(s): {list(providers.keys())}")

    # Initialize providers first (except in benchmark mode - they're initialized on demand)
    if not settings.benchmark_mode:
        logger.info("Initializing providers...")
        initialized_providers = {}
        for name, provider in providers.items():
            try:
                provider.initialize()
                logger.info(f"✓ Provider '{name}' initialized")
                initialized_providers[name] = provider
            except Exception as e:
                logger.error(f"✗ Failed to initialize provider '{name}': {e}")
                logger.warning(f"Skipping provider '{name}' due to initialization failure")

        # Update providers dict with only successfully initialized ones
        providers = initialized_providers

        logger.info(
            f"Successfully initialized {len(providers)} provider(s): {list(providers.keys())}"
        )

        if not providers:
            raise ValueError(
                "No providers successfully initialized. Check your configuration and dependencies."
            )
    else:
        logger.info(
            "Benchmark mode enabled - providers will be initialized on demand during benchmark"
        )

    # Create routing strategy with initialized providers
    strategy = _create_routing_strategy(providers)

    # Create router
    router = TranscriptionRouter(providers=providers, strategy=strategy)

    logger.info("Transcription router created successfully")
    return router


def _create_routing_strategy(providers: dict[str, TranscriptionProvider]) -> RoutingStrategy:
    """
    Create routing strategy based on configuration.

    Args:
        providers: Available providers

    Returns:
        Configured routing strategy

    Raises:
        ValueError: If strategy configuration is invalid
    """
    strategy_name = settings.whisper_routing_strategy

    logger.info(f"Creating routing strategy: {strategy_name}")

    strategy: RoutingStrategy
    if strategy_name == "single":
        primary = settings.primary_provider
        if primary not in providers:
            # Auto-select first available provider if configured one is not available
            available_providers = list(providers.keys())
            if not available_providers:
                raise ValueError("No providers available for single provider strategy")
            primary = available_providers[0]
            logger.warning(
                f"Configured primary provider '{settings.primary_provider}' not available. "
                f"Using '{primary}' instead."
            )
        strategy = SingleProviderStrategy(provider_name=primary)
        logger.info(f"✓ Single provider strategy: {primary}")

    elif strategy_name == "fallback":
        primary = settings.primary_provider
        fallback = settings.fallback_provider

        if primary not in providers:
            # Auto-select first available provider
            available_providers = list(providers.keys())
            if not available_providers:
                raise ValueError("No providers available for fallback strategy")
            primary = available_providers[0]
            logger.warning(
                f"Configured primary provider '{settings.primary_provider}' not available. "
                f"Using '{primary}' instead."
            )

        if fallback not in providers:
            # Auto-select second provider or same as primary if only one available
            available_providers = [p for p in providers.keys() if p != primary]
            if available_providers:
                fallback = available_providers[0]
                logger.warning(
                    f"Configured fallback provider '{settings.fallback_provider}' not available. "
                    f"Using '{fallback}' instead."
                )
            else:
                logger.warning(
                    f"No fallback provider available. Fallback strategy will use only '{primary}'."
                )
                fallback = primary

        strategy = FallbackStrategy(primary=primary, fallback=fallback)
        logger.info(f"✓ Fallback strategy: {primary} → {fallback}")

    elif strategy_name == "benchmark":
        if not settings.benchmark_mode:
            raise ValueError("Benchmark strategy requires BENCHMARK_MODE=true")

        # Parse benchmark configs
        benchmark_configs = [BenchmarkConfig(**config) for config in settings.benchmark_configs]

        strategy = BenchmarkStrategy(benchmark_configs=benchmark_configs)
        logger.info(f"✓ Benchmark strategy: {len(benchmark_configs)} configurations")

    else:
        raise ValueError(
            f"Unknown routing strategy: {strategy_name}. " f"Supported: single, fallback, benchmark"
        )

    return strategy


# Global instance
_router_instance: Optional[TranscriptionRouter] = None


def get_transcription_router() -> TranscriptionRouter:
    """
    Get or create global transcription router instance.

    Returns:
        Global TranscriptionRouter instance
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = create_transcription_router()
    return _router_instance


async def shutdown_transcription_router() -> None:
    """Shutdown global transcription router and cleanup resources."""
    global _router_instance
    if _router_instance is not None:
        logger.info("Shutting down transcription router...")
        await _router_instance.shutdown_all()
        _router_instance = None
        logger.info("Transcription router shut down")
