"""Unit tests for OpenAIProvider."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
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


@pytest_asyncio.fixture
async def initialized_provider(provider):
    """Create and initialize OpenAIProvider."""
    await provider.initialize()
    yield provider


class TestOpenAIProviderInit:
    """Tests for provider initialization."""

    def test_provider_creation(self, provider):
        """Test provider is created with correct parameters."""
        assert provider.model == "whisper-1"
        assert provider.timeout == 30
        assert provider.api_key == "test-api-key"
        assert not provider.is_initialized()

    @pytest.mark.asyncio
    async def test_provider_initialization(self, provider):
        """Test provider initialization."""
        await provider.initialize()

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

    @pytest.mark.asyncio
    async def test_transcribe_large_file_no_value_error(self, initialized_provider, tmp_path):
        """Test large file (>25MB) doesn't raise ValueError when chunking would be triggered."""
        from unittest.mock import AsyncMock, MagicMock
        from src.config import settings

        test_file = tmp_path / "large.mp3"

        file_size_30mb = 30 * 1024 * 1024
        test_file.write_bytes(b"x" * file_size_30mb)

        context = TranscriptionContext(
            user_id=123,
            duration_seconds=settings.openai_gpt4o_max_duration + 100,
            file_size_bytes=file_size_30mb,
        )

        mock_result = MagicMock(
            text="transcribed text",
            language="en",
            processing_time=10.0,
            audio_duration=settings.openai_gpt4o_max_duration + 100,
            provider_used="openai",
            model_name="gpt-4o-transcribe (chunked)",
        )

        initialized_provider._handle_long_audio = AsyncMock(return_value=mock_result)

        result = await initialized_provider.transcribe(test_file, context)

        assert result.text == "transcribed text"
        assert result.provider_used == "openai"
        initialized_provider._handle_long_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_10mb_file_no_chunking(self, initialized_provider, tmp_path):
        """Test 10MB file (< 25MB) transcribes directly without chunking."""
        import httpx
        from src.config import settings

        test_file = tmp_path / "medium.mp3"

        file_size_10mb = 10 * 1024 * 1024
        test_file.write_bytes(b"x" * file_size_10mb)

        context = TranscriptionContext(
            user_id=123, duration_seconds=300.0, file_size_bytes=file_size_10mb
        )

        mock_response = httpx.Response(
            status_code=200,
            json={"text": "10MB transcription", "language": "en"},
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with patch.object(
            initialized_provider._client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await initialized_provider.transcribe(test_file, context)

        assert result.text == "10MB transcription"
        assert result.provider_used == "openai"

    @pytest.mark.asyncio
    async def test_transcribe_100mb_file_multiple_chunks(self, initialized_provider, tmp_path):
        """Test 100MB file (> 25MB) triggers chunking path."""
        from unittest.mock import AsyncMock, MagicMock
        from src.config import settings

        test_file = tmp_path / "large.mp3"

        file_size_100mb = 100 * 1024 * 1024
        test_file.write_bytes(b"x" * file_size_100mb)

        context = TranscriptionContext(
            user_id=123,
            duration_seconds=settings.openai_gpt4o_max_duration + 500,
            file_size_bytes=file_size_100mb,
        )

        mock_result = MagicMock(
            text="chunked transcription from multiple segments",
            language="en",
            processing_time=20.0,
            audio_duration=settings.openai_gpt4o_max_duration + 500,
            provider_used="openai",
            model_name="gpt-4o-transcribe (chunked)",
        )

        initialized_provider._handle_long_audio = AsyncMock(return_value=mock_result)

        result = await initialized_provider.transcribe(test_file, context)

        assert result.text == "chunked transcription from multiple segments"
        assert result.provider_used == "openai"
        initialized_provider._handle_long_audio.assert_called_once()


class TestOpenAIProviderShutdown:
    """Tests for provider shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown(self, initialized_provider):
        """Test shutdown properly cleans up resources."""
        await initialized_provider.shutdown()

        assert not initialized_provider.is_initialized()
        assert initialized_provider._client is None
