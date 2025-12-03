"""Unit tests for TextProcessor length adjustment methods (Phase 3)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.text_processor import TextProcessor
from src.services.llm_service import LLMService, LLMError


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    service = MagicMock(spec=LLMService)
    service.provider = MagicMock()
    return service


@pytest.fixture
def text_processor(mock_llm_service):
    """Create TextProcessor with mock LLM service."""
    return TextProcessor(mock_llm_service)


class TestAdjustLength:
    """Test adjust_length method."""

    @pytest.mark.asyncio
    async def test_adjust_length_shorter(self, text_processor, mock_llm_service):
        """Test making text shorter."""
        original_text = "This is a longer text that needs to be shortened."
        expected_shortened = "This is shorter text."

        mock_llm_service.provider.refine_text = AsyncMock(return_value=expected_shortened)

        result = await text_processor.adjust_length(
            current_text=original_text,
            direction="shorter",
            current_level="default",
            mode="structured",
        )

        assert result == expected_shortened
        mock_llm_service.provider.refine_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_adjust_length_longer(self, text_processor, mock_llm_service):
        """Test making text longer."""
        original_text = "Short text."
        expected_longer = "This is a much longer and more detailed text."

        mock_llm_service.provider.refine_text = AsyncMock(return_value=expected_longer)

        result = await text_processor.adjust_length(
            current_text=original_text,
            direction="longer",
            current_level="default",
            mode="structured",
        )

        assert result == expected_longer
        mock_llm_service.provider.refine_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_adjust_length_invalid_direction(self, text_processor):
        """Test invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="Invalid direction"):
            await text_processor.adjust_length(
                current_text="Some text",
                direction="invalid",
                current_level="default",
                mode="structured",
            )

    @pytest.mark.asyncio
    async def test_adjust_length_llm_error_fallback(self, text_processor, mock_llm_service):
        """Test fallback to original text on LLM error."""
        original_text = "Text to adjust"
        mock_llm_service.provider.refine_text = AsyncMock(side_effect=LLMError("API Error"))

        result = await text_processor.adjust_length(
            current_text=original_text,
            direction="shorter",
            current_level="default",
            mode="structured",
        )

        # Should fallback to original text
        assert result == original_text


class TestMakeShorter:
    """Test make_shorter convenience method."""

    @pytest.mark.asyncio
    async def test_make_shorter(self, text_processor, mock_llm_service):
        """Test make_shorter wrapper."""
        original_text = "Long text to shorten"
        expected_shortened = "Short text"

        mock_llm_service.provider.refine_text = AsyncMock(return_value=expected_shortened)

        result = await text_processor.make_shorter(
            current_text=original_text, current_level="default", mode="structured"
        )

        assert result == expected_shortened
        mock_llm_service.provider.refine_text.assert_called_once()


class TestMakeLonger:
    """Test make_longer convenience method."""

    @pytest.mark.asyncio
    async def test_make_longer(self, text_processor, mock_llm_service):
        """Test make_longer wrapper."""
        original_text = "Short text"
        expected_longer = "Much longer and more detailed text"

        mock_llm_service.provider.refine_text = AsyncMock(return_value=expected_longer)

        result = await text_processor.make_longer(
            current_text=original_text, current_level="default", mode="structured"
        )

        assert result == expected_longer
        mock_llm_service.provider.refine_text.assert_called_once()


class TestLengthLevels:
    """Test all 5 length levels: shorter, short, default, long, longer."""

    @pytest.mark.parametrize(
        "level,direction,expected_prompt_keyword",
        [
            ("default", "shorter", "сократить"),
            ("default", "longer", "расширить"),
            ("short", "shorter", "сократить"),
            ("long", "longer", "расширить"),
        ],
    )
    @pytest.mark.asyncio
    async def test_different_levels_and_directions(
        self, text_processor, mock_llm_service, level, direction, expected_prompt_keyword
    ):
        """Test adjust_length with different starting levels."""
        original_text = "Test text for level transitions"
        result_text = f"Adjusted text from {level} going {direction}"

        mock_llm_service.provider.refine_text = AsyncMock(return_value=result_text)

        result = await text_processor.adjust_length(
            current_text=original_text,
            direction=direction,
            current_level=level,
            mode="structured",
        )

        assert result == result_text
        # Verify the prompt contains expected keyword
        call_args = mock_llm_service.provider.refine_text.call_args
        prompt = call_args[0][1]  # Second argument is the prompt
        assert expected_prompt_keyword in prompt.lower()


class TestModeSupport:
    """Test length adjustment for different modes (structured/summary)."""

    @pytest.mark.parametrize("mode", ["structured", "summary"])
    @pytest.mark.asyncio
    async def test_adjust_length_different_modes(self, text_processor, mock_llm_service, mode):
        """Test that adjust_length works with both structured and summary modes."""
        original_text = "Text in mode"
        adjusted_text = f"Adjusted text for {mode} mode"

        mock_llm_service.provider.refine_text = AsyncMock(return_value=adjusted_text)

        result = await text_processor.adjust_length(
            current_text=original_text,
            direction="shorter",
            current_level="default",
            mode=mode,
        )

        assert result == adjusted_text
        # Verify mode is in the prompt
        call_args = mock_llm_service.provider.refine_text.call_args
        prompt = call_args[0][1]
        assert mode in prompt.lower()


class TestPromptLoading:
    """Test prompt loading from files with fallback."""

    @pytest.mark.asyncio
    async def test_uses_fallback_prompts(self, text_processor, mock_llm_service):
        """Test that fallback inline prompts work when files don't exist."""
        # Prompts will fallback to inline versions since files don't exist
        original_text = "Text to adjust"
        adjusted_text = "Adjusted text"

        mock_llm_service.provider.refine_text = AsyncMock(return_value=adjusted_text)

        result = await text_processor.adjust_length(
            current_text=original_text,
            direction="shorter",
            current_level="default",
            mode="structured",
        )

        assert result == adjusted_text
        # Verify refine_text was called with a prompt
        assert mock_llm_service.provider.refine_text.called
