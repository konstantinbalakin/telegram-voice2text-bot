"""Unit tests for long text processing strategies in TextProcessor."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.text_processor import TextProcessor
from src.services.llm_service import DeepSeekProvider, LLMError, LLMResult, LLMService


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service with deepseek-chat provider."""
    service = MagicMock(spec=LLMService)
    service.provider = MagicMock(spec=DeepSeekProvider)
    service.provider.model = "deepseek-chat"
    service.provider.max_tokens = 8192
    service.provider.output_capacity = 8192
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
    async def test_magic_mode_bypasses_strategy(self, text_processor, mock_llm_service):
        """Test: magic mode never uses chunking/reasoner strategy."""
        long_text = "а" * 30000  # Very long text

        mock_llm_service.provider.refine_text = AsyncMock(
            return_value=LLMResult(text="Magic result.")
        )

        result = await text_processor.create_magic(long_text)
        assert result == "Magic result."
        # Only 1 call — no chunking applied for magic
        mock_llm_service.provider.refine_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_reasoner_model_bypasses_strategy(self, text_processor, mock_llm_service):
        """Test: deepseek-reasoner model never uses chunking strategy."""
        mock_llm_service.provider.model = "deepseek-reasoner"
        mock_llm_service.provider.max_tokens = 64000
        mock_llm_service.provider.output_capacity = 64000
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
    async def test_chunking_prompt_contains_chunk_not_full_text(
        self, text_processor, mock_llm_service
    ):
        """Test: when chunking, the system prompt contains chunk text, not full text."""
        text_processor.long_text_strategy = "chunking"
        text_processor.chunk_max_chars = 8000

        long_text = "Первое предложение. " * 1000 + "Второе предложение. " * 1000

        prompts_received: list[str] = []

        async def mock_refine(text: str, prompt: str) -> LLMResult:
            prompts_received.append(prompt)
            return LLMResult(text=text)

        mock_llm_service.provider.refine_text = mock_refine

        await text_processor.create_structured(long_text, emoji_level=0)

        # Each prompt should NOT contain the full original text
        for prompt in prompts_received:
            assert long_text not in prompt, "Chunk prompt should not contain full original text"

    @pytest.mark.asyncio
    async def test_output_capacity_separate_from_max_tokens(self, mock_llm_service):
        """Test: low max_tokens with high output_capacity does not trigger chunking."""
        mock_llm_service.provider.max_tokens = 80  # low API limit
        mock_llm_service.provider.output_capacity = 8192  # high chunking threshold

        tp = TextProcessor(mock_llm_service, long_text_strategy="chunking")

        # 500 chars ~ 167 tokens, below output_capacity=8192
        text = "Тестовое предложение. " * 25
        assert not tp._needs_long_text_strategy(text)

    @pytest.mark.asyncio
    async def test_low_output_capacity_triggers_chunking(self, mock_llm_service):
        """Test: low output_capacity triggers chunking even with high max_tokens."""
        mock_llm_service.provider.max_tokens = 8192  # high API limit
        mock_llm_service.provider.output_capacity = 80  # low chunking threshold

        tp = TextProcessor(mock_llm_service, long_text_strategy="chunking")

        # 500 chars ~ 167 tokens, above output_capacity=80
        text = "Тестовое предложение. " * 25
        assert tp._needs_long_text_strategy(text)

    @pytest.mark.asyncio
    async def test_reasoner_strategy_for_long_text(self, text_processor, mock_llm_service):
        """Test: reasoner strategy routes long texts to _process_with_reasoner."""
        text_processor.long_text_strategy = "reasoner"

        long_text = "Предложение для теста. " * 3000  # ~66000 chars

        with patch.object(
            text_processor,
            "_process_with_reasoner",
            new=AsyncMock(return_value=LLMResult(text="Reasoner result.")),
        ):
            result = await text_processor.create_structured(long_text, emoji_level=0)

        assert "Reasoner result." in result


