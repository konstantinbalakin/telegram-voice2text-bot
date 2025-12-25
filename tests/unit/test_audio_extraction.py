"""Tests for audio extraction from video files."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from src.transcription.audio_handler import AudioHandler


@pytest.fixture
def audio_handler(tmp_path):
    """Create AudioHandler with temporary directory."""
    return AudioHandler(temp_dir=tmp_path)


class TestHasAudioStream:
    """Test suite for _has_audio_stream functionality."""

    def test_has_audio_stream_with_audio(self, audio_handler):
        """Test detection of audio stream in file with audio."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="audio\n", returncode=0
            )
            result = audio_handler._has_audio_stream(Path("test.mp4"))
            assert result is True

    def test_has_audio_stream_without_audio(self, audio_handler):
        """Test detection when file has no audio stream."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", returncode=0
            )
            result = audio_handler._has_audio_stream(Path("test.mp4"))
            assert result is False

    def test_has_audio_stream_ffprobe_error(self, audio_handler):
        """Test handling ffprobe failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")
            result = audio_handler._has_audio_stream(Path("invalid.mp4"))
            assert result is False


class TestExtractAudioTrack:
    """Test suite for extract_audio_track functionality."""

    def test_extract_audio_track_success(self, audio_handler, tmp_path):
        """Test successful audio extraction."""
        input_file = tmp_path / "test.mp4"
        input_file.write_bytes(b"fake video data")

        with patch.object(audio_handler, "_has_audio_stream", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                # Create expected output file (simulating ffmpeg creating it)
                output_file = tmp_path / "test_extracted.ogg"
                output_file.write_bytes(b"fake audio")

                result = audio_handler.extract_audio_track(input_file)
                assert result.suffix == ".ogg"
                assert "extracted" in result.name

    def test_extract_audio_track_no_audio(self, audio_handler, tmp_path):
        """Test extraction fails when no audio stream."""
        input_file = tmp_path / "test.mp4"
        input_file.write_bytes(b"fake video data")

        with patch.object(audio_handler, "_has_audio_stream", return_value=False):
            with pytest.raises(ValueError, match="no audio stream"):
                audio_handler.extract_audio_track(input_file)

    def test_extract_audio_track_ffmpeg_error(self, audio_handler, tmp_path):
        """Test extraction handles ffmpeg failure."""
        input_file = tmp_path / "test.mp4"
        input_file.write_bytes(b"fake video data")

        with patch.object(audio_handler, "_has_audio_stream", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg")
                with pytest.raises(subprocess.CalledProcessError):
                    audio_handler.extract_audio_track(input_file)


class TestGetAudioDurationFfprobe:
    """Test suite for get_audio_duration_ffprobe functionality."""

    def test_get_duration_success(self, audio_handler):
        """Test successful duration retrieval."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="123.456\n", returncode=0
            )
            result = audio_handler.get_audio_duration_ffprobe(Path("test.mp3"))
            assert result == 123.456

    def test_get_duration_ffprobe_error(self, audio_handler):
        """Test handling ffprobe failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")
            result = audio_handler.get_audio_duration_ffprobe(Path("invalid.mp3"))
            assert result is None

    def test_get_duration_invalid_output(self, audio_handler):
        """Test handling invalid ffprobe output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="not a number\n", returncode=0
            )
            result = audio_handler.get_audio_duration_ffprobe(Path("test.mp3"))
            assert result is None

    def test_get_duration_empty_output(self, audio_handler):
        """Test handling empty ffprobe output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", returncode=0
            )
            result = audio_handler.get_audio_duration_ffprobe(Path("test.mp3"))
            assert result is None


class TestSupportedFormats:
    """Test suite for supported formats configuration."""

    def test_audio_formats_included(self, audio_handler):
        """Test that standard audio formats are supported."""
        audio_formats = {".ogg", ".oga", ".mp3", ".wav", ".m4a", ".opus"}
        for fmt in audio_formats:
            assert fmt in audio_handler.supported_formats

    def test_additional_audio_formats_included(self, audio_handler):
        """Test that additional audio formats are supported."""
        additional_formats = {".aac", ".flac", ".wma", ".amr", ".webm", ".3gp"}
        for fmt in additional_formats:
            assert fmt in audio_handler.supported_formats

    def test_video_formats_included(self, audio_handler):
        """Test that video formats are supported for audio extraction."""
        video_formats = {".mp4", ".mkv", ".avi", ".mov"}
        for fmt in video_formats:
            assert fmt in audio_handler.supported_formats
