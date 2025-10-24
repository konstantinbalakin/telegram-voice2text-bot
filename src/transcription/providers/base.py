"""Abstract base class for transcription providers."""

from abc import ABC, abstractmethod
from pathlib import Path

from src.transcription.models import TranscriptionContext, TranscriptionResult


class TranscriptionProvider(ABC):
    """Abstract base class for all transcription providers."""

    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the provider (load models, setup resources).

        This method should be called before using the provider.
        Must be idempotent - multiple calls should be safe.

        Raises:
            Exception: If initialization fails
        """
        pass

    @abstractmethod
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
            Exception: For other transcription errors
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shutdown the provider and cleanup resources.

        This method should be called when the provider is no longer needed.
        Must be idempotent - multiple calls should be safe.
        """
        pass

    @abstractmethod
    def is_initialized(self) -> bool:
        """
        Check if provider is initialized and ready to use.

        Returns:
            True if initialized, False otherwise
        """
        pass
