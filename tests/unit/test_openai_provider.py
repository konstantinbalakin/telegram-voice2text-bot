"""Unit tests for OpenAIProvider."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pathlib import Path

from src.transcription.providers.openai_provider import OpenAIProvider
from src.transcription.models import TranscriptionContext


@pytest.fixture
def provider():
    """Create OpenAIProvider instance."""
    return OpenAIProvider(
        api_key="test-api-key",
        model="whisper-1",
        timeout=30,
    )


@pytest.fixture
def initialized_provider(provider):
    """Create and initialize OpenAIProvider."""
    provider.initialize()
    yield provider


class TestOpenAIProviderInit:
    """Tests for provider initialization."""

    def test_provider_creation(self, provider):
        """Test provider is created with correct parameters."""
        assert provider.model == "whisper-1"
        assert provider.timeout == 30
        assert provider.api_key == "test-api-key"
        assert not provider.is_initialized()

    def test_provider_initialization(self, provider):
        """Test provider initialization."""
        provider.initialize()

        assert provider.is_initialized()
        assert provider._client is not None

    def test_initialization_without_api_key(self):
        """Test provider uses settings API key when None provided."""
        provider = OpenAIProvider(api_key=None)

        # Provider will use settings.openai_api_key as fallback
        # This tests the default behavior
        assert not provider.is_initialized()


class TestOpenAIProviderTranscribe:
    """Tests for transcription functionality."""

    @pytest.mark.asyncio
    async def test_transcribe_not_initialized(self, provider):
        """Test transcribe fails if provider not initialized."""
        audio_path = Path("/tmp/test.wav")
        context = TranscriptionContext(user_id=123, duration_seconds=5.0, file_size_bytes=1024)

        with pytest.raises(RuntimeError, match="not initialized"):
            await provider.transcribe(audio_path, context)

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self, initialized_provider):
        """Test transcribe fails if audio file doesn't exist."""
        audio_path = Path("/tmp/nonexistent.wav")
        context = TranscriptionContext(user_id=123, duration_seconds=5.0, file_size_bytes=1024)

        with pytest.raises(FileNotFoundError):
            await initialized_provider.transcribe(audio_path, context)

    @pytest.mark.asyncio
    async def test_transcribe_success(self, initialized_provider, tmp_path):
        """Test successful transcription with mocked httpx client."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        context = TranscriptionContext(user_id=123, duration_seconds=5.0, file_size_bytes=1024)

        mock_response = httpx.Response(
            status_code=200,
            json={"text": "Hello, this is a test transcription", "language": "en"},
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with patch.object(
            initialized_provider._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await initialized_provider.transcribe(test_file, context)

        assert result is not None
        assert result.text == "Hello, this is a test transcription"
        assert result.language == "en"
        assert result.provider_used == "openai"
        assert result.model_name == "whisper-1"
        assert result.processing_time > 0


class TestOpenAIProviderShutdown:
    """Tests for provider shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown(self, initialized_provider):
        """Test shutdown properly cleans up resources."""
        await initialized_provider.shutdown()

        assert not initialized_provider.is_initialized()
        assert initialized_provider._client is None
