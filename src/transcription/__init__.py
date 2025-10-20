"""Transcription services package."""

from src.transcription.audio_handler import AudioHandler
from src.transcription.factory import (
    get_transcription_router,
    shutdown_transcription_router,
)
from src.transcription.models import (
    BenchmarkConfig,
    BenchmarkReport,
    TranscriptionContext,
    TranscriptionResult,
)
from src.transcription.routing.router import TranscriptionRouter

# Legacy imports for backward compatibility
from src.transcription.whisper_service import WhisperService, get_whisper_service

__all__ = [
    "AudioHandler",
    # New API
    "get_transcription_router",
    "shutdown_transcription_router",
    "TranscriptionRouter",
    "TranscriptionContext",
    "TranscriptionResult",
    "BenchmarkConfig",
    "BenchmarkReport",
    # Legacy API (deprecated)
    "WhisperService",
    "get_whisper_service",
]
