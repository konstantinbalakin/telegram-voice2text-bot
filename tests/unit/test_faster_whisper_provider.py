"""Unit tests for FastWhisperProvider."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.transcription.providers.faster_whisper_provider import FastWhisperProvider
from src.transcription.models import TranscriptionContext, TranscriptionResult


@pytest.fixture
def provider():
    """Create FastWhisperProvider instance without initialization."""
    return FastWhisperProvider(
        model_size="base",
        device="cpu",
        compute_type="int8",
        beam_size=1,
        max_workers=2,
    )


@pytest.fixture
def initialized_provider():
    """Create and initialize FastWhisperProvider with mocked model."""
    provider = FastWhisperProvider(
        model_size="base",
        device="cpu",
        compute_type="int8",
        beam_size=1,
        max_workers=2,
    )

    with patch(
        "src.transcription.providers.faster_whisper_provider.WhisperModel"
    ) as mock_model_class:
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        provider.initialize()
        provider._model = mock_model

    yield provider

    asyncio.run(provider.shutdown())


class TestFasterWhisperProviderInit:
    """Tests for provider initialization."""

    def test_provider_creation(self, provider):
        """Test provider is created with correct parameters."""
        assert provider.model_size == "base"
        assert provider.device == "cpu"
        assert provider.compute_type == "int8"
        assert provider.beam_size == 1
        assert not provider.is_initialized()

    def test_provider_initialization(self):
        """Test provider initialization loads model."""
        provider = FastWhisperProvider(model_size="tiny", device="cpu")

        with patch(
            "src.transcription.providers.faster_whisper_provider.WhisperModel"
        ) as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model

            provider.initialize()

            assert provider.is_initialized()
            assert provider._model is not None
            assert provider._executor is not None

            mock_model_class.assert_called_once()


class TestFasterWhisperProviderTranscribe:
    """Tests for transcription functionality."""

    @pytest.mark.asyncio
    async def test_transcribe_not_initialized(self, provider):
        """Test transcribe fails if provider not initialized."""
        audio_path = Path("/tmp/test.wav")
        context = TranscriptionContext(
            user_id=123, duration_seconds=5.0, file_size_bytes=1024
        )

        with pytest.raises(RuntimeError, match="not initialized"):
            await provider.transcribe(audio_path, context)

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self, initialized_provider):
        """Test transcribe fails if audio file doesn't exist."""
        audio_path = Path("/tmp/nonexistent.wav")
        context = TranscriptionContext(
            user_id=123, duration_seconds=5.0, file_size_bytes=1024
        )

        with pytest.raises(FileNotFoundError):
            await initialized_provider.transcribe(audio_path, context)

    @pytest.mark.asyncio
    async def test_transcribe_success(self, initialized_provider, tmp_path):
        """Test successful transcription."""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        mock_segment = Mock()
        mock_segment.text = "Hello world"

        mock_info = Mock()
        mock_info.duration = 5.0
        mock_info.language = "en"

        initialized_provider._model.transcribe.return_value = (
            [mock_segment],
            mock_info,
        )

        context = TranscriptionContext(
            user_id=123, duration_seconds=5.0, file_size_bytes=1024, language="en"
        )
        result = await initialized_provider.transcribe(audio_file, context)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.provider_used == "faster-whisper"
        assert result.model_name == "base"
        assert result.audio_duration == 5.0


class TestFasterWhisperProviderShutdown:
    """Tests for provider shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_cleans_resources(self):
        """Test shutdown properly cleans up resources."""
        provider = FastWhisperProvider(model_size="tiny")

        with patch("src.transcription.providers.faster_whisper_provider.WhisperModel"):
            provider.initialize()
            assert provider.is_initialized()

            await provider.shutdown()

            assert not provider.is_initialized()
            assert provider._model is None
