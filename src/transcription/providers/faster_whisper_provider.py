"""FasterWhisper provider implementation."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

import psutil
from faster_whisper import WhisperModel  # type: ignore[import-untyped]

from src.config import settings
from src.transcription.models import TranscriptionContext, TranscriptionResult, TranscriptionSegment
from src.transcription.providers.base import TranscriptionProvider

logger = logging.getLogger(__name__)


class FastWhisperProvider(TranscriptionProvider):
    """Transcription provider using faster-whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        beam_size: Optional[int] = None,
        vad_filter: Optional[bool] = None,
        max_workers: int = 3,
    ):
        """
        Initialize FasterWhisper provider.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v2, large-v3)
            device: Device to use (cpu or cuda)
            compute_type: Compute type (int8, float16, float32)
            beam_size: Beam size for decoding (1=greedy, 5=default, 10=high quality)
            vad_filter: Enable voice activity detection filter
            max_workers: Maximum number of concurrent transcription workers
        """
        self.model_size = model_size or settings.faster_whisper_model_size
        self.device = device or settings.faster_whisper_device
        self.compute_type = compute_type or settings.faster_whisper_compute_type
        self.beam_size = beam_size or settings.faster_whisper_beam_size
        self.vad_filter = (
            vad_filter if vad_filter is not None else settings.faster_whisper_vad_filter
        )
        self.max_workers = max_workers

        self._model: Optional[WhisperModel] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._initialized = False
        self._process = psutil.Process()

        logger.info(
            f"FastWhisperProvider configured: model={self.model_size}, "
            f"device={self.device}, compute_type={self.compute_type}, "
            f"beam_size={self.beam_size}, vad_filter={self.vad_filter}"
        )

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "faster-whisper"

    def initialize(self) -> None:
        """Initialize the Whisper model and thread pool executor."""
        if self._initialized:
            logger.warning("FastWhisperProvider already initialized")
            return

        logger.debug(
            f"initialize: model_size={self.model_size}, device={self.device}, "
            f"compute_type={self.compute_type}, max_workers={self.max_workers}"
        )
        logger.info(f"Initializing FasterWhisper model: {self.model_size}...")
        try:
            start_time = time.time()
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
            self._initialized = True
            init_time = time.time() - start_time
            logger.debug(f"Model initialization took {init_time:.2f}s")
            logger.info("FasterWhisper model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize FasterWhisper model: {e}")
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
            raise RuntimeError("FastWhisperProvider not initialized. Call initialize() first.")

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        timeout_seconds = settings.transcription_timeout

        logger.debug(
            f"transcribe: audio_path={audio_path}, language={context.language}, "
            f"beam_size={self.beam_size}, vad_filter={self.vad_filter}, "
            f"timeout={timeout_seconds}s"
        )
        logger.info(
            f"Starting transcription: {audio_path.name}, "
            f"language={context.language}, model={self.model_size}"
        )

        # Track resource usage
        start_memory = self._process.memory_info().rss / 1024 / 1024  # MB
        start_time = time.time()
        logger.debug(f"Memory before transcription: {start_memory:.2f} MB")

        try:
            # Run transcription in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            segments, info = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._transcribe_sync,
                    str(audio_path),
                    context.language,
                ),
                timeout=timeout_seconds,
            )

            # Combine all segments into full text
            text = " ".join([segment.text.strip() for segment in segments])

            # Convert faster-whisper segments to TranscriptionSegment objects
            transcription_segments = [
                TranscriptionSegment(start=seg.start, end=seg.end, text=seg.text.strip())
                for seg in segments
            ]

            processing_time = time.time() - start_time
            audio_duration = info.duration

            # Measure peak memory
            end_memory = self._process.memory_info().rss / 1024 / 1024  # MB
            peak_memory = max(start_memory, end_memory)

            logger.debug(
                f"Transcription result: text_length={len(text)}, segments={len(segments)}, "
                f"audio_duration={audio_duration:.2f}s, processing_time={processing_time:.2f}s, "
                f"detected_language={info.language}, memory_delta={end_memory-start_memory:.2f} MB"
            )
            logger.info(
                f"Transcription complete: {len(text)} chars, "
                f"{audio_duration:.2f}s audio, {processing_time:.2f}s processing, "
                f"language={info.language}, RTF={processing_time/audio_duration:.2f}x"
            )

            return TranscriptionResult(
                text=text,
                language=info.language,
                confidence=None,  # faster-whisper doesn't provide overall confidence
                processing_time=processing_time,
                audio_duration=audio_duration,
                provider_used="faster-whisper",
                model_name=self.model_size,
                peak_memory_mb=peak_memory,
                segments=transcription_segments,
            )

        except asyncio.TimeoutError:
            logger.error(f"Transcription timeout after {timeout_seconds}s")
            raise TimeoutError(f"Transcription exceeded timeout of {timeout_seconds} seconds")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e

    def _transcribe_sync(self, audio_path: str, language: Optional[str]) -> tuple[list[Any], Any]:
        """
        Synchronous transcription (runs in thread pool).

        Args:
            audio_path: Path to audio file
            language: Language code or None

        Returns:
            Tuple of (segments, info)
        """
        if self._model is None:
            raise RuntimeError("Model not initialized")

        vad_parameters = dict(min_silence_duration_ms=500) if self.vad_filter else None

        segments, info = self._model.transcribe(
            audio_path,
            language=language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            vad_parameters=vad_parameters,
        )

        # Convert generator to list to avoid issues with async
        segments_list = list(segments)

        return segments_list, info

    async def shutdown(self) -> None:
        """Shutdown the provider and cleanup resources."""
        if not self._initialized:
            return

        logger.info("Shutting down FastWhisperProvider...")

        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

        self._model = None
        self._initialized = False

        logger.info("FastWhisperProvider shutdown complete")

    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._initialized
