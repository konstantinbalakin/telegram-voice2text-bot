"""
Whisper transcription service using faster-whisper
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel

from src.config import settings

logger = logging.getLogger(__name__)


class WhisperService:
    """Service for audio transcription using faster-whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        max_workers: int = 3,
    ):
        """
        Initialize Whisper service.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (cpu or cuda)
            compute_type: Compute type (int8, float16, float32)
            max_workers: Maximum number of concurrent transcription workers
        """
        self.model_size = model_size or settings.whisper_model_size
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute_type
        self.max_workers = max_workers

        self._model: Optional[WhisperModel] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._initialized = False

        logger.info(
            f"WhisperService configured: model={self.model_size}, "
            f"device={self.device}, compute_type={self.compute_type}"
        )

    def initialize(self) -> None:
        """Initialize the Whisper model and thread pool executor."""
        if self._initialized:
            logger.warning("WhisperService already initialized")
            return

        logger.info("Initializing WhisperModel...")
        try:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
            self._initialized = True
            logger.info("WhisperModel initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WhisperModel: {e}")
            raise

    async def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = "ru",
        timeout: Optional[int] = None,
    ) -> tuple[str, float]:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file
            language: Language code (ru, en, etc.) or None for auto-detect
            timeout: Timeout in seconds (default from settings)

        Returns:
            Tuple of (transcribed_text, processing_time_seconds)

        Raises:
            TimeoutError: If transcription exceeds timeout
            RuntimeError: If service not initialized or transcription fails
        """
        if not self._initialized or self._model is None or self._executor is None:
            raise RuntimeError("WhisperService not initialized. Call initialize() first.")

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        timeout_seconds = timeout or settings.transcription_timeout

        logger.info(f"Starting transcription: {audio_path.name}, language={language}")

        try:
            # Run transcription in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            segments, info = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._transcribe_sync,
                    str(audio_path),
                    language,
                ),
                timeout=timeout_seconds,
            )

            # Combine all segments into full text
            text = " ".join([segment.text.strip() for segment in segments])

            processing_time = info.duration  # Actual audio duration processed

            logger.info(
                f"Transcription complete: {len(text)} chars, "
                f"{processing_time:.2f}s audio, language={info.language}"
            )

            return text, processing_time

        except asyncio.TimeoutError:
            logger.error(f"Transcription timeout after {timeout_seconds}s")
            raise TimeoutError(
                f"Transcription exceeded timeout of {timeout_seconds} seconds"
            )
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e

    def _transcribe_sync(
        self, audio_path: str, language: Optional[str]
    ) -> tuple[list, any]:
        """
        Synchronous transcription (runs in thread pool).

        Args:
            audio_path: Path to audio file
            language: Language code or None

        Returns:
            Tuple of (segments, info)
        """
        segments, info = self._model.transcribe(
            audio_path,
            language=language,
            beam_size=5,  # Balance between speed and accuracy
            vad_filter=True,  # Voice activity detection filter
            vad_parameters=dict(
                min_silence_duration_ms=500  # Minimum silence to split
            ),
        )

        # Convert generator to list to avoid issues with async
        segments_list = list(segments)

        return segments_list, info

    async def shutdown(self) -> None:
        """Shutdown the service and cleanup resources."""
        if not self._initialized:
            return

        logger.info("Shutting down WhisperService...")

        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

        self._model = None
        self._initialized = False

        logger.info("WhisperService shutdown complete")

    def is_initialized(self) -> bool:
        """Check if service is initialized."""
        return self._initialized


# Global instance
_whisper_service: Optional[WhisperService] = None


def get_whisper_service() -> WhisperService:
    """Get or create global WhisperService instance."""
    global _whisper_service
    if _whisper_service is None:
        _whisper_service = WhisperService()
        _whisper_service.initialize()
    return _whisper_service
