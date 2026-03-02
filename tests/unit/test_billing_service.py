"""
Tests for BillingService - core billing logic
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.billing_service import BillingService


# === Helpers ===


def _make_billing_service(
    billing_enabled: bool = True,
    warning_threshold: float = 0.8,
) -> tuple[BillingService, dict[str, AsyncMock]]:
    """Create BillingService with mocked repositories."""
    mocks = {
        "condition_repo": AsyncMock(),
        "subscription_repo": AsyncMock(),
        "balance_repo": AsyncMock(),
        "daily_usage_repo": AsyncMock(),
        "deduction_log_repo": AsyncMock(),
    }

    service = BillingService(
        condition_repo=mocks["condition_repo"],
        subscription_repo=mocks["subscription_repo"],
        balance_repo=mocks["balance_repo"],
        daily_usage_repo=mocks["daily_usage_repo"],
        deduction_log_repo=mocks["deduction_log_repo"],
        billing_enabled=billing_enabled,
        warning_threshold=warning_threshold,
    )

    return service, mocks


# =============================================================================
# get_user_daily_limit Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_daily_limit_from_subscription():
    """Subscription replaces (not sums with) the daily limit."""
    service, mocks = _make_billing_service()

    # User has a Pro subscription with 30 min/day
    mock_sub = MagicMock()
    mock_sub.tier_id = 1
    mock_tier = MagicMock()
    mock_tier.daily_limit_minutes = 30.0
    mocks["subscription_repo"].get_active_subscription.return_value = mock_sub
    mocks["subscription_repo"].get_tier_by_id.return_value = mock_tier

    limit = await service.get_user_daily_limit(user_id=1)
    assert limit == 30.0


@pytest.mark.asyncio
async def test_get_daily_limit_from_billing_condition():
    """No subscription — use billing condition."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    limit = await service.get_user_daily_limit(user_id=1)
    assert limit == 10.0


@pytest.mark.asyncio
async def test_get_daily_limit_default_when_no_condition():
    """No subscription, no condition — default 10 min."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = None

    limit = await service.get_user_daily_limit(user_id=1)
    assert limit == 10.0


# =============================================================================
# get_user_balance Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_user_balance():
    """Test getting full user balance."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily_usage = MagicMock()
    mock_daily_usage.minutes_used = 3.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily_usage

    mocks["balance_repo"].get_total_minutes.side_effect = [20.0, 50.0]  # bonus, package

    balance = await service.get_user_balance(user_id=1)

    assert balance.daily_limit == 10.0
    assert balance.daily_used == 3.0
    assert balance.daily_remaining == 7.0
    assert balance.bonus_minutes == 20.0
    assert balance.package_minutes == 50.0
    assert balance.total_available == 77.0  # 7 + 20 + 50


@pytest.mark.asyncio
async def test_get_user_balance_no_usage_today():
    """Test balance when no usage today."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    balance = await service.get_user_balance(user_id=1)

    assert balance.daily_used == 0.0
    assert balance.daily_remaining == 10.0
    assert balance.total_available == 10.0


# =============================================================================
# check_can_transcribe Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_can_transcribe_enough_daily():
    """Test: enough daily minutes available."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=5.0)
    assert can is True
    assert reason is None


@pytest.mark.asyncio
async def test_check_can_transcribe_enough_with_bonus():
    """Test: daily exhausted but bonus available."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 10.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    mocks["balance_repo"].get_total_minutes.side_effect = [30.0, 0.0]  # bonus, package

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=5.0)
    assert can is True


@pytest.mark.asyncio
async def test_check_can_transcribe_not_enough():
    """Test: not enough minutes anywhere."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 10.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=5.0)
    assert can is False
    assert reason is not None


@pytest.mark.asyncio
async def test_check_can_transcribe_billing_disabled():
    """Test: billing disabled — always allow."""
    service, mocks = _make_billing_service(billing_enabled=False)

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=100.0)
    assert can is True


# =============================================================================
# deduct_minutes Tests
# =============================================================================


@pytest.mark.asyncio
async def test_deduct_minutes_from_daily_only():
    """Test deduction fully from daily limit."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 3.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)
    mocks["daily_usage_repo"].add_usage.return_value = mock_daily
    mocks["balance_repo"].get_active_balances.return_value = []

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0)

    assert result["from_daily"] == 5.0
    assert result["from_bonus"] == 0.0
    assert result["from_package"] == 0.0


@pytest.mark.asyncio
async def test_deduct_minutes_spread_across_sources():
    """Test deduction spread: daily → bonus → package."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    # 8 min used today, daily limit 10 → only 2 min left from daily
    mock_daily = MagicMock()
    mock_daily.minutes_used = 8.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)
    mocks["daily_usage_repo"].add_usage.return_value = mock_daily

    # Bonus: 1 min remaining, Package: 100 min remaining
    mock_bonus = MagicMock()
    mock_bonus.id = 1
    mock_bonus.balance_type = "bonus"
    mock_bonus.minutes_remaining = 1.0

    mock_package = MagicMock()
    mock_package.id = 2
    mock_package.balance_type = "package"
    mock_package.minutes_remaining = 100.0

    mocks["balance_repo"].get_active_balances.return_value = [mock_bonus, mock_package]
    mocks["balance_repo"].deduct_minutes.return_value = MagicMock()

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0)

    # 5 min needed: 2 from daily, 1 from bonus, 2 from package
    assert result["from_daily"] == 2.0
    assert result["from_bonus"] == 1.0
    assert result["from_package"] == 2.0


@pytest.mark.asyncio
async def test_deduct_minutes_billing_disabled():
    """Test: billing disabled — no deduction."""
    service, mocks = _make_billing_service(billing_enabled=False)

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0)

    assert result["from_daily"] == 0.0
    assert result["from_bonus"] == 0.0
    assert result["from_package"] == 0.0


# =============================================================================
# Rounding Tests
# =============================================================================


@pytest.mark.asyncio
async def test_round_to_tenth():
    """Test rounding to tenths of a minute."""
    service, _ = _make_billing_service()

    assert service.round_minutes(3.14159) == 3.2
    assert service.round_minutes(3.04) == 3.1
    assert service.round_minutes(0.0) == 0.0
    assert service.round_minutes(1.01) == 1.1
    assert service.round_minutes(1.99) == 2.0


# =============================================================================
# Warning Threshold Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_warning_threshold_exceeded():
    """Test warning when 80%+ of daily limit used."""
    service, mocks = _make_billing_service(warning_threshold=0.8)

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 8.5
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    should_warn = await service.should_warn_limit(user_id=1)
    assert should_warn is True


@pytest.mark.asyncio
async def test_check_warning_threshold_not_exceeded():
    """Test no warning when under threshold."""
    service, mocks = _make_billing_service(warning_threshold=0.8)

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 5.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    should_warn = await service.should_warn_limit(user_id=1)
    assert should_warn is False
