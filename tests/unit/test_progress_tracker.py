"""Tests for ProgressTracker."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import RetryAfter, TelegramError, TimedOut

from src.services.progress_tracker import ProgressTracker, _format_time


class TestFormatTime:
    """Tests for _format_time helper."""

    def test_seconds_only(self):
        assert _format_time(0) == "0с"
        assert _format_time(30) == "30с"
        assert _format_time(59) == "59с"

    def test_minutes_and_seconds(self):
        assert _format_time(60) == "1м 0с"
        assert _format_time(90) == "1м 30с"
        assert _format_time(125) == "2м 5с"

    def test_large_values(self):
        assert _format_time(3600) == "60м 0с"
        assert _format_time(3661) == "61м 1с"


class TestProgressBar:
    """Tests for _generate_bar."""

    def test_zero_percent(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60)
        bar = tracker._generate_bar(0)
        assert bar == "[░░░░░░░░░░░░░░░░░░░░]"

    def test_fifty_percent(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60)
        bar = tracker._generate_bar(50)
        assert bar == "[██████████░░░░░░░░░░]"

    def test_hundred_percent(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60)
        bar = tracker._generate_bar(100)
        assert bar == "[████████████████████]"

    def test_partial_percent(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60)
        # 23% -> 4 filled blocks (23/5 = 4.6, int = 4)
        bar = tracker._generate_bar(23)
        assert bar == "[████░░░░░░░░░░░░░░░░]"


class TestProgressTrackerInit:
    """Tests for ProgressTracker initialization."""

    def test_init_defaults(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60)
        assert tracker.message is msg
        assert tracker.duration_seconds == 60
        assert tracker.estimated_total_seconds == 60 * 0.3
        assert tracker.update_interval == 5
        assert tracker._task is None
        assert tracker._stopped is False

    def test_init_custom_params(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=120, rtf=0.5, update_interval=10)
        assert tracker.duration_seconds == 120
        assert tracker.estimated_total_seconds == 120 * 0.5
        assert tracker.update_interval == 10


class TestStartStop:
    """Tests for start/stop lifecycle."""

    async def test_start_creates_task(self):
        msg = MagicMock()
        msg.edit_text = AsyncMock()
        tracker = ProgressTracker(msg, duration_seconds=60, update_interval=100)

        await tracker.start()
        try:
            assert tracker._task is not None
            assert not tracker._task.done()
        finally:
            await tracker.stop()

    async def test_stop_cancels_task(self):
        msg = MagicMock()
        msg.edit_text = AsyncMock()
        tracker = ProgressTracker(msg, duration_seconds=60, update_interval=100)

        await tracker.start()
        assert tracker._task is not None

        await tracker.stop()
        assert tracker._task is None
        assert tracker._stopped is True

    async def test_start_twice_is_noop(self):
        msg = MagicMock()
        msg.edit_text = AsyncMock()
        tracker = ProgressTracker(msg, duration_seconds=60, update_interval=100)

        await tracker.start()
        try:
            original_task = tracker._task
            await tracker.start()
            assert tracker._task is original_task
        finally:
            await tracker.stop()

    async def test_stop_when_not_started(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60)
        # Should not raise
        await tracker.stop()
        assert tracker._task is None


class TestProgressPercent:
    """Tests for get_progress_percent."""

    def test_progress_capped_at_99(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=10, rtf=0.01)
        # estimated_total = 10 * 0.01 = 0.1s, so elapsed > estimated immediately
        tracker.start_time = time.time() - 100  # 100s ago
        assert tracker.get_progress_percent() == 99

    def test_progress_at_start(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60, rtf=0.3)
        tracker.start_time = time.time()
        assert tracker.get_progress_percent() <= 1


class TestElapsedTime:
    """Tests for get_elapsed_time."""

    def test_elapsed_time(self):
        msg = MagicMock()
        tracker = ProgressTracker(msg, duration_seconds=60)
        tracker.start_time = time.time() - 5.0
        elapsed = tracker.get_elapsed_time()
        assert 4.9 < elapsed < 5.5


class TestGlobalRateLimiter:
    """Tests for global rate limiting across instances."""

    async def test_global_lock_created_lazily(self):
        ProgressTracker._reset_global_state()
        assert ProgressTracker._global_lock is None
        lock = ProgressTracker._get_global_lock()
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)

    async def test_global_lock_singleton(self):
        ProgressTracker._reset_global_state()
        lock1 = ProgressTracker._get_global_lock()
        lock2 = ProgressTracker._get_global_lock()
        assert lock1 is lock2

    async def test_reset_global_state(self):
        ProgressTracker._get_global_lock()
        ProgressTracker._global_last_update = 999.0
        ProgressTracker._reset_global_state()
        assert ProgressTracker._global_last_update == 0.0
        assert ProgressTracker._global_lock is None

    @patch("src.services.progress_tracker.get_settings")
    async def test_global_rate_limiter_enforces_interval(self, mock_get_settings):
        """Two trackers should not call edit_text faster than the global rate limit."""
        ProgressTracker._reset_global_state()

        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.1
        mock_get_settings.return_value = mock_settings

        msg1 = MagicMock()
        msg1.edit_text = AsyncMock()
        msg2 = MagicMock()
        msg2.edit_text = AsyncMock()

        tracker1 = ProgressTracker(msg1, duration_seconds=60)
        tracker2 = ProgressTracker(msg2, duration_seconds=60)

        # Call _safe_update on both trackers rapidly
        await tracker1._safe_update("text1")
        await tracker2._safe_update("text2")

        # Both should have been called (rate limiter delays but doesn't skip)
        msg1.edit_text.assert_called_once_with("text1")
        msg2.edit_text.assert_called_once_with("text2")


class TestRetryAfterHandling:
    """Tests for RetryAfter error handling."""

    @patch("src.services.progress_tracker.get_settings")
    async def test_retry_after_skips_update(self, mock_get_settings):
        """RetryAfter should not crash and should update _global_last_update."""
        ProgressTracker._reset_global_state()

        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.0
        mock_get_settings.return_value = mock_settings

        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=RetryAfter(5))

        tracker = ProgressTracker(msg, duration_seconds=60)
        old_global = ProgressTracker._global_last_update

        # Should not raise
        await tracker._safe_update("test")

        # _global_last_update should have been bumped into the future
        assert ProgressTracker._global_last_update > old_global

    @patch("src.services.progress_tracker.get_settings")
    async def test_retry_after_does_not_block(self, mock_get_settings):
        """RetryAfter should skip the update, not sleep for retry_after seconds."""
        ProgressTracker._reset_global_state()

        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.0
        mock_get_settings.return_value = mock_settings

        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=RetryAfter(30))

        tracker = ProgressTracker(msg, duration_seconds=60)

        start = time.time()
        await tracker._safe_update("test")
        elapsed = time.time() - start

        # Should complete quickly (not sleep for 30s)
        assert elapsed < 2.0


class TestTelegramErrorHandling:
    """Tests for various Telegram error handling in _safe_update."""

    @patch("src.services.progress_tracker.get_settings")
    async def test_timed_out_does_not_crash(self, mock_get_settings):
        ProgressTracker._reset_global_state()
        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.0
        mock_get_settings.return_value = mock_settings

        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=TimedOut())
        tracker = ProgressTracker(msg, duration_seconds=60)

        # Should not raise
        await tracker._safe_update("test")

    @patch("src.services.progress_tracker.get_settings")
    async def test_message_not_modified_ignored(self, mock_get_settings):
        ProgressTracker._reset_global_state()
        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.0
        mock_get_settings.return_value = mock_settings

        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=TelegramError("Message is not modified"))
        tracker = ProgressTracker(msg, duration_seconds=60)

        # Should not raise
        await tracker._safe_update("test")
        assert not tracker._stopped

    @patch("src.services.progress_tracker.get_settings")
    async def test_message_deleted_stops_tracker(self, mock_get_settings):
        ProgressTracker._reset_global_state()
        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.0
        mock_get_settings.return_value = mock_settings

        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=TelegramError("Message to edit not found"))
        tracker = ProgressTracker(msg, duration_seconds=60)

        await tracker._safe_update("test")
        assert tracker._stopped is True

    @patch("src.services.progress_tracker.get_settings")
    async def test_unexpected_error_does_not_crash(self, mock_get_settings):
        ProgressTracker._reset_global_state()
        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.0
        mock_get_settings.return_value = mock_settings

        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=RuntimeError("unexpected"))
        tracker = ProgressTracker(msg, duration_seconds=60)

        # Should not raise
        await tracker._safe_update("test")


class TestUpdateLoop:
    """Tests for the _update_loop method."""

    @patch("src.services.progress_tracker.get_settings")
    async def test_update_loop_calls_edit_text(self, mock_get_settings):
        """Update loop should call edit_text after the interval."""
        ProgressTracker._reset_global_state()

        mock_settings = MagicMock()
        mock_settings.progress_global_rate_limit = 0.0
        mock_get_settings.return_value = mock_settings

        msg = MagicMock()
        msg.edit_text = AsyncMock()

        tracker = ProgressTracker(msg, duration_seconds=60, rtf=0.3, update_interval=1)

        await tracker.start()
        try:
            # Wait enough for at least one update
            await asyncio.sleep(1.5)
        finally:
            await tracker.stop()

        assert msg.edit_text.call_count >= 1
