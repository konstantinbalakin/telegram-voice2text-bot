"""
Audio file handler for downloading and processing Telegram voice messages
"""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx
from telegram import File as TelegramFile


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
