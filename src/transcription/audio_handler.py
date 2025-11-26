"""
Audio file handler for downloading and processing Telegram voice messages
"""

import logging
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx
from telegram import File as TelegramFile

from src.config import settings


logger = logging.getLogger(__name__)


class AudioHandler:
    """Handler for downloading and managing audio files from Telegram."""

    def __init__(self, temp_dir: Optional[Path] = None):
        """
        Initialize AudioHandler.

        Args:
            temp_dir: Directory for temporary audio files (default: system temp)
        """
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "telegram_voice2text"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Supported audio formats
        self.supported_formats = {".ogg", ".oga", ".mp3", ".wav", ".m4a", ".opus"}

        logger.info(f"AudioHandler initialized with temp_dir: {self.temp_dir}")

    async def download_voice_message(
        self,
        telegram_file: TelegramFile,
        file_id: str,
    ) -> Path:
        """
        Download voice message from Telegram.

        Args:
            telegram_file: Telegram File object
            file_id: Unique file identifier

        Returns:
            Path to downloaded audio file

        Raises:
            ValueError: If file format not supported or duration exceeds limit
            RuntimeError: If download fails
        """
        logger.debug(
            f"download_voice_message: file_id={file_id}, "
            f"file_size={telegram_file.file_size}, file_path={telegram_file.file_path}"
        )

        # Validate file
        if (
            telegram_file.file_size is not None and telegram_file.file_size > 20 * 1024 * 1024
        ):  # 20MB limit
            raise ValueError(f"File too large: {telegram_file.file_size} bytes")

        # Determine file extension (Telegram voice messages are usually .ogg)
        file_path = telegram_file.file_path or ""
        extension = Path(file_path).suffix or ".ogg"

        if extension not in self.supported_formats:
            raise ValueError(f"Unsupported audio format: {extension}")

        # Create unique filename with UUID suffix to avoid conflicts
        # when multiple users forward the same voice message
        unique_suffix = uuid.uuid4().hex[:8]
        audio_file = self.temp_dir / f"{file_id}_{unique_suffix}{extension}"

        logger.debug(f"Generated audio file path: {audio_file}")
        logger.info(f"Downloading voice message: {file_id} ({telegram_file.file_size} bytes)")

        try:
            # Download file
            await telegram_file.download_to_drive(audio_file)

            if not audio_file.exists():
                raise RuntimeError("Download succeeded but file not found")

            logger.info(f"Download complete: {audio_file}")
            return audio_file

        except Exception as e:
            logger.error(f"Failed to download voice message: {e}")
            # Cleanup partial download
            if audio_file.exists():
                audio_file.unlink()
            raise RuntimeError(f"Download failed: {e}") from e

    async def download_from_url(
        self,
        url: str,
        file_id: str,
        extension: str = ".ogg",
    ) -> Path:
        """
        Download audio file from URL (alternative method).

        Args:
            url: Direct URL to audio file
            file_id: Unique file identifier
            extension: File extension

        Returns:
            Path to downloaded audio file

        Raises:
            RuntimeError: If download fails
        """
        # Create unique filename with UUID suffix
        unique_suffix = uuid.uuid4().hex[:8]
        audio_file = self.temp_dir / f"{file_id}_{unique_suffix}{extension}"

        logger.info(f"Downloading from URL: {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                audio_file.write_bytes(response.content)

            logger.info(f"Download complete: {audio_file}")
            return audio_file

        except Exception as e:
            logger.error(f"Failed to download from URL: {e}")
            if audio_file.exists():
                audio_file.unlink()
            raise RuntimeError(f"Download failed: {e}") from e

    def cleanup_file(self, audio_file: Path) -> None:
        """
        Delete audio file after processing.

        Args:
            audio_file: Path to audio file to delete
        """
        try:
            if audio_file.exists():
                audio_file.unlink()
                logger.debug(f"Cleaned up audio file: {audio_file}")
        except Exception as e:
            logger.warning(f"Failed to cleanup audio file {audio_file}: {e}")

    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """
        Clean up old audio files from temp directory.

        Args:
            max_age_hours: Maximum age of files to keep (in hours)

        Returns:
            Number of files deleted
        """
        import time

        deleted_count = 0
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        try:
            for audio_file in self.temp_dir.glob("*"):
                if audio_file.is_file():
                    file_age = current_time - audio_file.stat().st_mtime
                    if file_age > max_age_seconds:
                        audio_file.unlink()
                        deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old audio files")

        except Exception as e:
            logger.warning(f"Failed to cleanup old files: {e}")

        return deleted_count

    def get_audio_duration(self, audio_file: Path) -> Optional[float]:
        """
        Get audio file duration in seconds (placeholder - would need ffprobe or similar).

        Args:
            audio_file: Path to audio file

        Returns:
            Duration in seconds or None if unavailable
        """
        # This is a placeholder - in production you'd use ffprobe or similar
        # For now, return None and rely on Whisper's duration from transcription
        return None

    def validate_audio_file(self, audio_file: Path) -> bool:
        """
        Validate audio file exists and has supported format.

        Args:
            audio_file: Path to audio file

        Returns:
            True if valid, False otherwise
        """
        if not audio_file.exists():
            logger.warning(f"Audio file does not exist: {audio_file}")
            return False

        if audio_file.suffix not in self.supported_formats:
            logger.warning(f"Unsupported audio format: {audio_file.suffix}")
            return False

        if audio_file.stat().st_size == 0:
            logger.warning(f"Audio file is empty: {audio_file}")
            return False

        return True

    def preprocess_audio(self, audio_path: Path) -> Path:
        """
        Apply audio preprocessing pipeline.

        Applies transformations in order:
        1. Mono conversion (if enabled)
        2. Speed adjustment (if enabled)

        Args:
            audio_path: Original audio file

        Returns:
            Path to preprocessed audio (or original if no preprocessing)

        Raises:
            subprocess.CalledProcessError: If preprocessing fails
        """
        logger.debug(
            f"preprocess_audio: input={audio_path.name}, "
            f"mono={settings.audio_convert_to_mono}, "
            f"speed={settings.audio_speed_multiplier}x"
        )

        path = audio_path

        # Mono conversion
        if settings.audio_convert_to_mono:
            try:
                path = self._convert_to_mono(path)
                logger.debug(f"Mono conversion output: {path}")
            except Exception as e:
                logger.warning(f"Mono conversion failed: {e}, using original")
                path = audio_path

        # Speed adjustment
        if settings.audio_speed_multiplier != 1.0:
            try:
                path = self._adjust_speed(path)
                logger.info(f"Adjusted speed {settings.audio_speed_multiplier}x: {path.name}")
                logger.debug(f"Speed adjustment output: {path}")
            except Exception as e:
                logger.warning(f"Speed adjustment failed: {e}, using original")
                path = audio_path if path == audio_path else path

        logger.debug(f"preprocess_audio: final output={path}")
        return path

    def _convert_to_mono(self, input_path: Path) -> Path:
        """
        Convert audio to mono.

        Args:
            input_path: Input audio file

        Returns:
            Path to mono audio file (or original if already mono)

        Raises:
            subprocess.CalledProcessError: If ffmpeg fails
        """
        # Check if file is already mono
        probe_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=channels",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(input_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        channels = int(probe_result.stdout.strip())

        if channels == 1:
            logger.info(f"File already mono, skipping conversion: {input_path.name}")
            return input_path

        # Get original file size
        original_size = input_path.stat().st_size
        original_size_mb = original_size / (1024 * 1024)

        output_path = input_path.parent / f"{input_path.stem}_mono.opus"

        subprocess.run(
            [
                "ffmpeg",
                "-y",  # Overwrite
                "-i",
                str(input_path),
                "-ac",
                "1",  # Mono channel
                "-acodec",
                "libopus",  # Opus codec (same as Telegram)
                "-b:a",
                "32k",  # 32 kbps bitrate (same as Telegram voice)
                "-vbr",
                "on",  # Variable bitrate for better quality
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # Get converted file size
        converted_size = output_path.stat().st_size
        converted_size_mb = converted_size / (1024 * 1024)
        size_ratio = (converted_size / original_size * 100) if original_size > 0 else 0

        logger.info(
            f"Mono conversion: original={original_size_mb:.2f}MB, "
            f"converted={converted_size_mb:.2f}MB ({size_ratio:.1f}% of original)"
        )

        return output_path

    def _adjust_speed(self, input_path: Path) -> Path:
        """
        Adjust audio playback speed.

        Args:
            input_path: Input audio file

        Returns:
            Path to speed-adjusted audio file

        Raises:
            subprocess.CalledProcessError: If ffmpeg fails
            ValueError: If speed multiplier out of range
        """
        multiplier = settings.audio_speed_multiplier
        output_path = input_path.parent / f"{input_path.stem}_speed{multiplier}x.wav"

        # Note: atempo filter only supports 0.5-2.0 range
        # For values outside, need to chain multiple filters
        if not (0.5 <= multiplier <= 2.0):
            raise ValueError(f"Speed multiplier must be 0.5-2.0, got {multiplier}")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-filter:a",
                f"atempo={multiplier}",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        return output_path
