"""Unit tests for AudioHandler."""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.transcription.audio_handler import AudioHandler


@pytest.fixture
def audio_handler(tmp_path):
    """Create AudioHandler with temporary directory."""
    return AudioHandler(temp_dir=tmp_path)


@pytest.fixture
def mock_telegram_file():
    """Create mock Telegram File object."""
    mock_file = Mock()
    mock_file.file_size = 1024 * 1024  # 1MB
    mock_file.file_path = "/path/to/file.ogg"
    mock_file.download_to_drive = AsyncMock()
    return mock_file


class TestAudioHandlerInit:
    """Tests for AudioHandler initialization."""

    def test_handler_creation_with_custom_dir(self, tmp_path):
        """Test handler is created with custom temp directory."""
        handler = AudioHandler(temp_dir=tmp_path)

        assert handler.temp_dir == tmp_path
        assert handler.temp_dir.exists()
        assert ".ogg" in handler.supported_formats
        assert ".mp3" in handler.supported_formats
        assert ".wav" in handler.supported_formats

    def test_handler_creation_with_default_dir(self):
        """Test handler creates default temp directory."""
        handler = AudioHandler()

        assert handler.temp_dir.exists()
        assert handler.temp_dir.name == "telegram_voice2text"

    def test_supported_formats(self, audio_handler):
        """Test supported audio formats."""
        expected_formats = {".ogg", ".mp3", ".wav", ".m4a", ".opus", ".oga"}
        assert audio_handler.supported_formats == expected_formats


class TestAudioHandlerDownloadVoice:
    """Tests for voice message download."""

    @pytest.mark.asyncio
    async def test_download_success(self, audio_handler, mock_telegram_file, tmp_path):
        """Test successful voice message download."""
        file_id = "test_file_123"

        # Mock successful download
        async def mock_download(path):
            path.write_bytes(b"fake audio data")

        mock_telegram_file.download_to_drive = mock_download

        audio_path = await audio_handler.download_voice_message(mock_telegram_file, file_id)

        assert audio_path.exists()
        assert audio_path.suffix == ".ogg"
        assert file_id in audio_path.name
        assert audio_path.read_bytes() == b"fake audio data"

    @pytest.mark.asyncio
    async def test_download_file_too_large(self, audio_handler, mock_telegram_file):
        """Test download fails for files exceeding size limit."""
        mock_telegram_file.file_size = 21 * 1024 * 1024  # 21MB

        with pytest.raises(ValueError, match="File too large"):
            await audio_handler.download_voice_message(mock_telegram_file, "test_id")

    @pytest.mark.asyncio
    async def test_download_unsupported_format(self, audio_handler, mock_telegram_file):
        """Test download fails for unsupported audio format."""
        mock_telegram_file.file_path = "/path/to/file.avi"

        with pytest.raises(ValueError, match="Unsupported audio format"):
            await audio_handler.download_voice_message(mock_telegram_file, "test_id")

    @pytest.mark.asyncio
    async def test_download_failure_cleanup(self, audio_handler, mock_telegram_file):
        """Test partial download is cleaned up on failure."""
        file_id = "test_file_456"

        # Mock download failure
        async def mock_download_fail(path):
            path.write_bytes(b"partial data")
            raise RuntimeError("Download failed")

        mock_telegram_file.download_to_drive = mock_download_fail

        audio_path = audio_handler.temp_dir / f"{file_id}.ogg"

        with pytest.raises(RuntimeError, match="Download failed"):
            await audio_handler.download_voice_message(mock_telegram_file, file_id)

        # Verify cleanup happened
        assert not audio_path.exists()

    @pytest.mark.asyncio
    async def test_download_no_extension_defaults_to_ogg(self, audio_handler, mock_telegram_file):
        """Test download defaults to .ogg extension if not specified."""
        mock_telegram_file.file_path = None
        file_id = "test_file_789"

        async def mock_download(path):
            path.write_bytes(b"audio data")

        mock_telegram_file.download_to_drive = mock_download

        audio_path = await audio_handler.download_voice_message(mock_telegram_file, file_id)

        assert audio_path.suffix == ".ogg"


