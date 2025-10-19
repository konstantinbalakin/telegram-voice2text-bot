"""Unit tests for WhisperService."""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

from src.transcription.whisper_service import WhisperService


@pytest.fixture
def whisper_service():
    """Create WhisperService instance without initialization."""
    service = WhisperService(
        model_size="base",
        device="cpu",
        compute_type="int8",
        max_workers=2,
    )
    return service


@pytest.fixture
def initialized_whisper_service():
    """Create and initialize WhisperService with mocked model."""
    service = WhisperService(
        model_size="base",
        device="cpu",
        compute_type="int8",
        max_workers=2,
    )

    # Mock the WhisperModel
    with patch("src.transcription.whisper_service.WhisperModel") as mock_model_class:
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        service.initialize()
        service._model = mock_model

    yield service

    # Cleanup
    asyncio.run(service.shutdown())


class TestWhisperServiceInit:
    """Tests for WhisperService initialization."""

    def test_service_creation(self, whisper_service):
        """Test service is created with correct parameters."""
        assert whisper_service.model_size == "base"
        assert whisper_service.device == "cpu"
        assert whisper_service.compute_type == "int8"
        assert whisper_service.max_workers == 2
        assert not whisper_service.is_initialized()

    def test_service_initialization(self):
        """Test service initialization loads model and creates executor."""
        service = WhisperService(model_size="tiny", device="cpu")

        with patch("src.transcription.whisper_service.WhisperModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model

            service.initialize()

            assert service.is_initialized()
            assert service._model is not None
            assert service._executor is not None
            assert isinstance(service._executor, ThreadPoolExecutor)

            # Verify WhisperModel was called with correct parameters
            mock_model_class.assert_called_once_with(
                "tiny",
                device="cpu",
                compute_type="int8",
            )

    def test_service_initialization_idempotent(self):
        """Test calling initialize() multiple times doesn't reinitialize."""
        service = WhisperService(model_size="tiny")

        with patch("src.transcription.whisper_service.WhisperModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model

            service.initialize()
            service.initialize()  # Second call

            # Should only be called once
            assert mock_model_class.call_count == 1

    def test_service_initialization_failure(self):
        """Test service handles initialization failure."""
        service = WhisperService()

        with patch("src.transcription.whisper_service.WhisperModel") as mock_model_class:
            mock_model_class.side_effect = RuntimeError("Model load failed")

            with pytest.raises(RuntimeError, match="Model load failed"):
                service.initialize()

            assert not service.is_initialized()


class TestWhisperServiceTranscribe:
    """Tests for transcription functionality."""

    @pytest.mark.asyncio
    async def test_transcribe_not_initialized(self, whisper_service):
        """Test transcribe fails if service not initialized."""
        audio_path = Path("/tmp/test.wav")

        with pytest.raises(RuntimeError, match="not initialized"):
            await whisper_service.transcribe(audio_path)

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self, initialized_whisper_service):
        """Test transcribe fails if audio file doesn't exist."""
        audio_path = Path("/tmp/nonexistent.wav")

        with pytest.raises(FileNotFoundError):
            await initialized_whisper_service.transcribe(audio_path)

    @pytest.mark.asyncio
    async def test_transcribe_success(self, initialized_whisper_service, tmp_path):
        """Test successful transcription."""
        # Create temporary audio file
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        # Mock transcription result
        mock_segment1 = Mock()
        mock_segment1.text = " Hello "
        mock_segment2 = Mock()
        mock_segment2.text = " world "

        mock_info = Mock()
        mock_info.duration = 5.0
        mock_info.language = "en"

        initialized_whisper_service._model.transcribe.return_value = (
            [mock_segment1, mock_segment2],
            mock_info,
        )

        # Transcribe
        text, duration = await initialized_whisper_service.transcribe(audio_file, language="en")

        assert text == "Hello world"
        assert duration == 5.0

    @pytest.mark.asyncio
    async def test_transcribe_with_timeout(self, initialized_whisper_service, tmp_path):
        """Test transcription respects timeout."""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        # Mock slow transcription (sync function since _transcribe_sync is sync)
        def slow_transcribe(*args, **kwargs):
            import time
            time.sleep(10)  # Simulate slow transcription
            return [], Mock()

        with patch.object(initialized_whisper_service, "_transcribe_sync", side_effect=slow_transcribe):
            with pytest.raises(TimeoutError, match="exceeded timeout"):
                await initialized_whisper_service.transcribe(audio_file, timeout=1)

    @pytest.mark.asyncio
    async def test_transcribe_failure(self, initialized_whisper_service, tmp_path):
        """Test transcription handles errors."""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        # Mock transcription failure
        initialized_whisper_service._model.transcribe.side_effect = RuntimeError("Transcription failed")

        with pytest.raises(RuntimeError, match="Transcription failed"):
            await initialized_whisper_service.transcribe(audio_file)


class TestWhisperServiceShutdown:
    """Tests for service shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_not_initialized(self, whisper_service):
        """Test shutdown on non-initialized service is safe."""
        await whisper_service.shutdown()
        assert not whisper_service.is_initialized()

    @pytest.mark.asyncio
    async def test_shutdown_cleans_resources(self):
        """Test shutdown properly cleans up resources."""
        service = WhisperService(model_size="tiny")

        with patch("src.transcription.whisper_service.WhisperModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model

            service.initialize()
            assert service.is_initialized()

            await service.shutdown()

            assert not service.is_initialized()
            assert service._model is None
            assert service._executor is None


class TestWhisperServiceTranscribeSync:
    """Tests for synchronous transcription method."""

    def test_transcribe_sync(self, initialized_whisper_service):
        """Test synchronous transcription method."""
        mock_segment = Mock()
        mock_segment.text = "Test"

        mock_info = Mock()
        mock_info.duration = 2.0

        # Mock the model's transcribe method
        initialized_whisper_service._model.transcribe.return_value = (
            iter([mock_segment]),  # Generator
            mock_info,
        )

        segments, info = initialized_whisper_service._transcribe_sync("/tmp/test.wav", "en")

        assert len(segments) == 1
        assert segments[0].text == "Test"
        assert info.duration == 2.0

        # Verify transcribe was called with correct parameters
        initialized_whisper_service._model.transcribe.assert_called_once()
        call_kwargs = initialized_whisper_service._model.transcribe.call_args.kwargs
        assert call_kwargs["language"] == "en"
        assert call_kwargs["beam_size"] == 5
        assert call_kwargs["vad_filter"] is True


class TestWhisperServiceGlobalInstance:
    """Tests for global instance getter."""

    def test_get_whisper_service_creates_instance(self):
        """Test get_whisper_service creates and initializes instance."""
        from src.transcription.whisper_service import get_whisper_service

        with patch("src.transcription.whisper_service.WhisperModel"):
            service = get_whisper_service()

            assert service is not None
            assert isinstance(service, WhisperService)

    def test_get_whisper_service_returns_same_instance(self):
        """Test get_whisper_service returns singleton."""
        from src.transcription.whisper_service import get_whisper_service, _whisper_service

        with patch("src.transcription.whisper_service.WhisperModel"):
            service1 = get_whisper_service()
            service2 = get_whisper_service()

            assert service1 is service2
