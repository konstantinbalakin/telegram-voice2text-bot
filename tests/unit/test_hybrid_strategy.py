"""Unit tests for HybridStrategy."""

import pytest
from unittest.mock import Mock

from src.transcription.routing.strategies import HybridStrategy
from src.transcription.models import TranscriptionContext


@pytest.fixture
def hybrid_strategy():
    """Create HybridStrategy instance with 20s threshold."""
    return HybridStrategy(
        short_threshold=20,
        draft_provider_name="faster-whisper",
        draft_model="small",
        quality_provider_name="faster-whisper",
        quality_model="medium",
    )


class TestHybridStrategyInit:
    """Tests for hybrid strategy initialization."""

    def test_strategy_creation(self, hybrid_strategy):
        """Test strategy is created with correct parameters."""
        assert hybrid_strategy.short_threshold == 20
        assert hybrid_strategy.draft_provider == "faster-whisper"
        assert hybrid_strategy.draft_model == "small"
        assert hybrid_strategy.quality_provider == "faster-whisper"
        assert hybrid_strategy.quality_model == "medium"


class TestHybridStrategyRouting:
    """Tests for provider selection logic."""

    @pytest.mark.asyncio
    async def test_short_audio_uses_quality_provider(self, hybrid_strategy):
        """Test short audio (<20s) routes to quality provider."""
        context = TranscriptionContext(user_id=123, duration_seconds=15.0, file_size_bytes=1024)
        providers = {"faster-whisper": Mock()}

        provider = await hybrid_strategy.select_provider(context, providers)

        assert provider == "faster-whisper"

    @pytest.mark.asyncio
    async def test_long_audio_uses_draft_provider(self, hybrid_strategy):
        """Test long audio (>=20s) routes to draft provider."""
        context = TranscriptionContext(user_id=123, duration_seconds=60.0, file_size_bytes=5120)
        providers = {"faster-whisper": Mock()}

        provider = await hybrid_strategy.select_provider(context, providers)

        assert provider == "faster-whisper"

    @pytest.mark.asyncio
    async def test_threshold_boundary_exact(self, hybrid_strategy):
        """Test audio exactly at threshold routes to draft provider."""
        context = TranscriptionContext(user_id=123, duration_seconds=20.0, file_size_bytes=2048)
        providers = {"faster-whisper": Mock()}

        provider = await hybrid_strategy.select_provider(context, providers)

        assert provider == "faster-whisper"

    @pytest.mark.asyncio
    async def test_threshold_boundary_just_below(self, hybrid_strategy):
        """Test audio just below threshold routes to quality provider."""
        context = TranscriptionContext(user_id=123, duration_seconds=19.9, file_size_bytes=2048)
        providers = {"faster-whisper": Mock()}

        provider = await hybrid_strategy.select_provider(context, providers)

        assert provider == "faster-whisper"

    @pytest.mark.asyncio
    async def test_threshold_boundary_just_above(self, hybrid_strategy):
        """Test audio just above threshold routes to draft provider."""
        context = TranscriptionContext(user_id=123, duration_seconds=20.1, file_size_bytes=2048)
        providers = {"faster-whisper": Mock()}

        provider = await hybrid_strategy.select_provider(context, providers)

        assert provider == "faster-whisper"


class TestHybridStrategyModelSelection:
    """Tests for model selection based on duration."""

    def test_get_model_for_short_duration(self, hybrid_strategy):
        """Test model selection for short audio."""
        model = hybrid_strategy.get_model_for_duration(15.0)
        assert model == "medium"

    def test_get_model_for_long_duration(self, hybrid_strategy):
        """Test model selection for long audio."""
        model = hybrid_strategy.get_model_for_duration(60.0)
        assert model == "small"

    def test_get_model_at_threshold(self, hybrid_strategy):
        """Test model selection at exact threshold."""
        model = hybrid_strategy.get_model_for_duration(20.0)
        assert model == "small"


class TestHybridStrategyRefinement:
    """Tests for refinement requirement logic."""

    def test_short_audio_no_refinement(self, hybrid_strategy):
        """Test short audio doesn't require refinement."""
        requires = hybrid_strategy.requires_refinement(15.0)
        assert requires is False

    def test_long_audio_requires_refinement(self, hybrid_strategy):
        """Test long audio requires refinement."""
        requires = hybrid_strategy.requires_refinement(60.0)
        assert requires is True

    def test_threshold_boundary_refinement(self, hybrid_strategy):
        """Test refinement requirement at threshold."""
        requires = hybrid_strategy.requires_refinement(20.0)
        assert requires is True

    def test_very_short_audio_no_refinement(self, hybrid_strategy):
        """Test very short audio doesn't require refinement."""
        requires = hybrid_strategy.requires_refinement(5.0)
        assert requires is False

    def test_very_long_audio_requires_refinement(self, hybrid_strategy):
        """Test very long audio requires refinement."""
        requires = hybrid_strategy.requires_refinement(300.0)
        assert requires is True


class TestHybridStrategyWithDifferentProviders:
    """Tests for hybrid strategy with different provider configurations."""

    @pytest.mark.asyncio
    async def test_openai_draft_provider(self):
        """Test hybrid strategy with OpenAI as draft provider."""
        strategy = HybridStrategy(
            short_threshold=20,
            draft_provider_name="openai",
            draft_model="whisper-1",
            quality_provider_name="faster-whisper",
            quality_model="medium",
        )

        context_short = TranscriptionContext(
            user_id=123, duration_seconds=15.0, file_size_bytes=1024
        )
        context_long = TranscriptionContext(
            user_id=123, duration_seconds=60.0, file_size_bytes=5120
        )

        providers = {"faster-whisper": Mock(), "openai": Mock()}

        # Short audio uses quality provider
        provider_short = await strategy.select_provider(context_short, providers)
        assert provider_short == "faster-whisper"

        # Long audio uses draft provider
        provider_long = await strategy.select_provider(context_long, providers)
        assert provider_long == "openai"

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        """Test hybrid strategy with custom threshold."""
        strategy = HybridStrategy(
            short_threshold=30,  # 30s threshold
            draft_provider_name="faster-whisper",
            draft_model="tiny",
            quality_provider_name="faster-whisper",
            quality_model="large",
        )

        context_25s = TranscriptionContext(user_id=123, duration_seconds=25.0, file_size_bytes=2048)

        providers = {"faster-whisper": Mock()}

        # 25s is below 30s threshold, should use quality model
        provider = await strategy.select_provider(context_25s, providers)
        assert provider == "faster-whisper"
        assert strategy.get_model_for_duration(25.0) == "large"

        # 35s is above threshold, should use draft model
        assert strategy.get_model_for_duration(35.0) == "tiny"
