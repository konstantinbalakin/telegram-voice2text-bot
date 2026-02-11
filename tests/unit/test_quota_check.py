"""Tests for per-user quota check in BotHandlers._check_quota."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch


from src.bot.handlers import BotHandlers


def _make_user(
    daily_quota_seconds: int = 60,
    today_usage_seconds: int = 0,
    is_unlimited: bool = False,
    last_reset_date: date | None = None,
) -> MagicMock:
    """Create a mock User object for testing."""
    user = MagicMock()
    user.id = 1
    user.telegram_id = 123456
    user.username = "testuser"
    user.daily_quota_seconds = daily_quota_seconds
    user.today_usage_seconds = today_usage_seconds
    user.is_unlimited = is_unlimited
    user.last_reset_date = last_reset_date or date.today()
    user.total_usage_seconds = 0
    return user


def _make_handlers() -> BotHandlers:
    """Create a BotHandlers with mocked dependencies."""
    return BotHandlers.__new__(BotHandlers)


class TestCheckQuota:
    """Tests for BotHandlers._check_quota."""

    def test_quota_disabled_always_allows(self):
        """When enable_quota_check is False, always allow."""
        handlers = _make_handlers()
        user = _make_user(daily_quota_seconds=60, today_usage_seconds=9999)

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = False
            ok, msg = handlers._check_quota(user, 100)

        assert ok is True
        assert msg == ""

    def test_unlimited_user_always_allowed(self):
        """Unlimited users bypass quota."""
        handlers = _make_handlers()
        user = _make_user(is_unlimited=True, today_usage_seconds=9999)

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            ok, msg = handlers._check_quota(user, 100)

        assert ok is True
        assert msg == ""

    def test_within_quota_allowed(self):
        """User with remaining quota is allowed."""
        handlers = _make_handlers()
        user = _make_user(daily_quota_seconds=60, today_usage_seconds=20)

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            ok, msg = handlers._check_quota(user, 30)

        assert ok is True
        assert msg == ""

    def test_exact_quota_boundary_allowed(self):
        """Request that exactly fills quota is allowed."""
        handlers = _make_handlers()
        user = _make_user(daily_quota_seconds=60, today_usage_seconds=20)

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            ok, msg = handlers._check_quota(user, 40)

        assert ok is True
        assert msg == ""

    def test_exceeds_quota_rejected(self):
        """Request that exceeds quota is rejected."""
        handlers = _make_handlers()
        user = _make_user(daily_quota_seconds=60, today_usage_seconds=30)

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            ok, msg = handlers._check_quota(user, 40)

        assert ok is False
        assert "дневной лимит" in msg.lower() or "Достигнут дневной лимит" in msg

    def test_quota_full_rejected(self):
        """User already at quota limit is rejected."""
        handlers = _make_handlers()
        user = _make_user(daily_quota_seconds=60, today_usage_seconds=60)

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            ok, msg = handlers._check_quota(user, 1)

        assert ok is False
        assert "Достигнут дневной лимит" in msg

    def test_daily_reset_on_new_day(self):
        """Quota resets when last_reset_date is yesterday."""
        handlers = _make_handlers()
        yesterday = date.today() - timedelta(days=1)
        user = _make_user(
            daily_quota_seconds=60,
            today_usage_seconds=60,
            last_reset_date=yesterday,
        )

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            ok, msg = handlers._check_quota(user, 30)

        assert ok is True
        assert msg == ""
        assert user.today_usage_seconds == 0
        assert user.last_reset_date == date.today()

    def test_daily_reset_then_exceed(self):
        """After daily reset, request still checked against quota."""
        handlers = _make_handlers()
        yesterday = date.today() - timedelta(days=1)
        user = _make_user(
            daily_quota_seconds=60,
            today_usage_seconds=50,
            last_reset_date=yesterday,
        )

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            # After reset, usage is 0, requesting 70 > 60
            ok, msg = handlers._check_quota(user, 70)

        assert ok is False
        assert user.today_usage_seconds == 0  # Was reset

    def test_rejection_message_contains_details(self):
        """Rejection message includes usage details."""
        handlers = _make_handlers()
        user = _make_user(daily_quota_seconds=60, today_usage_seconds=50)

        with patch("src.bot.handlers.settings") as mock_settings:
            mock_settings.enable_quota_check = True
            ok, msg = handlers._check_quota(user, 20)

        assert ok is False
        assert "60" in msg  # quota
        assert "50" in msg  # used
        assert "10" in msg  # remaining
        assert "20" in msg  # requested
