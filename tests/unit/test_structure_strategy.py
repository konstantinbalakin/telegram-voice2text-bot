"""Unit tests for StructureStrategy."""

import pytest
from unittest.mock import Mock

from src.transcription.routing.strategies import StructureStrategy
from src.transcription.models import TranscriptionContext


@pytest.fixture
def structure_strategy():
    """Create StructureStrategy instance with default settings."""
    return StructureStrategy(
        provider_name="faster-whisper",
        model="medium",
        draft_threshold_seconds=20,
        emoji_level=1,
    )


class TestStructureStrategyInit:
    """Tests for structure strategy initialization."""

    def test_strategy_creation_default(self, structure_strategy):
        """Test strategy is created with correct default parameters."""
        assert structure_strategy.provider_name == "faster-whisper"
        assert structure_strategy.model == "medium"
        assert structure_strategy.draft_threshold == 20
        assert structure_strategy.emoji_level == 1

    def test_strategy_creation_custom(self):
        """Test strategy with custom parameters."""
        strategy = StructureStrategy(
            provider_name="openai",
            model="whisper-1",
            draft_threshold_seconds=30,
            emoji_level=3,
        )
        assert strategy.provider_name == "openai"
        assert strategy.model == "whisper-1"
        assert strategy.draft_threshold == 30
        assert strategy.emoji_level == 3

    def test_strategy_creation_no_emoji(self):
        """Test strategy with no emojis."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
            emoji_level=0,
        )
        assert strategy.emoji_level == 0


class TestStructureStrategyProviderSelection:
    """Tests for provider selection logic."""

    @pytest.mark.asyncio
    async def test_select_provider_available(self, structure_strategy):
        """Test provider selection when provider is available."""
        context = TranscriptionContext(user_id=123, duration_seconds=30.0, file_size_bytes=2048)
        providers = {"faster-whisper": Mock(), "openai": Mock()}

        provider = await structure_strategy.select_provider(context, providers)

        assert provider == "faster-whisper"

    @pytest.mark.asyncio
    async def test_select_provider_not_available(self, structure_strategy):
        """Test provider selection when provider is not available."""
        context = TranscriptionContext(user_id=123, duration_seconds=30.0, file_size_bytes=2048)
        providers = {"openai": Mock()}  # faster-whisper not available

        with pytest.raises(ValueError, match="not available"):
            await structure_strategy.select_provider(context, providers)

    @pytest.mark.asyncio
    async def test_select_openai_provider(self):
        """Test selection with OpenAI provider."""
        strategy = StructureStrategy(
            provider_name="openai",
            model="whisper-1",
        )
        context = TranscriptionContext(user_id=123, duration_seconds=30.0, file_size_bytes=2048)
        providers = {"faster-whisper": Mock(), "openai": Mock()}

        provider = await strategy.select_provider(context, providers)

        assert provider == "openai"


class TestStructureStrategyModelSelection:
    """Tests for model selection."""

    def test_get_model_name(self, structure_strategy):
        """Test getting model name."""
        assert structure_strategy.get_model_name() == "medium"

    def test_get_model_name_custom(self):
        """Test getting custom model name."""
        strategy = StructureStrategy(
            provider_name="openai",
            model="whisper-1",
        )
        assert strategy.get_model_name() == "whisper-1"


class TestStructureStrategyStructuring:
    """Tests for structuring requirement logic."""

    def test_requires_structuring_long_audio(self, structure_strategy):
        """Test that structuring is required for long audio (≥20s)."""
        assert structure_strategy.requires_structuring(25.0) is True
        assert structure_strategy.requires_structuring(60.0) is True
        assert structure_strategy.requires_structuring(300.0) is True

    def test_requires_structuring_short_audio(self, structure_strategy):
        """Test that structuring is NOT required for short audio (<20s)."""
        assert structure_strategy.requires_structuring(5.0) is False
        assert structure_strategy.requires_structuring(15.0) is False
        assert structure_strategy.requires_structuring(19.9) is False

    def test_requires_structuring_at_threshold(self, structure_strategy):
        """Test structuring requirement at exact threshold."""
        assert structure_strategy.requires_structuring(20.0) is True

    def test_requires_structuring_custom_threshold(self):
        """Test structuring requirement with custom threshold."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
            draft_threshold_seconds=30,
        )
        assert strategy.requires_structuring(25.0) is False
        assert strategy.requires_structuring(30.0) is True
        assert strategy.requires_structuring(35.0) is True


class TestStructureStrategyDraftLogic:
    """Tests for draft showing logic."""

    def test_should_show_draft_long_audio(self, structure_strategy):
        """Test should show draft for long audio (≥20s)."""
        assert structure_strategy.should_show_draft(25.0) is True
        assert structure_strategy.should_show_draft(60.0) is True
        assert structure_strategy.should_show_draft(300.0) is True

    def test_should_show_draft_short_audio(self, structure_strategy):
        """Test should not show draft for short audio (<20s)."""
        assert structure_strategy.should_show_draft(5.0) is False
        assert structure_strategy.should_show_draft(15.0) is False
        assert structure_strategy.should_show_draft(19.9) is False

    def test_should_show_draft_at_threshold(self, structure_strategy):
        """Test draft showing at exact threshold."""
        assert structure_strategy.should_show_draft(20.0) is True

    def test_should_show_draft_custom_threshold(self):
        """Test draft showing with custom threshold."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
            draft_threshold_seconds=30,
        )
        assert strategy.should_show_draft(25.0) is False
        assert strategy.should_show_draft(30.0) is True
        assert strategy.should_show_draft(35.0) is True


class TestStructureStrategyEmojiLevel:
    """Tests for emoji level functionality."""

    def test_get_emoji_level_default(self, structure_strategy):
        """Test getting default emoji level."""
        assert structure_strategy.get_emoji_level() == 1

    def test_get_emoji_level_none(self):
        """Test emoji level 0 (no emojis)."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
            emoji_level=0,
        )
        assert strategy.get_emoji_level() == 0

    def test_get_emoji_level_moderate(self):
        """Test emoji level 2 (moderate)."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
            emoji_level=2,
        )
        assert strategy.get_emoji_level() == 2

    def test_get_emoji_level_many(self):
        """Test emoji level 3 (many)."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
            emoji_level=3,
        )
        assert strategy.get_emoji_level() == 3


class TestStructureStrategyEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_zero_duration(self, structure_strategy):
        """Test handling of zero duration audio."""
        assert structure_strategy.should_show_draft(0.0) is False

    @pytest.mark.asyncio
    async def test_very_long_duration(self, structure_strategy):
        """Test handling of very long audio."""
        assert structure_strategy.should_show_draft(3600.0) is True  # 1 hour

    def test_default_draft_threshold(self):
        """Test default draft threshold value."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
        )
        assert strategy.draft_threshold == 20

    def test_default_emoji_level(self):
        """Test default emoji level value."""
        strategy = StructureStrategy(
            provider_name="faster-whisper",
            model="medium",
        )
        assert strategy.emoji_level == 1
