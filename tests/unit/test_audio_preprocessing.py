"""Unit tests for audio preprocessing."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from src.transcription.audio_handler import AudioHandler


@pytest.fixture
def audio_handler(tmp_path):
    """Create AudioHandler instance with temp directory."""
    return AudioHandler(temp_dir=tmp_path)


@pytest.fixture
def sample_audio_file(tmp_path):
    """Create a sample audio file for testing."""
    audio_file = tmp_path / "test_audio.ogg"
    audio_file.write_text("fake audio content")
    return audio_file


class TestPreprocessAudio:
    """Tests for preprocess_audio method."""

    def test_preprocess_no_transformations(self, audio_handler, sample_audio_file):
        """Test preprocessing with all transformations disabled."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_convert_to_mono = False
            mock_settings.audio_speed_multiplier = 1.0

            result = audio_handler.preprocess_audio(sample_audio_file)

            assert result == sample_audio_file

    def test_preprocess_with_mono_only(self, audio_handler, sample_audio_file):
        """Test preprocessing with mono conversion only."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_convert_to_mono = True
            mock_settings.audio_speed_multiplier = 1.0
            mock_settings.audio_target_sample_rate = 16000

            with patch.object(
                audio_handler, "_convert_to_mono", return_value=sample_audio_file
            ) as mock_mono:
                result = audio_handler.preprocess_audio(sample_audio_file)

                mock_mono.assert_called_once_with(sample_audio_file)
                assert result == sample_audio_file

    def test_preprocess_with_speed_only(self, audio_handler, sample_audio_file):
        """Test preprocessing with speed adjustment only."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_convert_to_mono = False
            mock_settings.audio_speed_multiplier = 1.5

            with patch.object(
                audio_handler, "_adjust_speed", return_value=sample_audio_file
            ) as mock_speed:
                result = audio_handler.preprocess_audio(sample_audio_file)

                mock_speed.assert_called_once_with(sample_audio_file)
                assert result == sample_audio_file

    def test_preprocess_with_both_transformations(self, audio_handler, sample_audio_file, tmp_path):
        """Test preprocessing with both mono and speed."""
        mono_file = tmp_path / "mono.wav"
        speed_file = tmp_path / "speed.wav"
        mono_file.write_text("mono content")
        speed_file.write_text("speed content")

        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_convert_to_mono = True
            mock_settings.audio_speed_multiplier = 1.5
            mock_settings.audio_target_sample_rate = 16000

            with (
                patch.object(
                    audio_handler, "_convert_to_mono", return_value=mono_file
                ) as mock_mono,
                patch.object(audio_handler, "_adjust_speed", return_value=speed_file) as mock_speed,
            ):
                result = audio_handler.preprocess_audio(sample_audio_file)

                mock_mono.assert_called_once_with(sample_audio_file)
                mock_speed.assert_called_once_with(mono_file)
                assert result == speed_file

    def test_preprocess_mono_failure_fallback(self, audio_handler, sample_audio_file):
        """Test fallback when mono conversion fails."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_convert_to_mono = True
            mock_settings.audio_speed_multiplier = 1.0

            with patch.object(
                audio_handler, "_convert_to_mono", side_effect=Exception("ffmpeg error")
            ):
                result = audio_handler.preprocess_audio(sample_audio_file)

                # Should fall back to original
                assert result == sample_audio_file

    def test_preprocess_speed_failure_fallback(self, audio_handler, sample_audio_file):
        """Test fallback when speed adjustment fails."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_convert_to_mono = False
            mock_settings.audio_speed_multiplier = 1.5

            with patch.object(
                audio_handler, "_adjust_speed", side_effect=Exception("ffmpeg error")
            ):
                result = audio_handler.preprocess_audio(sample_audio_file)

                # Should fall back to original
                assert result == sample_audio_file


