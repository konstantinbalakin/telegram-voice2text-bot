"""Business exception hierarchy for the bot."""


class BotError(Exception):
    """Base exception for bot errors."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or message


class TranscriptionError(BotError):
    """Errors during transcription process."""

    pass


class QuotaExceededError(BotError):
    """User quota exceeded."""

    pass


class FileProcessingError(BotError):
    """Error processing audio/video file."""

    pass


class LLMProcessingError(BotError):
    """Error in LLM text processing."""

    pass


class AuthorizationError(BotError):
    """Unauthorized access attempt."""

    pass


class VariantLimitError(BotError):
    """Too many variants for transcription."""

    pass


class StateNotFoundError(BotError):
    """Transcription state not found."""

    pass
