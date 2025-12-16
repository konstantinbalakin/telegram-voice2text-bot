"""Factory for creating transcription router with configured providers and strategy."""

import logging
from typing import Optional

from src.config import settings
from src.transcription.models import BenchmarkConfig
from src.transcription.providers.base import TranscriptionProvider
from src.transcription.providers.faster_whisper_provider import FastWhisperProvider
from src.transcription.providers.openai_provider import OpenAIProvider
from src.transcription.routing.router import TranscriptionRouter
from src.transcription.routing.strategies import (
    BenchmarkStrategy,
    FallbackStrategy,
    HybridStrategy,
    RoutingStrategy,
    SingleProviderStrategy,
    StructureStrategy,
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

    # Check if we need special hybrid strategy providers
    is_hybrid_strategy = settings.whisper_routing_strategy == "hybrid"

    # For hybrid strategy, we need to create providers based on hybrid config
    # not on WHISPER_PROVIDERS list
    if is_hybrid_strategy:
        # Create OpenAI provider if enabled (for retranscription support)
        if "openai" in settings.whisper_providers:
            if not settings.openai_api_key:
                logger.warning(
                    "OpenAI provider enabled but OPENAI_API_KEY not set. "
                    "Provider will fail at initialization."
                )
            else:
                providers["openai"] = OpenAIProvider(
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    timeout=settings.openai_timeout,
                )
                logger.info(f"✓ Configured provider: openai (model={settings.openai_model})")

        # Create faster-whisper provider with retranscribe_free_model for retranscription
        if "faster-whisper" in settings.whisper_providers and settings.retranscribe_free_model:
            # Only create if model is different from draft and quality models
            free_model = settings.retranscribe_free_model
            if free_model not in [settings.hybrid_draft_model, settings.hybrid_quality_model]:
                providers[f"faster-whisper-{free_model}"] = FastWhisperProvider(
                    model_size=free_model,
                    device=settings.faster_whisper_device,
                    compute_type=settings.faster_whisper_compute_type,
                    beam_size=settings.faster_whisper_beam_size,
                    vad_filter=settings.faster_whisper_vad_filter,
                )
                logger.info(
                    f"✓ Configured provider: faster-whisper-{free_model} (for free retranscription)"
                )

        # Create draft provider
        if settings.hybrid_draft_provider == "faster-whisper":
            providers["faster-whisper-draft"] = FastWhisperProvider(
                model_size=settings.hybrid_draft_model,
                device=settings.faster_whisper_device,
                compute_type=settings.faster_whisper_compute_type,
                beam_size=settings.faster_whisper_beam_size,
                vad_filter=settings.faster_whisper_vad_filter,
            )
            logger.info(
                f"✓ Configured provider: faster-whisper-draft "
                f"(model={settings.hybrid_draft_model})"
            )
        elif settings.hybrid_draft_provider == "openai":
            if not settings.openai_api_key:
                logger.warning(
                    "OpenAI draft provider enabled but OPENAI_API_KEY not set. "
                    "Provider will fail at initialization."
                )
            providers["openai-draft"] = OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.hybrid_draft_model,
                timeout=settings.openai_timeout,
            )
            logger.info(
                f"✓ Configured provider: openai-draft (model={settings.hybrid_draft_model})"
            )

        # Create quality provider
        if settings.hybrid_quality_provider == "faster-whisper":
            providers["faster-whisper-quality"] = FastWhisperProvider(
                model_size=settings.hybrid_quality_model,
                device=settings.faster_whisper_device,
                compute_type=settings.faster_whisper_compute_type,
                beam_size=settings.faster_whisper_beam_size,
                vad_filter=settings.faster_whisper_vad_filter,
            )
            logger.info(
                f"✓ Configured provider: faster-whisper-quality "
                f"(model={settings.hybrid_quality_model})"
            )
        elif settings.hybrid_quality_provider == "openai":
            if not settings.openai_api_key:
                logger.warning(
                    "OpenAI quality provider enabled but OPENAI_API_KEY not set. "
                    "Provider will fail at initialization."
                )
            providers["openai-quality"] = OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.hybrid_quality_model,
                timeout=settings.openai_timeout,
            )
            logger.info(
                f"✓ Configured provider: openai-quality (model={settings.hybrid_quality_model})"
            )

    # For non-hybrid strategies, create providers from WHISPER_PROVIDERS list
    else:
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

    elif strategy_name == "hybrid":
        # Hybrid strategy: duration-based routing
        # Map logical provider names to actual provider instances
        draft_provider_base = settings.hybrid_draft_provider
        quality_provider_base = settings.hybrid_quality_provider
        short_threshold = settings.hybrid_short_threshold

        # Determine actual provider names based on configuration
        if draft_provider_base == "faster-whisper":
            draft_provider_name = "faster-whisper-draft"
        elif draft_provider_base == "openai":
            draft_provider_name = "openai-draft"
        else:
            draft_provider_name = draft_provider_base

        if quality_provider_base == "faster-whisper":
            quality_provider_name = "faster-whisper-quality"
        elif quality_provider_base == "openai":
            quality_provider_name = "openai-quality"
        else:
            quality_provider_name = quality_provider_base

        # Validate quality provider exists (required)
        if quality_provider_name not in providers:
            raise ValueError(
                f"Quality provider '{quality_provider_name}' not available. "
                f"Available: {list(providers.keys())}"
            )

        # Check if draft provider is available
        if draft_provider_name not in providers:
            logger.warning(
                f"Draft provider '{draft_provider_name}' not available. "
                f"Using quality provider '{quality_provider_name}' for all audio."
            )
            # Fallback: use quality provider for both short and long audio
            draft_provider_name = quality_provider_name

        strategy = HybridStrategy(
            short_threshold=short_threshold,
            draft_provider_name=draft_provider_name,
            draft_model=settings.hybrid_draft_model,
            quality_provider_name=quality_provider_name,
            quality_model=settings.hybrid_quality_model,
        )
        logger.info(
            f"✓ Hybrid strategy: short(<{short_threshold}s)={quality_provider_name}/{settings.hybrid_quality_model}, "
            f"long(>={short_threshold}s)={draft_provider_name}/{settings.hybrid_draft_model}"
        )

    elif strategy_name == "structure":
        # Validate LLM is enabled
        if not settings.llm_refinement_enabled:
            raise ValueError(
                "StructureStrategy requires LLM to be enabled. "
                "Set LLM_REFINEMENT_ENABLED=true in .env"
            )

        provider_name = settings.structure_provider
        model_name = settings.structure_model

        logger.info(
            f"Creating StructureStrategy: provider={provider_name}, "
            f"model={model_name}, "
            f"draft_threshold={settings.structure_draft_threshold}s, "
            f"emoji_level={settings.structure_emoji_level}"
        )

        # For structure strategy, create provider based on configured provider
        # (similar to single strategy, but we don't use the WHISPER_PROVIDERS list)
        if provider_name not in providers:
            # Provider not yet created, create it now
            if provider_name == "faster-whisper":
                providers["faster-whisper"] = FastWhisperProvider(
                    model_size=model_name,
                    device=settings.faster_whisper_device,
                    compute_type=settings.faster_whisper_compute_type,
                    beam_size=settings.faster_whisper_beam_size,
                    vad_filter=settings.faster_whisper_vad_filter,
                )
                providers["faster-whisper"].initialize()
                logger.info(f"✓ Configured provider: faster-whisper (model={model_name})")
            elif provider_name == "openai":
                if not settings.openai_api_key:
                    raise ValueError("OpenAI provider configured but OPENAI_API_KEY not set")
                providers["openai"] = OpenAIProvider(
                    api_key=settings.openai_api_key,
                    model=model_name,
                    timeout=settings.openai_timeout,
                )
                providers["openai"].initialize()
                logger.info(f"✓ Configured provider: openai (model={model_name})")
            else:
                raise ValueError(
                    f"Unknown provider '{provider_name}' for structure strategy. "
                    f"Supported: faster-whisper, openai"
                )

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
            fallback_provider_name=fallback_provider,
        )
        logger.info(
            f"✓ Structure strategy: provider={provider_name}, model={model_name}, "
            f"draft_threshold={settings.structure_draft_threshold}s, "
            f"emoji_level={settings.structure_emoji_level}"
        )

    else:
        raise ValueError(
            f"Unknown routing strategy: {strategy_name}. "
            f"Supported: single, fallback, benchmark, hybrid, structure"
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
