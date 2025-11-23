"""Unit tests for LLM service."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx

from src.services.llm_service import (
    DeepSeekProvider,
    LLMFactory,
    LLMService,
    LLMTimeoutError,
    LLMAPIError,
)
from src.config import Settings


@pytest.fixture
def deepseek_provider():
    """Create DeepSeekProvider instance."""
    return DeepSeekProvider(
        api_key="test-api-key",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        timeout=30,
    )


class TestDeepSeekProvider:
    """Tests for DeepSeekProvider."""

    def test_provider_creation(self, deepseek_provider):
        """Test provider is created with correct parameters."""
        assert deepseek_provider.api_key == "test-api-key"
        assert deepseek_provider.model == "deepseek-chat"
        assert deepseek_provider.base_url == "https://api.deepseek.com"
        assert deepseek_provider.timeout == 30
        assert deepseek_provider.client is not None

    @pytest.mark.asyncio
    async def test_refine_empty_text(self, deepseek_provider):
        """Test refinement with empty text returns unchanged."""
        result = await deepseek_provider.refine_text("", "test prompt")
        assert result == ""

        result = await deepseek_provider.refine_text("   ", "test prompt")
        assert result == "   "

    @pytest.mark.asyncio
    async def test_refine_text_success(self, deepseek_provider):
        """Test successful text refinement."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Refined text here."}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        with patch.object(deepseek_provider.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await deepseek_provider.refine_text("draft text here", "Improve this text")

            assert result == "Refined text here."
            mock_post.assert_called_once()

            # Verify API request structure
            call_args = mock_post.call_args
            assert call_args[0][0] == "/v1/chat/completions"
            assert call_args[1]["json"]["model"] == "deepseek-chat"
            assert call_args[1]["json"]["temperature"] == 0.3
            assert len(call_args[1]["json"]["messages"]) == 2

    @pytest.mark.asyncio
    async def test_refine_text_truncates_long_text(self, deepseek_provider):
        """Test that overly long text is truncated."""
        long_text = "a" * 15000

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Refined"}}],
            "usage": {"total_tokens": 100},
        }

        with patch.object(deepseek_provider.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await deepseek_provider.refine_text(long_text, "test prompt")

            # Verify text was truncated in request
            call_args = mock_post.call_args
            sent_text = call_args[1]["json"]["messages"][1]["content"]
            assert len(sent_text) == 10000

    @pytest.mark.asyncio
    async def test_refine_text_timeout(self, deepseek_provider):
        """Test timeout handling."""
        with patch.object(deepseek_provider.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(LLMTimeoutError, match="timeout after"):
                await deepseek_provider.refine_text("test text", "test prompt")

    @pytest.mark.asyncio
    async def test_refine_text_http_error(self, deepseek_provider):
        """Test HTTP error handling."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        error = httpx.HTTPStatusError("Unauthorized", request=Mock(), response=mock_response)

        with patch.object(deepseek_provider.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = error

            with pytest.raises(LLMAPIError, match="API error: 401"):
                await deepseek_provider.refine_text("test text", "test prompt")

    @pytest.mark.asyncio
    async def test_refine_text_unexpected_error(self, deepseek_provider):
        """Test handling of unexpected errors."""
        with patch.object(deepseek_provider.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Unexpected error")

            with pytest.raises(LLMAPIError, match="DeepSeek error"):
                await deepseek_provider.refine_text("test text", "test prompt")

    @pytest.mark.asyncio
    async def test_close(self, deepseek_provider):
        """Test provider cleanup."""
        with patch.object(deepseek_provider.client, "aclose", new_callable=AsyncMock) as mock_close:
            await deepseek_provider.close()
            mock_close.assert_called_once()


class TestLLMFactory:
    """Tests for LLMFactory."""

    def test_create_provider_disabled(self):
        """Test factory returns None when refinement disabled."""
        settings = Mock(spec=Settings)
        settings.llm_refinement_enabled = False

        provider = LLMFactory.create_provider(settings)
        assert provider is None

    def test_create_provider_no_api_key(self):
        """Test factory returns None when no API key."""
        settings = Mock(spec=Settings)
        settings.llm_refinement_enabled = True
        settings.llm_api_key = None

        provider = LLMFactory.create_provider(settings)
        assert provider is None

    def test_create_deepseek_provider(self):
        """Test factory creates DeepSeek provider."""
        settings = Mock(spec=Settings)
        settings.llm_refinement_enabled = True
        settings.llm_api_key = "test-key"
        settings.llm_provider = "deepseek"
        settings.llm_model = "deepseek-chat"
        settings.llm_base_url = "https://api.deepseek.com"
        settings.llm_timeout = 30

        provider = LLMFactory.create_provider(settings)

        assert isinstance(provider, DeepSeekProvider)
        assert provider.api_key == "test-key"
        assert provider.model == "deepseek-chat"

    def test_create_unknown_provider(self):
        """Test factory raises error for unknown provider."""
        settings = Mock(spec=Settings)
        settings.llm_refinement_enabled = True
        settings.llm_api_key = "test-key"
        settings.llm_provider = "unknown"

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMFactory.create_provider(settings)


class TestLLMService:
    """Tests for LLMService."""

    @pytest.mark.asyncio
    async def test_refine_with_no_provider(self):
        """Test refinement with no provider returns draft."""
        service = LLMService(provider=None, prompt="test prompt")

        result = await service.refine_transcription("draft text")
        assert result == "draft text"

    @pytest.mark.asyncio
    async def test_refine_success(self):
        """Test successful refinement."""
        mock_provider = AsyncMock()
        mock_provider.refine_text.return_value = "refined text"

        service = LLMService(provider=mock_provider, prompt="test prompt")

        result = await service.refine_transcription("draft text")
        assert result == "refined text"
        mock_provider.refine_text.assert_called_once_with("draft text", "test prompt")

    @pytest.mark.asyncio
    async def test_refine_timeout_fallback(self):
        """Test timeout falls back to draft."""
        mock_provider = AsyncMock()
        mock_provider.refine_text.side_effect = LLMTimeoutError("Timeout")

        service = LLMService(provider=mock_provider, prompt="test prompt")

        result = await service.refine_transcription("draft text")
        assert result == "draft text"

    @pytest.mark.asyncio
    async def test_refine_api_error_fallback(self):
        """Test API error falls back to draft."""
        mock_provider = AsyncMock()
        mock_provider.refine_text.side_effect = LLMAPIError("API error")

        service = LLMService(provider=mock_provider, prompt="test prompt")

        result = await service.refine_transcription("draft text")
        assert result == "draft text"

    @pytest.mark.asyncio
    async def test_refine_unexpected_error_fallback(self):
        """Test unexpected error falls back to draft."""
        mock_provider = AsyncMock()
        mock_provider.refine_text.side_effect = Exception("Unexpected")

        service = LLMService(provider=mock_provider, prompt="test prompt")

        result = await service.refine_transcription("draft text")
        assert result == "draft text"

    @pytest.mark.asyncio
    async def test_close_with_provider(self):
        """Test service cleanup with provider."""
        mock_provider = AsyncMock()
        service = LLMService(provider=mock_provider, prompt="test prompt")

        await service.close()
        mock_provider.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_provider(self):
        """Test service cleanup without provider."""
        service = LLMService(provider=None, prompt="test prompt")
        await service.close()  # Should not raise