class TestParallelChunking:
    """Tests for parallel LLM chunk processing."""

    @pytest.mark.asyncio
    async def test_parallel_chunking_processes_all_chunks(self, mock_llm_service):
        """Test: parallel chunking processes all chunks and merges correctly."""
        tp = TextProcessor(
            mock_llm_service,
            long_text_strategy="chunking",
            chunk_max_chars=8000,
            parallel_chunks=True,
            max_parallel_chunks=3,
        )
        long_text = "Это длинное предложение. " * 2500  # ~60000 chars

        call_count = 0

        async def mock_refine(text: str, prompt: str) -> LLMResult:
            nonlocal call_count
            call_count += 1
            return LLMResult(text=f"Chunk {call_count} done.")

        mock_llm_service.provider.refine_text = mock_refine

        result = await tp.create_structured(long_text, emoji_level=0)
        assert call_count > 1
        assert "done." in result

    @pytest.mark.asyncio
    async def test_parallel_chunking_preserves_order(self, mock_llm_service):
        """Test: parallel chunks are merged in correct order despite varying delays."""
        tp = TextProcessor(
            mock_llm_service,
            long_text_strategy="chunking",
            chunk_max_chars=8000,
            parallel_chunks=True,
            max_parallel_chunks=10,
        )
        long_text = "Слово слово слово. " * 3000

        chunk_index_tracker: list[int] = []
        chunk_counter = 0

        async def mock_refine(text: str, prompt: str) -> LLMResult:
            nonlocal chunk_counter
            idx = chunk_counter
            chunk_counter += 1
            # Earlier chunks get longer delay to test ordering
            await asyncio.sleep(0.05 * (3 - min(idx, 3)))
            chunk_index_tracker.append(idx)
            return LLMResult(text=f"[CHUNK-{idx}]")

        mock_llm_service.provider.refine_text = mock_refine

        result = await tp.create_structured(long_text, emoji_level=0)
        # Chunks may complete out of order, but result must be ordered
        parts = result.split("\n\n")
        for i, part in enumerate(parts):
            assert f"[CHUNK-{i}]" == part

    @pytest.mark.asyncio
    async def test_sequential_chunking_when_parallel_disabled(self, mock_llm_service):
        """Test: sequential processing when parallel_chunks=False."""
        tp = TextProcessor(
            mock_llm_service,
            long_text_strategy="chunking",
            chunk_max_chars=8000,
            parallel_chunks=False,
        )
        long_text = "Это текст для теста. " * 3000

        call_order: list[int] = []

        async def mock_refine(text: str, prompt: str) -> LLMResult:
            idx = len(call_order)
            call_order.append(idx)
            return LLMResult(text=f"Result {idx}")

        mock_llm_service.provider.refine_text = mock_refine

        await tp.create_structured(long_text, emoji_level=0)
        assert len(call_order) > 1
        # Sequential: call order must be strictly increasing
        assert call_order == list(range(len(call_order)))

    @pytest.mark.asyncio
    async def test_parallel_chunking_retry_on_failure(self, mock_llm_service):
        """Test: parallel chunking retries failed chunks once."""
        tp = TextProcessor(
            mock_llm_service,
            long_text_strategy="chunking",
            chunk_max_chars=8000,
            parallel_chunks=True,
            max_parallel_chunks=3,
        )
        long_text = "Тестовое предложение. " * 3000

        attempt_count = 0

        async def mock_refine(text: str, prompt: str) -> LLMResult:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise LLMError("Temporary API error")
            return LLMResult(text="OK")

        mock_llm_service.provider.refine_text = mock_refine

        result = await tp.create_structured(long_text, emoji_level=0)
        assert "OK" in result
        assert attempt_count > 1  # At least one retry happened

    @pytest.mark.asyncio
    async def test_parallel_chunking_tracks_truncation(self, mock_llm_service):
        """Test: truncation flag propagated from any chunk."""
        tp = TextProcessor(
            mock_llm_service,
            long_text_strategy="chunking",
            chunk_max_chars=8000,
            parallel_chunks=True,
            max_parallel_chunks=3,
        )
        long_text = "Текст для проверки. " * 3000

        call_count = 0

        async def mock_refine(text: str, prompt: str) -> LLMResult:
            nonlocal call_count
            call_count += 1
            return LLMResult(text="done", truncated=(call_count == 2))

        mock_llm_service.provider.refine_text = mock_refine

        result = await tp._process_with_chunking(long_text, f"Process: {long_text}")
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_single_chunk_uses_sequential(self, mock_llm_service):
        """Test: single chunk uses sequential even with parallel_chunks=True."""
        tp = TextProcessor(
            mock_llm_service,
            long_text_strategy="chunking",
            chunk_max_chars=100000,  # Very large — text fits in one chunk
            parallel_chunks=True,
            max_parallel_chunks=3,
        )
        long_text = "Короткий текст для одного чанка. " * 100

        mock_llm_service.provider.refine_text = AsyncMock(
            return_value=LLMResult(text="Single chunk result.")
        )

        result = await tp._process_with_chunking(long_text, f"Process: {long_text}")
        assert result.text == "Single chunk result."
        mock_llm_service.provider.refine_text.assert_called_once()
