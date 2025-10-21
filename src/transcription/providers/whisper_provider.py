"""Original OpenAI Whisper provider implementation."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import psutil

# Conditional import - whisper is optional
try:
    import whisper  # type: ignore[import-untyped]

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    whisper = None

from src.config import settings
from src.transcription.models import TranscriptionContext, TranscriptionResult
from src.transcription.providers.base import TranscriptionProvider

logger = logging.getLogger(__name__)


class WhisperProvider(TranscriptionProvider):
    """Transcription provider using original OpenAI Whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        max_workers: int = 3,
    ):
        """
        Initialize Whisper provider.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (cpu or cuda)
            max_workers: Maximum number of concurrent transcription workers
        """
        if not WHISPER_AVAILABLE:
            raise ImportError(
                "Original OpenAI Whisper is not installed. "
                "Install with: poetry install --extras='openai-whisper'"
            )

        self.model_size = model_size or settings.whisper_model_size
        self.device = device or settings.whisper_device
        self.max_workers = max_workers

        self._model: Optional[whisper.Whisper] = None  # type: ignore
        self._executor: Optional[ThreadPoolExecutor] = None
        self._initialized = False
        self._process = psutil.Process()

        logger.info(f"WhisperProvider configured: model={self.model_size}, device={self.device}")

    def initialize(self) -> None:
        """Initialize the Whisper model and thread pool executor."""
        if self._initialized:
            logger.warning("WhisperProvider already initialized")
            return

        if not WHISPER_AVAILABLE:
            raise ImportError("Original OpenAI Whisper is not installed")

        logger.info(f"Initializing Whisper model: {self.model_size}...")
        try:
            self._model = whisper.load_model(self.model_size, device=self.device)
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
            self._initialized = True
            logger.info("Whisper model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Whisper model: {e}")
            raise

    async def transcribe(
        self, audio_path: Path, context: TranscriptionContext
    ) -> TranscriptionResult:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file
            context: Context information for transcription

        Returns:
            TranscriptionResult with text and metrics

        Raises:
            RuntimeError: If provider not initialized
            FileNotFoundError: If audio file doesn't exist
            TimeoutError: If transcription times out
        """
        if not self._initialized or self._model is None or self._executor is None:
            raise RuntimeError("WhisperProvider not initialized. Call initialize() first.")

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        timeout_seconds = settings.transcription_timeout

        logger.info(
            f"Starting transcription: {audio_path.name}, "
            f"language={context.language}, model={self.model_size}"
        )

        # Track resource usage
        start_memory = self._process.memory_info().rss / 1024 / 1024  # MB
        start_time = time.time()

        try:
            # Run transcription in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._transcribe_sync,
                    str(audio_path),
                    context.language,
                ),
                timeout=timeout_seconds,
            )

            processing_time = time.time() - start_time

            # Measure peak memory
            end_memory = self._process.memory_info().rss / 1024 / 1024  # MB
            peak_memory = max(start_memory, end_memory)

            text = result["text"].strip()
            language = result.get("language", context.language or "unknown")

            # Calculate audio duration from segments if available
            audio_duration = context.duration_seconds
            if "segments" in result and result["segments"]:
                last_segment = result["segments"][-1]
                audio_duration = last_segment.get("end", audio_duration)

            logger.info(
                f"Transcription complete: {len(text)} chars, "
                f"{audio_duration:.2f}s audio, {processing_time:.2f}s processing, "
                f"language={language}, RTF={processing_time/audio_duration:.2f}x"
            )

            return TranscriptionResult(
                text=text,
                language=language,
                processing_time=processing_time,
                audio_duration=audio_duration,
                provider_used="whisper",
                model_name=self.model_size,
                peak_memory_mb=peak_memory,
            )

        except asyncio.TimeoutError:
            logger.error(f"Transcription timeout after {timeout_seconds}s")
            raise TimeoutError(f"Transcription exceeded timeout of {timeout_seconds} seconds")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e

    def _transcribe_sync(self, audio_path: str, language: Optional[str]) -> dict:  # type: ignore[type-arg]
        """
        Synchronous transcription (runs in thread pool).

        Args:
            audio_path: Path to audio file
            language: Language code or None

        Returns:
            Transcription result dictionary
        """
        if self._model is None:
            raise RuntimeError("Model not initialized")

        logger.debug(f"Calling whisper.transcribe(audio={audio_path}, language={language})")

        # Try transcription with various parameters to handle edge cases
        result = self._model.transcribe(
            audio_path,
            language=language,
            verbose=True,  # Enable verbose for debugging
            task="transcribe",  # Explicitly set task
            fp16=False,  # Disable FP16 (not supported on CPU anyway)
        )

        logger.debug(
            f"Whisper raw result - text length: {len(result.get('text', ''))}, "
            f"segments: {len(result.get('segments', []))}, "
            f"language: {result.get('language', 'unknown')}"
        )

        if "segments" in result and result["segments"]:
            for i, seg in enumerate(result["segments"][:3]):  # Log first 3 segments
                logger.debug(
                    f"Segment {i}: start={seg.get('start')}, end={seg.get('end')}, "
                    f"text='{seg.get('text', '')}'"
                )

        return result

    async def shutdown(self) -> None:
        """Shutdown the provider and cleanup resources."""
        if not self._initialized:
            return

        logger.info("Shutting down WhisperProvider...")

        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

        self._model = None
        self._initialized = False

        logger.info("WhisperProvider shutdown complete")

    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._initialized
