"""Tests for TextProcessor timestamp formatting (Phase 6)."""

import pytest

from src.services.text_processor import TextProcessor


class MockSegment:
    """Mock TranscriptionSegment for testing."""

    def __init__(self, start_time: float, end_time: float, text: str, index: int = 0):
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
        self.segment_index = index


class TestFormatTime:
    """Test time formatting helper."""

    def test_format_seconds_only(self):
        """Test formatting time with only seconds."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        assert processor._format_time(45.5) == "00:45"

    def test_format_minutes_and_seconds(self):
        """Test formatting time with minutes and seconds."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        assert processor._format_time(125.3) == "02:05"

    def test_format_hours_minutes_seconds(self):
        """Test formatting time with hours, minutes, and seconds."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        assert processor._format_time(3725.7) == "01:02:05"

    def test_format_exact_minute(self):
        """Test formatting exact minute boundary."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        assert processor._format_time(60.0) == "01:00"

    def test_format_exact_hour(self):
        """Test formatting exact hour boundary."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        assert processor._format_time(3600.0) == "01:00:00"

    def test_format_zero(self):
        """Test formatting zero time."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        assert processor._format_time(0.0) == "00:00"


class TestFormatWithTimestamps:
    """Test timestamp formatting for different modes."""

    def test_format_original_mode_single_segment(self):
        """Test formatting with single segment in original mode."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        segments = [MockSegment(15.5, 30.2, "Привет, это тестовое сообщение.", 0)]

        result = processor.format_with_timestamps(segments, "base_text", mode="original")

        assert result == "[00:15] Привет, это тестовое сообщение."

    def test_format_original_mode_multiple_segments(self):
        """Test formatting with multiple segments in original mode."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        segments = [
            MockSegment(0.0, 5.0, "Первый сегмент.", 0),
            MockSegment(5.0, 10.5, "Второй сегмент.", 1),
            MockSegment(10.5, 18.2, "Третий сегмент.", 2),
        ]

        result = processor.format_with_timestamps(segments, "base_text", mode="original")

        expected = (
            "[00:00] Первый сегмент.\n"
            "[00:05] Второй сегмент.\n"
            "[00:10] Третий сегмент."
        )
        assert result == expected

    def test_format_structured_mode(self):
        """Test formatting in structured mode (same as original)."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        segments = [
            MockSegment(125.0, 145.0, "Структурированный текст.", 0),
            MockSegment(145.0, 165.0, "Еще один абзац.", 1),
        ]

        result = processor.format_with_timestamps(segments, "base_text", mode="structured")

        expected = "[02:05] Структурированный текст.\n[02:25] Еще один абзац."
        assert result == expected

    def test_format_summary_mode(self):
        """Test formatting in summary mode (simplified)."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        segments = [
            MockSegment(30.0, 60.0, "Ignored in summary", 0),
            MockSegment(60.0, 90.0, "Also ignored", 1),
        ]
        summary_text = "О чем текст: краткое резюме."

        result = processor.format_with_timestamps(segments, summary_text, mode="summary")

        assert result == "[00:30] О чем текст: краткое резюме."

    def test_format_empty_segments(self):
        """Test formatting with empty segments list."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        base_text = "Текст без таймкодов"

        result = processor.format_with_timestamps([], base_text, mode="original")

        assert result == base_text

    def test_format_long_audio_with_hours(self):
        """Test formatting segments from long audio (>1 hour)."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        segments = [
            MockSegment(3600.0, 3605.0, "Первый час прошел.", 0),
            MockSegment(7200.5, 7210.0, "Второй час.", 1),
        ]

        result = processor.format_with_timestamps(segments, "base_text", mode="original")

        expected = "[01:00:00] Первый час прошел.\n[02:00:00] Второй час."
        assert result == expected


class TestFormatTimestampsSummary:
    """Test summary-specific timestamp formatting."""

    def test_summary_uses_first_segment(self):
        """Test that summary mode uses first segment timestamp."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        segments = [
            MockSegment(45.0, 60.0, "First", 0),
            MockSegment(60.0, 75.0, "Second", 1),
            MockSegment(75.0, 90.0, "Third", 2),
        ]
        summary = "Резюме: основная мысль."

        result = processor._format_timestamps_summary(segments, summary)

        assert result == "[00:45] Резюме: основная мысль."

    def test_summary_empty_segments(self):
        """Test summary formatting with no segments."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        summary = "Резюме без таймкодов"

        result = processor._format_timestamps_summary([], summary)

        assert result == summary

    def test_summary_preserves_multiline(self):
        """Test that summary formatting preserves multiline text."""
        processor = TextProcessor(llm_service=None)  # type: ignore
        segments = [MockSegment(10.0, 20.0, "Ignored", 0)]
        summary = "О чем текст: краткое описание\n\nКлючевые моменты:\n• Пункт 1\n• Пункт 2"

        result = processor._format_timestamps_summary(segments, summary)

        expected = (
            "[00:10] О чем текст: краткое описание\n\n"
            "Ключевые моменты:\n• Пункт 1\n• Пункт 2"
        )
        assert result == expected