class TestAudioHandlerDownloadFromURL:
    """Tests for downloading from URL."""

    @pytest.mark.asyncio
    async def test_download_from_url_success(self, audio_handler):
        """Test successful download from URL."""
        url = "https://example.com/audio.mp3"
        file_id = "url_file_123"
        audio_data = b"audio data from url"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.content = audio_data
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            audio_path = await audio_handler.download_from_url(url, file_id, ".mp3")

            assert audio_path.exists()
            assert audio_path.suffix == ".mp3"
            assert audio_path.read_bytes() == audio_data

    @pytest.mark.asyncio
    async def test_download_from_url_failure(self, audio_handler):
        """Test download from URL handles errors."""
        url = "https://example.com/audio.mp3"
        file_id = "url_file_456"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = RuntimeError("Network error")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="Download failed"):
                await audio_handler.download_from_url(url, file_id)


class TestAudioHandlerCleanup:
    """Tests for file cleanup functionality."""

    def test_cleanup_file_success(self, audio_handler, tmp_path):
        """Test successful file cleanup."""
        audio_file = tmp_path / "test_audio.ogg"
        audio_file.write_bytes(b"audio data")

        assert audio_file.exists()

        audio_handler.cleanup_file(audio_file)

        assert not audio_file.exists()

    def test_cleanup_nonexistent_file(self, audio_handler, tmp_path):
        """Test cleanup of nonexistent file doesn't raise error."""
        audio_file = tmp_path / "nonexistent.ogg"

        # Should not raise exception
        audio_handler.cleanup_file(audio_file)

    def test_cleanup_old_files(self, audio_handler, tmp_path):
        """Test cleanup of old files."""
        import time

        # Create some test files
        old_file = tmp_path / "old.ogg"
        new_file = tmp_path / "new.ogg"

        old_file.write_bytes(b"old")
        new_file.write_bytes(b"new")

        # Modify old file's timestamp to be 25 hours ago
        old_time = time.time() - (25 * 3600)
        import os

        os.utime(old_file, (old_time, old_time))

        deleted_count = audio_handler.cleanup_old_files(max_age_hours=24)

        assert deleted_count == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_old_files_no_files(self, audio_handler):
        """Test cleanup when no old files exist."""
        deleted_count = audio_handler.cleanup_old_files()

        assert deleted_count == 0


class TestAudioHandlerValidation:
    """Tests for audio file validation."""

    def test_validate_valid_file(self, audio_handler, tmp_path):
        """Test validation of valid audio file."""
        audio_file = tmp_path / "valid.ogg"
        audio_file.write_bytes(b"audio data")

        assert audio_handler.validate_audio_file(audio_file)

    def test_validate_nonexistent_file(self, audio_handler, tmp_path):
        """Test validation fails for nonexistent file."""
        audio_file = tmp_path / "nonexistent.ogg"

        assert not audio_handler.validate_audio_file(audio_file)

    def test_validate_unsupported_format(self, audio_handler, tmp_path):
        """Test validation fails for unsupported format."""
        audio_file = tmp_path / "invalid.txt"
        audio_file.write_bytes(b"not audio")

        assert not audio_handler.validate_audio_file(audio_file)

    def test_validate_empty_file(self, audio_handler, tmp_path):
        """Test validation fails for empty file."""
        audio_file = tmp_path / "empty.ogg"
        audio_file.write_bytes(b"")

        assert not audio_handler.validate_audio_file(audio_file)


class TestAudioHandlerGetDuration:
    """Tests for audio duration detection."""

    def test_get_audio_duration_placeholder(self, audio_handler, tmp_path):
        """Test get_audio_duration returns None (placeholder implementation)."""
        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"audio data")

        duration = audio_handler.get_audio_duration(audio_file)

        # Current implementation returns None
        assert duration is None
