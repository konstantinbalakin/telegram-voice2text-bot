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

    def initialize(self) -> None:
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

        # Check file size (OpenAI limit is 25 MB)
        file_size_mb = audio_path.stat().st_size / 1024 / 1024
        if file_size_mb > 25:
            raise ValueError(f"Audio file too large: {file_size_mb:.1f}MB (max 25MB)")

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