class TestAudioAnalysisHelpers:
    """Tests for audio analysis helper methods."""

    def test_get_audio_codec(self, audio_handler, sample_audio_file):
        """Test getting audio codec."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout.strip.return_value = "opus"
            mock_run.return_value = mock_result

            codec = audio_handler._get_audio_codec(sample_audio_file)

            assert codec == "opus"
            mock_run.assert_called_once()

    def test_get_audio_channels(self, audio_handler, sample_audio_file):
        """Test getting number of audio channels."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout.strip.return_value = "2"
            mock_run.return_value = mock_result

            channels = audio_handler._get_audio_channels(sample_audio_file)

            assert channels == 2
            mock_run.assert_called_once()

    def test_get_audio_sample_rate(self, audio_handler, sample_audio_file):
        """Test getting audio sample rate."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout.strip.return_value = "48000"
            mock_run.return_value = mock_result

            sample_rate = audio_handler._get_audio_sample_rate(sample_audio_file)

            assert sample_rate == 48000
            mock_run.assert_called_once()


class TestConvertToMono:
    """Tests for _convert_to_mono method."""

    def test_convert_to_mono_success(self, audio_handler, sample_audio_file):
        """Test successful mono conversion."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_target_sample_rate = 16000

            with patch.object(audio_handler, "_get_audio_channels", return_value=2):
                with patch("subprocess.run") as mock_run:
                    # Create the output file so stat() works
                    output_path = sample_audio_file.parent / f"{sample_audio_file.stem}_mono.opus"
                    output_path.write_bytes(b"fake audio data")

                    result = audio_handler._convert_to_mono(sample_audio_file)

                    # Verify output path uses opus format
                    assert result.name.endswith("_mono.opus")
                    assert result.parent == sample_audio_file.parent

                    # Verify ffmpeg was called correctly
                    mock_run.assert_called_once()
                    call_args = mock_run.call_args[0][0]
                    assert call_args[0] == "ffmpeg"
                    assert "-ac" in call_args
                    assert "1" in call_args  # Mono channel
                    assert "-ar" in call_args
                    assert "16000" in call_args  # Sample rate
                    assert "-acodec" in call_args
                    assert "libopus" in call_args

    def test_convert_to_mono_already_mono_skips(self, audio_handler, sample_audio_file):
        """Test that mono conversion is skipped for already mono files."""
        with patch.object(audio_handler, "_get_audio_channels", return_value=1):
            result = audio_handler._convert_to_mono(sample_audio_file)

            # Should return original file without conversion
            assert result == sample_audio_file

    def test_convert_to_mono_ffmpeg_failure(self, audio_handler, sample_audio_file):
        """Test ffmpeg failure during mono conversion."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_target_sample_rate = 16000

            with patch.object(audio_handler, "_get_audio_channels", return_value=2):
                with patch(
                    "subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffmpeg")
                ):
                    with pytest.raises(subprocess.CalledProcessError):
                        audio_handler._convert_to_mono(sample_audio_file)


class TestAdjustSpeed:
    """Tests for _adjust_speed method."""

    def test_adjust_speed_success(self, audio_handler, sample_audio_file):
        """Test successful speed adjustment."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_speed_multiplier = 1.5

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock()

                result = audio_handler._adjust_speed(sample_audio_file)

                # Verify output path uses opus format
                assert result.name.endswith("_speed1.5x.opus")
                assert result.parent == sample_audio_file.parent

                # Verify ffmpeg was called correctly
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert call_args[0] == "ffmpeg"
                assert "-filter:a" in call_args
                assert "atempo=1.5" in call_args
                assert "-acodec" in call_args
                assert "libopus" in call_args

    def test_adjust_speed_invalid_multiplier_low(self, audio_handler, sample_audio_file):
        """Test speed adjustment with multiplier too low."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_speed_multiplier = 0.3  # Below 0.5 minimum

            with pytest.raises(ValueError, match="must be 0.5-2.0"):
                audio_handler._adjust_speed(sample_audio_file)

    def test_adjust_speed_invalid_multiplier_high(self, audio_handler, sample_audio_file):
        """Test speed adjustment with multiplier too high."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_speed_multiplier = 2.5  # Above 2.0 maximum

            with pytest.raises(ValueError, match="must be 0.5-2.0"):
                audio_handler._adjust_speed(sample_audio_file)

    def test_adjust_speed_valid_boundary_values(self, audio_handler, sample_audio_file):
        """Test speed adjustment with boundary values."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()

            # Test minimum value
            with patch("src.transcription.audio_handler.settings") as mock_settings:
                mock_settings.audio_speed_multiplier = 0.5
                result = audio_handler._adjust_speed(sample_audio_file)
                assert result.name.endswith("_speed0.5x.opus")

            # Test maximum value
            with patch("src.transcription.audio_handler.settings") as mock_settings:
                mock_settings.audio_speed_multiplier = 2.0
                result = audio_handler._adjust_speed(sample_audio_file)
                assert result.name.endswith("_speed2.0x.opus")

    def test_adjust_speed_ffmpeg_failure(self, audio_handler, sample_audio_file):
        """Test ffmpeg failure during speed adjustment."""
        with patch("src.transcription.audio_handler.settings") as mock_settings:
            mock_settings.audio_speed_multiplier = 1.5

            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffmpeg")):
                with pytest.raises(subprocess.CalledProcessError):
                    audio_handler._adjust_speed(sample_audio_file)
