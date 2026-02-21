"""Unit tests for long text processing strategies in TextProcessor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.text_processor import TextProcessor
from src.services.llm_service import LLMResult, LLMService


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service with deepseek-chat provider."""
    service = MagicMock(spec=LLMService)
    service.provider = MagicMock()
    service.provider.model = "deepseek-chat"
    service.provider.max_tokens = 8192
    return service


@pytest.fixture
def text_processor(mock_llm_service):
    """Create TextProcessor with mock LLM service."""
    return TextProcessor(mock_llm_service)


class TestLongTextStrategy:
    """Tests for long text handling strategies."""

    @pytest.mark.asyncio
    async def test_short_text_no_strategy_applied(self, text_processor, mock_llm_service):
        """Test: short text is processed normally without any strategy."""
        mock_llm_service.provider.refine_text = AsyncMock(
            return_value=LLMResult(text="Structured short text.")
        )

        result = await text_processor.create_structured("Short text.", emoji_level=0)
        assert result == "Structured short text."
        # refine_text called exactly once (no chunking)
        mock_llm_service.provider.refine_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_summary_mode_bypasses_strategy(self, text_processor, mock_llm_service):
        """Test: summary mode never uses chunking/reasoner strategy."""
        long_text = "а" * 30000  # Very long text

        mock_llm_service.provider.refine_text = AsyncMock(
            return_value=LLMResult(text="Summary of the text.")
        )

        result = await text_processor.summarize_text(long_text)
        assert result == "Summary of the text."
        # Only 1 call — no chunking applied for summary
        mock_llm_service.provider.refine_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_reasoner_model_bypasses_strategy(self, text_processor, mock_llm_service):
        """Test: deepseek-reasoner model never uses chunking strategy."""
        mock_llm_service.provider.model = "deepseek-reasoner"
        mock_llm_service.provider.max_tokens = 64000
        long_text = "а" * 30000

        mock_llm_service.provider.refine_text = AsyncMock(
            return_value=LLMResult(text="Full result from reasoner.")
        )

        result = await text_processor.create_structured(long_text, emoji_level=0)
        assert result == "Full result from reasoner."
        mock_llm_service.provider.refine_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_chunking_strategy_splits_long_text(self, text_processor, mock_llm_service):
        """Test: chunking strategy splits long text and processes each chunk."""
        # Configure for chunking
        text_processor.long_text_strategy = "chunking"
        text_processor.chunk_max_chars = 8000

        # Create text that will trigger chunking (~50000 chars > 8192 tokens)
        long_text = "Это длинное предложение. " * 2500  # ~60000 chars

        call_count = 0

        async def mock_refine(text: str, prompt: str) -> LLMResult:
            nonlocal call_count
            call_count += 1
            return LLMResult(text=f"Chunk {call_count} processed.")

        mock_llm_service.provider.refine_text = mock_refine

        result = await text_processor.create_structured(long_text, emoji_level=0)

        # Should have been called multiple times (chunked)
        assert call_count > 1
        # Result should contain all chunks merged
        assert "Chunk 1 processed." in result

    @pytest.mark.asyncio
    async def test_reasoner_strategy_for_long_text(self, text_processor, mock_llm_service):
        """Test: reasoner strategy switches to deepseek-reasoner for long texts."""
        text_processor.long_text_strategy = "reasoner"

        long_text = "Предложение для теста. " * 3000  # ~66000 chars

        original_refine = AsyncMock(return_value=LLMResult(text="Reasoner result."))
        mock_llm_service.provider.refine_text = original_refine

        with patch("src.services.text_processor.DeepSeekProvider") as mock_provider_class:
            reasoner_provider = AsyncMock()
            reasoner_provider.refine_text = AsyncMock(
                return_value=LLMResult(text="Reasoner result.")
            )
            reasoner_provider.close = AsyncMock()
            mock_provider_class.return_value = reasoner_provider

            result = await text_processor.create_structured(long_text, emoji_level=0)

        assert "Reasoner result." in result
