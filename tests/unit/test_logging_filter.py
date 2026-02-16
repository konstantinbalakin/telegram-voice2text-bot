"""Tests for SensitiveDataFilter in logging configuration."""

import logging

from src.utils.logging_config import SensitiveDataFilter


class TestSensitiveDataFilter:
    def test_masks_token_in_message(self) -> None:
        f = SensitiveDataFilter(patterns=["123456:ABC-secret-token"])
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Bot token is 123456:ABC-secret-token here",
            args=None,
            exc_info=None,
        )
        f.filter(record)
        assert "ABC-secret-token" not in str(record.msg)
        assert "1234***REDACTED***" in str(record.msg)

    def test_normal_message_unchanged(self) -> None:
        f = SensitiveDataFilter(patterns=["123456:ABC-secret-token"])
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Normal log message without secrets",
            args=None,
            exc_info=None,
        )
        f.filter(record)
        assert str(record.msg) == "Normal log message without secrets"

    def test_no_patterns(self) -> None:
        f = SensitiveDataFilter(patterns=None)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Some message",
            args=None,
            exc_info=None,
        )
        f.filter(record)
        assert str(record.msg) == "Some message"

    def test_masks_in_args(self) -> None:
        f = SensitiveDataFilter(patterns=["secret123"])
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Token: %s",
            args=("secret123",),
            exc_info=None,
        )
        f.filter(record)
        assert "secret123" not in str(record.msg)
        assert "secr***REDACTED***" in str(record.msg)

    def test_masks_non_string_args(self) -> None:
        """Token in non-string args (e.g. httpx.URL objects) should be masked."""

        class FakeURL:
            """Simulates httpx.URL that contains a token in its string representation."""

            def __init__(self, url: str) -> None:
                self._url = url

            def __str__(self) -> str:
                return self._url

        f = SensitiveDataFilter(patterns=["secret123"])
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="HTTP Request: %s %s %r",
            args=("POST", FakeURL("https://api.example.com/botsecret123/getMe"), "200 OK"),
            exc_info=None,
        )
        f.filter(record)
        assert "secret123" not in str(record.msg)
        assert "secr***REDACTED***" in str(record.msg)

    def test_add_pattern(self) -> None:
        f = SensitiveDataFilter()
        f.add_pattern("new-secret")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Data: new-secret",
            args=None,
            exc_info=None,
        )
        f.filter(record)
        assert "new-secret" not in str(record.msg)

    def test_empty_patterns_ignored(self) -> None:
        f = SensitiveDataFilter(patterns=["", None, "real-secret"])  # type: ignore[list-item]
        assert len(f._patterns) == 1
        assert f._patterns[0] == "real-secret"

    def test_filter_returns_true(self) -> None:
        """Filter should always return True (we mask, not suppress)."""
        f = SensitiveDataFilter(patterns=["secret"])
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="secret data",
            args=None,
            exc_info=None,
        )
        assert f.filter(record) is True
