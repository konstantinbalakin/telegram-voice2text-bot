"""Tests for business exception hierarchy."""

from src.exceptions import (
    AuthorizationError,
    BotError,
    FileProcessingError,
    LLMProcessingError,
    QuotaExceededError,
    StateNotFoundError,
    TranscriptionError,
    VariantLimitError,
)


class TestBotError:
    def test_message(self) -> None:
        err = BotError("internal error")
        assert str(err) == "internal error"

    def test_user_message_defaults_to_message(self) -> None:
        err = BotError("something broke")
        assert err.user_message == "something broke"

    def test_user_message_override(self) -> None:
        err = BotError("db timeout", user_message="Please try again later")
        assert str(err) == "db timeout"
        assert err.user_message == "Please try again later"


class TestExceptionHierarchy:
    def test_all_inherit_bot_error(self) -> None:
        subclasses = [
            TranscriptionError,
            QuotaExceededError,
            FileProcessingError,
            LLMProcessingError,
            AuthorizationError,
            VariantLimitError,
            StateNotFoundError,
        ]
        for cls in subclasses:
            err = cls("test")
            assert isinstance(err, BotError), f"{cls.__name__} must inherit BotError"
            assert isinstance(err, Exception)

    def test_user_message_propagated(self) -> None:
        err = TranscriptionError("whisper failed", user_message="Could not transcribe")
        assert err.user_message == "Could not transcribe"
        assert str(err) == "whisper failed"

    def test_each_exception_is_catchable(self) -> None:
        try:
            raise QuotaExceededError("limit reached")
        except BotError as e:
            assert e.user_message == "limit reached"

    def test_str_output(self) -> None:
        err = FileProcessingError("bad format")
        assert str(err) == "bad format"
