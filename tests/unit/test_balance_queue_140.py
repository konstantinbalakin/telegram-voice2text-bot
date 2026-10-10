"""it-002 regression: /balance shows queued renewal (#140).

Полигон: оператор оплатил продление, /balance молчал про очередь.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.billing_commands import BillingCommands
from src.storage.models import UserSubscription


def _queued(user_id: int = 1, tier_id: int = 1) -> UserSubscription:
    start = datetime(2026, 11, 9, tzinfo=timezone.utc)
    return UserSubscription(
        user_id=user_id,
        tier_id=tier_id,
        period="month",
        started_at=start,
        expires_at=start + timedelta(days=30),
        payment_provider="yookassa",
        status="queued",
    )


@pytest.fixture
def billing():
    b = MagicMock()
    b.get_user_balance = AsyncMock(
        return_value=MagicMock(
            daily_limit=30,
            daily_used=0,
            daily_remaining=30,
            bonus_minutes=0,
            package_minutes=0,
            total_available=30,
        )
    )
    return b


async def test_balance_shows_queued_renewal(billing, monkeypatch):
    sub_service = MagicMock()
    sub_service.get_active_subscription = AsyncMock(
        return_value=MagicMock(tier_id=1, expires_at=datetime(2026, 11, 9, tzinfo=timezone.utc))
    )
    sub_service.get_tier_by_id = AsyncMock(return_value=MagicMock(name="Pro"))
    sub_service.get_queued_subscription_info = AsyncMock(
        return_value=(_queued(), MagicMock(name="Pro"))
    )
    cmds = BillingCommands(
        billing_service=billing,
        subscription_service=sub_service,
        payment_service=MagicMock(),
    )

    async def fake_session():
        yield MagicMock()

    user_repo = AsyncMock()
    user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("src.bot.billing_commands.UserRepository", lambda s: user_repo)

    text, _ = await cmds.build_balance_text_and_markup(42)
    assert "Подписка" in text
    assert "Продлено" in text
    assert "09.11.2026" in text and "09.12.2026" in text


async def test_balance_no_queue_line_without_queued(billing, monkeypatch):
    sub_service = MagicMock()
    sub_service.get_active_subscription = AsyncMock(
        return_value=MagicMock(tier_id=1, expires_at=datetime(2026, 11, 9, tzinfo=timezone.utc))
    )
    sub_service.get_tier_by_id = AsyncMock(return_value=MagicMock(name="Pro"))
    sub_service.get_queued_subscription_info = AsyncMock(return_value=None)
    cmds = BillingCommands(
        billing_service=billing,
        subscription_service=sub_service,
        payment_service=MagicMock(),
    )

    user_repo = AsyncMock()
    user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("src.bot.billing_commands.UserRepository", lambda s: user_repo)

    text, _ = await cmds.build_balance_text_and_markup(42)
    assert "Продлено" not in text


async def test_balance_shows_planned_downgrade(billing, monkeypatch):
    """it-003: next_subscription_tier_id виден в /balance."""
    sub_service = MagicMock()
    active = MagicMock(
        tier_id=1,
        expires_at=datetime(2026, 11, 9, tzinfo=timezone.utc),
        next_subscription_tier_id=2,
    )
    sub_service.get_active_subscription = AsyncMock(return_value=active)
    sub_service.get_tier_by_id = AsyncMock(
        return_value=MagicMock(name="Basic", daily_limit_minutes=15.0)
    )
    sub_service.get_queued_subscription_info = AsyncMock(return_value=None)
    cmds = BillingCommands(
        billing_service=billing,
        subscription_service=sub_service,
        payment_service=MagicMock(),
    )

    user_repo = AsyncMock()
    user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("src.bot.billing_commands.UserRepository", lambda s: user_repo)

    text, _ = await cmds.build_balance_text_and_markup(42)
    assert "станет" in text
    assert "Basic" in text
    assert "15 мин/день" in text
