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

    def _get_audio_codec(self, file_path: Path) -> str:
        """
        Get audio codec of a file.

        Args:
            file_path: Path to audio file

        Returns:
            Codec name (e.g., 'opus', 'mp3', 'pcm_s16le')

        Raises:
            subprocess.CalledProcessError: If ffprobe fails
        """
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _get_audio_channels(self, file_path: Path) -> int:
        """
        Get number of audio channels.

        Args:
            file_path: Path to audio file

        Returns:
            Number of channels (1=mono, 2=stereo, etc.)

        Raises:
            subprocess.CalledProcessError: If ffprobe fails
        """
        result = subprocess.run(
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
                str(file_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(result.stdout.strip())

    def _get_audio_sample_rate(self, file_path: Path) -> int:
        """
        Get audio sample rate.

        Args:
            file_path: Path to audio file

        Returns:
            Sample rate in Hz (e.g., 16000, 48000)

        Raises:
            subprocess.CalledProcessError: If ffprobe fails
        """
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(result.stdout.strip())

    def preprocess_audio(
        self,
        audio_path: Path,
        target_provider: Optional[str] = None,
    ) -> Path:
        """
        Apply intelligent audio preprocessing pipeline.

        Applies transformations in order:
        1. Provider-specific format optimization (if target_provider specified)
        2. Mono conversion (if enabled and file is stereo)
        3. Speed adjustment (if enabled)

        Smart preprocessing:
        - Optimizes format for target provider (e.g., MP3 for OpenAI gpt-4o models)
        - Skips mono conversion if file is already mono
        - Uses efficient Opus codec for local processing
        - Optimizes sample rate for Whisper (16kHz)

        Args:
            audio_path: Original audio file
            target_provider: Target provider name for format optimization (optional)

        Returns:
            Path to preprocessed audio (or original if no preprocessing needed)

        Raises:
            subprocess.CalledProcessError: If preprocessing fails
        """
        logger.debug(
            f"preprocess_audio: input={audio_path.name}, "
            f"provider={target_provider}, "
            f"mono_enabled={settings.audio_convert_to_mono}, "
            f"speed={settings.audio_speed_multiplier}x"
        )

        path = audio_path

        # Format optimization based on provider
        if target_provider:
            try:
                path = self._optimize_for_provider(path, target_provider)
                if path != audio_path:
                    logger.info(f"Optimized for {target_provider}: {path.name}")
            except Exception as e:
                logger.warning(f"Provider optimization failed: {e}, using original")
                path = audio_path

        # Mono conversion (if not already done by optimization)
        if settings.audio_convert_to_mono and path == audio_path:
            try:
                path = self._convert_to_mono(path)
                if path != audio_path:
                    logger.info(f"Converted to mono: {path.name}")
            except Exception as e:
                logger.warning(f"Mono conversion failed: {e}, using original")
                path = audio_path

        # Speed adjustment
        if settings.audio_speed_multiplier != 1.0:
            try:
                path = self._adjust_speed(path)
                logger.info(f"Adjusted speed {settings.audio_speed_multiplier}x: " f"{path.name}")
            except Exception as e:
                logger.warning(f"Speed adjustment failed: {e}, using original")

        if path == audio_path:
            logger.debug("No preprocessing applied, using original file")
        else:
            logger.debug(f"Preprocessing complete: {path}")

        return path

    def _convert_to_mono(self, input_path: Path) -> Path:
        """
        Convert audio to mono with optimal settings for Whisper.

        Smart preprocessing:
        - Skips conversion only if file is BOTH mono AND opus
        - Converts if stereo (any format) OR not opus (any channels)

        Args:
            input_path: Input audio file

        Returns:
            Path to mono opus audio file (or original if already optimal)

        Raises:
            subprocess.CalledProcessError: If ffmpeg fails
        """
        # Check if file is already optimal (mono + opus)
        channels = self._get_audio_channels(input_path)
        codec = self._get_audio_codec(input_path)

        if channels == 1 and codec == "opus":
            logger.info(f"File already mono Opus, skipping conversion: {input_path.name}")
            return input_path

        # Log reason for conversion
        if channels > 1:
            logger.info(f"Converting to mono (current: {channels} channels): {input_path.name}")
        elif codec != "opus":
            logger.info(f"Converting to Opus (current codec: {codec}): {input_path.name}")

        # Get original file info for logging
        original_size = input_path.stat().st_size
        original_size_mb = original_size / (1024 * 1024)

        output_path = input_path.parent / f"{input_path.stem}_mono.ogg"

        # Convert to mono with Whisper-optimal settings
        # Use .ogg container for OpenAI compatibility (doesn't support .opus extension)
        subprocess.run(
            [
                "ffmpeg",
                "-y",  # Overwrite
                "-i",
                str(input_path),
                "-ac",
                "1",  # Mono channel
                "-ar",
                str(settings.audio_target_sample_rate),  # Resample (16kHz optimal for Whisper)
                "-acodec",
                "libopus",  # Opus codec (efficient compression)
                "-b:a",
                "32k",  # 32 kbps bitrate (optimal for speech)
                "-vbr",
                "on",  # Variable bitrate for better quality
                "-f",
                "ogg",  # OGG container format (OpenAI compatible)
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
        Adjust audio playback speed with optimal output format.

        Args:
            input_path: Input audio file

        Returns:
            Path to speed-adjusted audio file (OGG format for OpenAI compatibility)

        Raises:
            subprocess.CalledProcessError: If ffmpeg fails
            ValueError: If speed multiplier out of range
        """
        multiplier = settings.audio_speed_multiplier
        output_path = input_path.parent / f"{input_path.stem}_speed{multiplier}x.ogg"

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
                "-acodec",
                "libopus",  # Use Opus codec for efficient compression
                "-b:a",
                "32k",  # 32 kbps bitrate (optimal for speech)
                "-vbr",
                "on",  # Variable bitrate for better quality
                "-f",
                "ogg",  # OGG container format (OpenAI compatible)
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        return output_path

    def _optimize_for_provider(
        self,
        input_path: Path,
        provider_name: str,
    ) -> Path:
        """
        Optimize audio format for specific provider.

        Args:
            input_path: Input audio file
            provider_name: Target provider (e.g., 'openai', 'faster-whisper')

        Returns:
            Path to optimized audio file (or original if no optimization needed)
        """
        from src.config import OPENAI_FORMAT_REQUIREMENTS

        # OpenAI provider optimization
        if provider_name == "openai":
            # Determine if conversion needed based on model
            model = settings.openai_model
            required_formats = OPENAI_FORMAT_REQUIREMENTS.get(model)

            if required_formats:
                # New models (gpt-4o-*) - require MP3/WAV
                current_ext = input_path.suffix.lower()

                if current_ext in [".oga", ".ogg", ".opus"]:
                    # Convert to preferred format
                    target_format = settings.openai_4o_transcribe_preferred_format

                    if target_format == "mp3":
                        return self._convert_to_mp3(input_path)
                    elif target_format == "wav":
                        return self._convert_to_wav(input_path)
                    else:
                        logger.warning(f"Unknown format {target_format}, using mp3")
                        return self._convert_to_mp3(input_path)
                else:
                    logger.debug(f"Format {current_ext} already supported by {model}")
                    return input_path
            else:
                # Old model (whisper-1) - supports OGA
                logger.debug(f"Model {model} supports OGA format")
                return input_path

        # FasterWhisper - prefer OGA (efficient)
        elif provider_name == "faster-whisper":
            # OGA is optimal for local processing, keep as is
            logger.debug("FasterWhisper: using original format (optimal)")
            return input_path

        # Unknown provider - no optimization
        else:
            logger.debug(f"No optimization for provider: {provider_name}")
            return input_path

    def _convert_to_mp3(self, input_path: Path) -> Path:
        """
        Convert audio to MP3 format optimized for speech recognition.

        Args:
            input_path: Input audio file

        Returns:
            Path to MP3 audio file

        Raises:
            subprocess.CalledProcessError: If ffmpeg fails
        """
        original_size = input_path.stat().st_size
        original_size_mb = original_size / (1024 * 1024)

        output_path = input_path.parent / f"{input_path.stem}_converted.mp3"

        logger.info(f"Converting to MP3: {input_path.name} " f"({original_size_mb:.2f}MB)")

        # Convert to MP3 with speech-optimized settings
        subprocess.run(
            [
                "ffmpeg",
                "-y",  # Overwrite
                "-i",
                str(input_path),
                "-ac",
                "1",  # Mono
                "-ar",
                "16000",  # 16kHz sample rate (optimal for Whisper)
                "-b:a",
                "64k",  # 64 kbps bitrate (good quality for speech)
                "-acodec",
                "libmp3lame",  # MP3 codec
                "-q:a",
                "2",  # Quality level (2 = high quality)
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        converted_size = output_path.stat().st_size
        converted_size_mb = converted_size / (1024 * 1024)
        size_ratio = (converted_size / original_size * 100) if original_size > 0 else 0

        logger.info(
            f"MP3 conversion complete: "
            f"original={original_size_mb:.2f}MB, "
            f"converted={converted_size_mb:.2f}MB "
            f"({size_ratio:.1f}% of original)"
        )

        # Warn if approaching 25MB limit
        if converted_size_mb > 20:
            logger.warning(
                f"Converted file size {converted_size_mb:.2f}MB " f"approaching OpenAI limit (25MB)"
            )

        return output_path

    def _convert_to_wav(self, input_path: Path) -> Path:
        """
        Convert audio to WAV format (PCM 16-bit).

        Args:
            input_path: Input audio file

        Returns:
            Path to WAV audio file

        Note:
            WAV files are larger than MP3 but avoid double compression.
            Use only if quality is critical and file size is small.
        """
        original_size_mb = input_path.stat().st_size / (1024 * 1024)
        output_path = input_path.parent / f"{input_path.stem}_converted.wav"

        logger.info(f"Converting to WAV: {input_path.name}")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-ac",
                "1",  # Mono
                "-ar",
                "16000",  # 16kHz
                "-acodec",
                "pcm_s16le",  # PCM 16-bit
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        converted_size_mb = output_path.stat().st_size / (1024 * 1024)

        logger.info(
            f"WAV conversion complete: " f"{original_size_mb:.2f}MB → {converted_size_mb:.2f}MB"
        )

        if converted_size_mb > 20:
            logger.warning(f"WAV file {converted_size_mb:.2f}MB may exceed OpenAI limit")

        return output_path
