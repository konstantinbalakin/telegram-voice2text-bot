"""Unit tests for TextProcessor create_magic method."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.text_processor import TextProcessor
from src.services.llm_service import LLMResult, LLMService


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service."""
    service = MagicMock(spec=LLMService)
    service.provider = MagicMock()
    service.provider.model = "deepseek-chat"
    service.provider.max_tokens = 8192
    return service


@pytest.fixture
def text_processor(mock_llm_service: MagicMock) -> TextProcessor:
    """Create TextProcessor with mock LLM service."""
    return TextProcessor(mock_llm_service)


class TestCreateMagicFallbackPrompt:
    """Test that fallback prompt uses Markdown, not HTML."""

    @pytest.mark.asyncio
    async def test_fallback_prompt_uses_markdown_not_html(
        self, text_processor: TextProcessor, mock_llm_service: MagicMock
    ) -> None:
        """When prompt file fails to load, fallback must use Markdown instructions."""
        mock_llm_service.provider.refine_text = AsyncMock(return_value=LLMResult(text="result"))

        with patch(
            "src.services.text_processor.load_prompt", side_effect=FileNotFoundError("not found")
        ):
            await text_processor.create_magic("test text")

        # Verify the prompt was passed to refine_text
        call_args = mock_llm_service.provider.refine_text.call_args
        prompt_sent = call_args[0][1]  # second positional arg is the prompt

        # Must NOT contain HTML formatting instructions
        assert "<b>" not in prompt_sent, "Fallback prompt still contains HTML <b> tag"
        assert "<i>" not in prompt_sent, "Fallback prompt still contains HTML <i> tag"
        assert "<code>" not in prompt_sent, "Fallback prompt still contains HTML <code> tag"
        assert (
            "HTML-форматирование" not in prompt_sent
        ), "Fallback prompt still instructs to use HTML formatting"

        # Must contain Markdown formatting instructions
        assert "Markdown" in prompt_sent, "Fallback prompt should reference Markdown formatting"
