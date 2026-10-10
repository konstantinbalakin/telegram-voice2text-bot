"""it-006 regression: /balance дневной лимит из активной подписки (#140).

Полигон: юзер с active Basic (daily_limit_minutes=15) видел в /balance
«Дневной лимит: 10 мин» — подписочный слой показывал подписку верно,
лимит приходил из балансового слоя (дефолт conditions).

Причина: build_balance_text_and_markup вызывал get_user_balance ДО
get_active_subscription — ленивая активация очереди (волна 3) ещё не
поднимала due-queued строку, и биллинг считал лимит по conditions/дефолту.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.billing_commands import BillingCommands
from src.services.payments.base import UserBalance
from tests.conftest import make_billing_service

# =============================================================================
# Сервисный уровень: BillingService учитывает лимит активной подписки
# =============================================================================


@pytest.mark.asyncio
async def test_get_user_balance_daily_limit_from_active_subscription():
    """Active-подписка Basic (tier daily_limit_minutes=15) → daily_limit == 15."""
    service, mocks = make_billing_service()

    mock_sub = MagicMock()
    mock_sub.tier = MagicMock()
    mock_sub.tier.daily_limit_minutes = 15.0
    mocks["subscription_repo"].get_active_subscription_with_tier.return_value = mock_sub
    mocks["condition_repo"].get_effective_value.return_value = "10"
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    balance = await service.get_user_balance(user_id=1)

    assert balance.daily_limit == 15.0
    mocks["condition_repo"].get_effective_value.assert_not_called()


@pytest.mark.asyncio
async def test_get_user_balance_daily_limit_pro_tier_30():
    """Active Pro (30 мин) → daily_limit == 30."""
    service, mocks = make_billing_service()

    mock_sub = MagicMock()
    mock_sub.tier = MagicMock()
    mock_sub.tier.daily_limit_minutes = 30.0
    mocks["subscription_repo"].get_active_subscription_with_tier.return_value = mock_sub
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    balance = await service.get_user_balance(user_id=1)

    assert balance.daily_limit == 30.0


@pytest.mark.asyncio
async def test_get_user_balance_without_subscription_uses_condition():
    """Без подписки — прежний путь: conditions → 10."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription_with_tier.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    balance = await service.get_user_balance(user_id=1)

    assert balance.daily_limit == 10.0


@pytest.mark.asyncio
async def test_get_user_balance_without_subscription_default_10():
    """Без подписки и без conditions — дефолт 10."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription_with_tier.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = None
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    balance = await service.get_user_balance(user_id=1)

    assert balance.daily_limit == 10.0


# =============================================================================
# Бот-уровень: get_active_subscription вызывается ДО get_user_balance
# (ленивая активация очереди должна успеть сработать до расчёта лимита)
# ==============================================================================


def _make_cmds(billing_service, subscription_service) -> BillingCommands:
    return BillingCommands(
        billing_service=billing_service,
        subscription_service=subscription_service,
        payment_service=AsyncMock(),
    )


async def _run_balance_screen(cmds: BillingCommands) -> str:
    with patch("src.bot.billing_commands.get_session") as mock_session:
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
            mock_user_repo = AsyncMock()
            mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
            MockUserRepo.return_value = mock_user_repo
            text, _ = await cmds.build_balance_text_and_markup(42)
    return text


@pytest.mark.asyncio
async def test_balance_activates_subscription_before_limit_calc():
    """Порядок: get_active_subscription строго раньше get_user_balance."""
    billing_service = AsyncMock()
    billing_service.get_user_balance = AsyncMock(
        return_value=UserBalance(
            daily_limit=15.0, daily_used=0.0, bonus_minutes=0.0, package_minutes=0.0
        )
    )

    subscription_service = AsyncMock()
    active_sub = MagicMock(tier_id=1, expires_at=datetime(2026, 11, 16))
    subscription_service.get_active_subscription = AsyncMock(return_value=active_sub)
    tier = SimpleNamespace(name="Basic", daily_limit_minutes=15.0)
    subscription_service.get_tier_by_id = AsyncMock(return_value=tier)
    subscription_service.get_queued_subscription_info = AsyncMock(return_value=None)

    calls: list[str] = []

    async def track_sub(*a, **kw):
        calls.append("sub")
        return active_sub

    async def track_bal(*a, **kw):
        calls.append("balance")
        return UserBalance(daily_limit=15.0, daily_used=0.0, bonus_minutes=0.0, package_minutes=0.0)

    subscription_service.get_active_subscription.side_effect = track_sub
    billing_service.get_user_balance.side_effect = track_bal

    cmds = _make_cmds(billing_service, subscription_service)
    text = await _run_balance_screen(cmds)

    assert calls.index("sub") < calls.index("balance")
    assert "Дневной лимит: 15 мин" in text
    assert "Подписка: Basic" in text


@pytest.mark.asyncio
async def test_balance_without_subscription_shows_default_limit():
    """Без подписки лимит берётся из биллинга (дефолт/conditions)."""
    billing_service = AsyncMock()
    billing_service.get_user_balance = AsyncMock(
        return_value=UserBalance(
            daily_limit=10.0, daily_used=0.0, bonus_minutes=0.0, package_minutes=0.0
        )
    )

    subscription_service = AsyncMock()
    subscription_service.get_active_subscription = AsyncMock(return_value=None)

    cmds = _make_cmds(billing_service, subscription_service)
    text = await _run_balance_screen(cmds)

    assert "Дневной лимит: 10 мин" in text
    assert "Подписка: нет" in text
    billing_service.get_user_balance.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_balance_single_get_active_subscription_call():
    """get_active_subscription вызывается один раз (не дублируется)."""
    billing_service = AsyncMock()
    billing_service.get_user_balance = AsyncMock(
        return_value=UserBalance(
            daily_limit=15.0, daily_used=0.0, bonus_minutes=0.0, package_minutes=0.0
        )
    )

    subscription_service = AsyncMock()
    subscription_service.get_active_subscription = AsyncMock(
        return_value=MagicMock(tier_id=1, expires_at=datetime(2026, 11, 16))
    )
    subscription_service.get_tier_by_id = AsyncMock(return_value=MagicMock(name="Basic"))
    subscription_service.get_queued_subscription_info = AsyncMock(return_value=None)

    cmds = _make_cmds(billing_service, subscription_service)
    await _run_balance_screen(cmds)

    subscription_service.get_active_subscription.assert_awaited_once()
