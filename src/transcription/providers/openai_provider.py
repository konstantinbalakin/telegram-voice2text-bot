"""OpenAI API provider implementation."""

import asyncio
import logging
import mimetypes
import time
from pathlib import Path
from typing import Optional

import httpx

from src.config import settings
from src.transcription.models import TranscriptionContext, TranscriptionResult
from src.transcription.providers.base import TranscriptionProvider

logger = logging.getLogger(__name__)

# OpenAI API limits
OPENAI_MAX_FILE_SIZE_MB = 25
OPENAI_CONTEXT_WINDOW_CHARS = 224


class OpenAIProvider(TranscriptionProvider):
    """Transcription provider using OpenAI Whisper API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: int = 3,
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model name (default: whisper-1)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.timeout = timeout or settings.openai_timeout
        self.max_retries = max_retries

        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

        if not self.api_key:
            logger.warning("OpenAI API key not provided")

        logger.info(f"OpenAIProvider configured: model={self.model}, timeout={self.timeout}s")

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "openai"

    def get_preferred_format(self) -> Optional[str]:
        """
        Get preferred audio format based on model.

        New models (gpt-4o-transcribe, gpt-4o-mini-transcribe) require MP3/WAV.
        Legacy model (whisper-1) supports OGA natively.

        Returns:
            Preferred format ('mp3' or 'wav') for new models, None for whisper-1
        """
        from src.config import OPENAI_FORMAT_REQUIREMENTS, settings

        required_formats = OPENAI_FORMAT_REQUIREMENTS.get(self.model)

        if required_formats:  # New models - require conversion from OGA
            return settings.openai_4o_transcribe_preferred_format

        return None  # whisper-1 or other - no format requirements

    async def initialize(self) -> None:
        """Initialize the OpenAI API client."""
        if self._initialized:
            logger.warning("OpenAIProvider already initialized")
            return

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY in environment.")

        logger.info("Initializing OpenAI API client...")
        try:
            self._client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
                timeout=httpx.Timeout(self.timeout),
            )
            self._initialized = True
            logger.info("OpenAI API client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI API client: {e}")
            raise

    async def transcribe(
        self, audio_path: Path, context: TranscriptionContext
    ) -> TranscriptionResult:
        """
        Transcribe audio file using OpenAI API.

        Args:
            audio_path: Path to audio file
            context: Context information for transcription

        Returns:
            TranscriptionResult with text and metrics

        Raises:
            RuntimeError: If provider not initialized
            FileNotFoundError: If audio file doesn't exist
            Exception: For API errors
        """
        if not self._initialized or self._client is None:
            raise RuntimeError("OpenAIProvider not initialized. Call initialize() first.")

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size_mb = audio_path.stat().st_size / 1024 / 1024

        # Check duration limit for gpt-4o models
        if context.duration_seconds > settings.openai_gpt4o_max_duration:
            return await self._handle_long_audio(audio_path, context)

        api_key_masked = self.api_key[:8] + "..." if self.api_key else "None"
        logger.debug(
            f"transcribe: audio_path={audio_path}, model={self.model}, "
            f"language={context.language}, file_size={file_size_mb:.1f}MB, "
            f"api_key={api_key_masked}, max_retries={self.max_retries}"
        )
        logger.info(
            f"Starting OpenAI transcription: {audio_path.name}, "
            f"language={context.language}, size={file_size_mb:.1f}MB"
        )

        start_time = time.time()

        # Retry logic with exponential backoff
        last_exception: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # Detect MIME type based on file extension
                mime_type = mimetypes.guess_type(audio_path)[0] or "audio/mpeg"
                logger.debug(f"Detected MIME type: {mime_type} for file {audio_path.name}")

                # Prepare request
                with open(audio_path, "rb") as audio_file:
                    files = {"file": (audio_path.name, audio_file, mime_type)}
                    data = {
                        "model": self.model,
                    }

                    if context.language:
                        data["language"] = context.language

                    # Make API request
                    response = await self._client.post(
                        "/audio/transcriptions",
                        files=files,
                        data=data,
                    )

                response.raise_for_status()
                result = response.json()

                processing_time = time.time() - start_time
                text = result.get("text", "")
                language = result.get("language", context.language or "unknown")

                logger.debug(
                    f"OpenAI API response: text_length={len(text)}, language={language}, "
                    f"processing_time={processing_time:.2f}s, attempt={attempt}"
                )
                logger.info(
                    f"OpenAI transcription complete: {len(text)} chars, "
                    f"{processing_time:.2f}s processing"
                )

                return TranscriptionResult(
                    text=text,
                    language=language,
                    processing_time=processing_time,
                    audio_duration=context.duration_seconds,
                    provider_used="openai",
                    model_name=self.model,
                )

            except httpx.HTTPStatusError as e:
                last_exception = e
                status_code = e.response.status_code

                # Log detailed error information
                error_body = ""
                try:
                    error_body = e.response.text
                    logger.error(f"OpenAI API response body: {error_body}")
                except Exception:
                    pass

                # Don't retry on client errors (4xx)
                if 400 <= status_code < 500:
                    error_msg = f"OpenAI API client error ({status_code}): {e}"
                    if error_body:
                        error_msg += f" | Response: {error_body}"
                    logger.error(error_msg)
                    raise RuntimeError(f"OpenAI API error: {e}") from e

                # Retry on server errors (5xx) and rate limits (429)
                if attempt < self.max_retries:
                    wait_time = 2**attempt  # Exponential backoff: 2, 4, 8 seconds
                    logger.warning(
                        f"OpenAI API error ({status_code}), "
                        f"retrying in {wait_time}s (attempt {attempt}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"OpenAI API error after {self.max_retries} attempts: {e}")

            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Transcription error, "
                        f"retrying in {wait_time}s (attempt {attempt}/{self.max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Transcription failed after {self.max_retries} attempts: {e}")

        # All retries exhausted
        raise RuntimeError(f"OpenAI transcription failed: {last_exception}") from last_exception

    async def _handle_long_audio(
        self, audio_path: Path, context: TranscriptionContext
    ) -> TranscriptionResult:
        """
        Handle long audio files that exceed the duration limit.

        Args:
            audio_path: Path to audio file
            context: Transcription context

        Returns:
            TranscriptionResult

        Raises:
            ValueError: If both chunking and model switching are disabled
        """
        duration = context.duration_seconds
        max_duration = settings.openai_gpt4o_max_duration

        logger.info(
            f"Audio duration {duration}s exceeds limit {max_duration}s. "
            f"Chunking={settings.openai_chunking}, "
            f"ChangeModel={settings.openai_change_model}"
        )

        if settings.openai_change_model:
            # Switch model to whisper-1 for entire file (no chunking needed)
            logger.info(f"Switching model from {self.model} to whisper-1")

            original_model = self.model
            self.model = "whisper-1"

            try:
                result = await self._transcribe_single(audio_path, context)
                result.model_name = f"whisper-1 (switched from {original_model})"
                return result
            finally:
                self.model = original_model

        elif settings.openai_chunking:
            # Chunking with current model (no model switch)
            logger.info(f"Splitting audio into chunks and transcribing with {self.model}")

            start_time = time.time()

            # Split into chunks
            chunk_paths = await self._split_audio_into_chunks(audio_path, context)

            try:
                # Transcribe chunks
                if settings.openai_parallel_chunks:
                    text = await self._transcribe_chunks_parallel(chunk_paths, context, self.model)
                else:
                    text = await self._transcribe_chunks_sequential(
                        chunk_paths, context, self.model
                    )

                processing_time = time.time() - start_time

                return TranscriptionResult(
                    text=text,
                    language=context.language or "unknown",
                    processing_time=processing_time,
                    audio_duration=context.duration_seconds,
                    provider_used="openai",
                    model_name=f"{self.model} (chunked)",
                )

            finally:
                # Cleanup chunk files
                self._cleanup_chunks(chunk_paths)

        else:
            raise ValueError(
                f"Audio duration {duration}s exceeds maximum {max_duration}s for {self.model}. "
                f"Enable OPENAI_CHUNKING or OPENAI_CHANGE_MODEL to handle long files."
            )

    async def _get_duration_seconds(self, audio_path: Path) -> float:
        """
        Get audio duration via ffprobe without loading into RAM.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds

        Raises:
            RuntimeError: If ffprobe fails
        """
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"ffprobe failed for {audio_path}: {stderr.decode().strip()}")
        return float(stdout.decode().strip())

    async def _extract_chunk(
        self, audio_path: Path, chunk_path: Path, start_sec: float, duration_sec: float
    ) -> None:
        """
        Extract a single audio chunk via ffmpeg without loading into RAM.

        Args:
            audio_path: Source audio file
            chunk_path: Output chunk file path
            start_sec: Start time in seconds
            duration_sec: Chunk duration in seconds

        Raises:
            RuntimeError: If ffmpeg fails
        """
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-ss",
            str(start_sec),
            "-t",
            str(duration_sec),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(chunk_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"ffmpeg chunk extraction failed for {chunk_path}: {stderr.decode().strip()}"
            )

    async def _split_audio_into_chunks(
        self, audio_path: Path, context: TranscriptionContext
    ) -> list[Path]:
        """
        Split audio file into chunks using ffmpeg (streaming, no RAM loading).

        Args:
            audio_path: Path to original audio file
            context: Transcription context

        Returns:
            List of paths to chunk files

        Raises:
            RuntimeError: If splitting fails
        """
        import uuid

        chunk_size_sec = settings.openai_chunk_size_seconds
        overlap_sec = settings.openai_chunk_overlap_seconds
        step_sec = chunk_size_sec - overlap_sec

        logger.info(
            f"Splitting {audio_path.name} into chunks: "
            f"size={chunk_size_sec}s, "
            f"overlap={overlap_sec}s"
        )

        try:
            duration_sec = await self._get_duration_seconds(audio_path)
            duration_ms = int(duration_sec * 1000)

            chunk_size_ms = chunk_size_sec * 1000
            step_ms = step_sec * 1000

            chunk_paths: list[Path] = []
            start_ms = 0
            chunk_index = 0

            while start_ms < duration_ms:
                end_ms = min(start_ms + chunk_size_ms, duration_ms)

                chunk_filename = f"{audio_path.stem}_chunk_{chunk_index}_{uuid.uuid4().hex[:8]}.mp3"
                chunk_path = audio_path.parent / chunk_filename

                start_s = start_ms / 1000.0
                duration_chunk_s = (end_ms - start_ms) / 1000.0

                await self._extract_chunk(audio_path, chunk_path, start_s, duration_chunk_s)
                chunk_paths.append(chunk_path)

                logger.debug(
                    f"Created chunk {chunk_index}: {chunk_path.name}, "
                    f"duration={duration_chunk_s:.1f}s"
                )

                chunk_index += 1

                if end_ms >= duration_ms:
                    break

                start_ms += step_ms

            logger.info(f"Split audio into {len(chunk_paths)} chunks")
            return chunk_paths

        except Exception as e:
            logger.error(f"Failed to split audio into chunks: {e}")
            raise RuntimeError(f"Audio splitting failed: {e}") from e

    async def _transcribe_chunks_parallel(
        self, chunk_paths: list[Path], context: TranscriptionContext, model: str
    ) -> str:
        """
        Transcribe chunks in parallel (no context between chunks).

        Faster but loses context between chunks.

        Args:
            chunk_paths: List of chunk file paths
            context: Transcription context
            model: Model to use

        Returns:
            Concatenated text from all chunks
        """
        logger.info(
            f"Starting parallel transcription of {len(chunk_paths)} chunks "
            f"with {model}, max_parallel={settings.openai_max_parallel_chunks}"
        )

        # Semaphore for rate limiting
        semaphore = asyncio.Semaphore(settings.openai_max_parallel_chunks)

        async def transcribe_one_chunk(chunk_path: Path, chunk_index: int) -> tuple[int, str]:
            """Transcribe one chunk."""
            async with semaphore:
                try:
                    logger.info(f"Transcribing chunk {chunk_index + 1}/{len(chunk_paths)}")

                    # Create temporary context for chunk
                    chunk_context = TranscriptionContext(
                        user_id=context.user_id,
                        language=context.language,
                        priority=context.priority,
                    )

                    # Transcribe chunk
                    result = await self._transcribe_single_file(chunk_path, chunk_context, model)

                    logger.info(f"Chunk {chunk_index + 1} complete: {len(result.text)} chars")

                    return (chunk_index, result.text)

                except Exception as e:
                    logger.error(f"Chunk {chunk_index + 1} failed: {e}")
                    # Retry logic
                    try:
                        logger.warning(f"Retrying chunk {chunk_index + 1}")
                        result = await self._transcribe_single_file(
                            chunk_path, chunk_context, model
                        )
                        logger.info(
                            f"Chunk {chunk_index + 1} retry succeeded: {len(result.text)} chars"
                        )
                        return (chunk_index, result.text)
                    except Exception as retry_error:
                        logger.error(f"Chunk {chunk_index + 1} retry failed: {retry_error}")
                        return (chunk_index, f"[ERROR: Chunk {chunk_index + 1} failed]")

        # Launch all chunks in parallel
        tasks = [transcribe_one_chunk(chunk_path, i) for i, chunk_path in enumerate(chunk_paths)]

        results = await asyncio.gather(*tasks)

        # Sort by index and concatenate
        results_sorted = sorted(results, key=lambda x: x[0])

        # Check for errors - if any chunk failed, raise exception for fallback
        errors = [text for _, text in results_sorted if text.startswith("[ERROR")]
        if errors:
            error_details = ", ".join(
                [f"chunk {idx + 1}" for idx, text in results_sorted if text.startswith("[ERROR")]
            )
            raise RuntimeError(
                f"{len(errors)} of {len(chunk_paths)} chunks failed during transcription ({error_details})"
            )

        # All chunks succeeded - concatenate texts
        texts = [text for _, text in results_sorted]
        final_text = " ".join(texts)
        logger.info(f"Parallel transcription complete: {len(final_text)} chars total")

        return final_text

    async def _transcribe_chunks_sequential(
        self, chunk_paths: list[Path], context: TranscriptionContext, model: str
    ) -> str:
        """
        Transcribe chunks sequentially (with context between chunks).

        Slower but preserves context via prompt parameter.

        Args:
            chunk_paths: List of chunk file paths
            context: Transcription context
            model: Model to use

        Returns:
            Concatenated text from all chunks
        """
        logger.info(f"Starting sequential transcription of {len(chunk_paths)} chunks with {model}")

        transcriptions = []
        previous_text = ""

        for i, chunk_path in enumerate(chunk_paths):
            try:
                logger.info(f"Transcribing chunk {i + 1}/{len(chunk_paths)}")

                # Create context with prompt from previous chunk
                chunk_context = TranscriptionContext(
                    user_id=context.user_id,
                    language=context.language,
                    priority=context.priority,
                )

                # Transcribe with context (last OPENAI_CONTEXT_WINDOW_CHARS tokens)
                prompt = previous_text[-OPENAI_CONTEXT_WINDOW_CHARS:] if previous_text else None

                result = await self._transcribe_single_file(
                    chunk_path, chunk_context, model, prompt=prompt
                )

                transcriptions.append(result.text)
                previous_text = result.text

                logger.info(f"Chunk {i + 1} complete: {len(result.text)} chars")

            except Exception as e:
                logger.error(f"Chunk {i + 1} failed: {e}")

                # Retry without context
                try:
                    logger.warning(f"Retrying chunk {i + 1} without context")
                    result = await self._transcribe_single_file(chunk_path, chunk_context, model)
                    logger.info(f"Chunk {i + 1} retry succeeded: {len(result.text)} chars")
                    transcriptions.append(result.text)
                except Exception as retry_error:
                    logger.error(f"Chunk {i + 1} retry failed: {retry_error}")
                    transcriptions.append(f"[ERROR: Chunk {i + 1} failed]")

        # Check for errors - if any chunk failed, raise exception for fallback
        errors = [t for t in transcriptions if t.startswith("[ERROR")]
        if errors:
            failed_chunks = ", ".join(
                [str(i + 1) for i, t in enumerate(transcriptions) if t.startswith("[ERROR")]
            )
            raise RuntimeError(
                f"{len(errors)} of {len(chunk_paths)} chunks failed during transcription (chunks: {failed_chunks})"
            )

        # All chunks succeeded - concatenate texts
        final_text = " ".join(transcriptions)
        logger.info(f"Sequential transcription complete: {len(final_text)} chars total")

        return final_text

    async def _transcribe_single_file(
        self,
        audio_path: Path,
        context: TranscriptionContext,
        model: str,
        prompt: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe a single file (helper for chunking).

        Args:
            audio_path: Path to audio file
            context: Transcription context
            model: Model to use
            prompt: Optional prompt for context

        Returns:
            TranscriptionResult
        """
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")

        file_size_mb = audio_path.stat().st_size / 1024 / 1024
        if file_size_mb > OPENAI_MAX_FILE_SIZE_MB:
            logger.warning(
                f"Chunk size {file_size_mb:.1f}MB exceeds OpenAI limit {OPENAI_MAX_FILE_SIZE_MB}MB. "
                "This may cause API errors. Consider reducing chunk size."
            )

        start_time = time.time()

        try:
            mime_type = mimetypes.guess_type(audio_path)[0] or "audio/mpeg"

            with open(audio_path, "rb") as audio_file:
                files = {"file": (audio_path.name, audio_file, mime_type)}
                data = {"model": model}

                if context.language:
                    data["language"] = context.language

                if prompt:
                    data["prompt"] = prompt

                response = await self._client.post(
                    "/audio/transcriptions",
                    files=files,
                    data=data,
                )

            response.raise_for_status()
            result = response.json()

            processing_time = time.time() - start_time
            text = result.get("text", "")
            language = result.get("language", context.language or "unknown")

            return TranscriptionResult(
                text=text,
                language=language,
                processing_time=processing_time,
                audio_duration=0,  # Unknown for chunks
                provider_used="openai",
                model_name=model,
            )

        except Exception as e:
            logger.error(f"Transcription failed for {audio_path.name}: {e}")
            raise

    async def _transcribe_single(
        self, audio_path: Path, context: TranscriptionContext
    ) -> TranscriptionResult:
        """
        Transcribe entire file without chunking (used for model switching).

        Args:
            audio_path: Path to audio file
            context: Transcription context

        Returns:
            TranscriptionResult
        """
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")

        start_time = time.time()

        # Retry logic with exponential backoff
        last_exception: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # Detect MIME type based on file extension
                mime_type = mimetypes.guess_type(audio_path)[0] or "audio/mpeg"

                # Prepare request
                with open(audio_path, "rb") as audio_file:
                    files = {"file": (audio_path.name, audio_file, mime_type)}
                    data = {"model": self.model}

                    if context.language:
                        data["language"] = context.language

                    # Make API request
                    response = await self._client.post(
                        "/audio/transcriptions",
                        files=files,
                        data=data,
                    )

                response.raise_for_status()
                result = response.json()

                processing_time = time.time() - start_time
                text = result.get("text", "")
                language = result.get("language", context.language or "unknown")

                return TranscriptionResult(
                    text=text,
                    language=language,
                    processing_time=processing_time,
                    audio_duration=context.duration_seconds,
                    provider_used="openai",
                    model_name=self.model,
                )

            except httpx.HTTPStatusError as e:
                last_exception = e
                status_code = e.response.status_code

                # Don't retry on client errors (4xx)
                if 400 <= status_code < 500:
                    raise RuntimeError(f"OpenAI API error: {e}") from e

                # Retry on server errors (5xx) and rate limits (429)
                if attempt < self.max_retries:
                    wait_time = 2**attempt
                    logger.warning(
                        f"OpenAI API error ({status_code}), "
                        f"retrying in {wait_time}s (attempt {attempt}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Transcription error, "
                        f"retrying in {wait_time}s (attempt {attempt}/{self.max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        raise RuntimeError(f"OpenAI transcription failed: {last_exception}") from last_exception

    def _cleanup_chunks(self, chunk_paths: list[Path]) -> None:
        """
        Delete temporary chunk files.

        Args:
            chunk_paths: List of chunk file paths
        """
        for chunk_path in chunk_paths:
            try:
                if chunk_path.exists():
                    chunk_path.unlink()
                    logger.debug(f"Cleaned up chunk: {chunk_path.name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup chunk {chunk_path.name}: {e}")

    async def shutdown(self) -> None:
        """Shutdown the provider and cleanup resources."""
        if not self._initialized:
            return

        logger.info("Shutting down OpenAIProvider...")

        if self._client:
            await self._client.aclose()
            self._client = None

        self._initialized = False

        logger.info("OpenAIProvider shutdown complete")

    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._initialized
