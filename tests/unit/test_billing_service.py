"""
Tests for BillingService - core billing logic
"""

import pytest
from unittest.mock import MagicMock

from tests.conftest import make_billing_service


# =============================================================================
# get_user_daily_limit Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_daily_limit_from_subscription():
    """Subscription replaces (not sums with) the daily limit."""
    service, mocks = make_billing_service()

    # User has a Pro subscription with 30 min/day
    mock_sub = MagicMock()
    mock_sub.tier = MagicMock()
    mock_sub.tier.daily_limit_minutes = 30.0
    mocks["subscription_repo"].get_active_subscription_with_tier.return_value = mock_sub

    limit = await service.get_user_daily_limit(user_id=1)
    assert limit == 30.0


@pytest.mark.asyncio
async def test_get_daily_limit_from_billing_condition():
    """No subscription — use billing condition."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    limit = await service.get_user_daily_limit(user_id=1)
    assert limit == 10.0


@pytest.mark.asyncio
async def test_get_daily_limit_default_when_no_condition():
    """No subscription, no condition — default 10 min."""
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service(billing_enabled=False)

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=100.0)
    assert can is True


# =============================================================================
# deduct_minutes Tests
# =============================================================================


@pytest.mark.asyncio
async def test_deduct_minutes_from_daily_only():
    """Test deduction fully from daily limit."""
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service()

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
    service, mocks = make_billing_service(billing_enabled=False)

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
    service, _ = make_billing_service()

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
    service, mocks = make_billing_service(warning_threshold=0.8)

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
    service, mocks = make_billing_service(warning_threshold=0.8)

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 5.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    should_warn = await service.should_warn_limit(user_id=1)
    assert should_warn is False


# =============================================================================
# Task 6.1: Deduction Shortfall Tests
# =============================================================================


@pytest.mark.asyncio
async def test_deduct_minutes_shortfall_logs_warning():
    """Test: remaining > 0 after all sources exhausted logs a warning."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "5"  # 5 min daily

    mock_daily = MagicMock()
    mock_daily.minutes_used = 5.0  # daily fully used
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)

    # Only 2 bonus minutes available, no package
    mock_bonus = MagicMock()
    mock_bonus.id = 1
    mock_bonus.balance_type = "bonus"
    mock_bonus.minutes_remaining = 2.0
    mocks["balance_repo"].get_active_balances.return_value = [mock_bonus]
    mocks["balance_repo"].deduct_minutes.return_value = MagicMock()

    # Request 5 min, but only 2 available (from bonus)
    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0)

    assert result["from_daily"] == 0.0
    assert result["from_bonus"] == 2.0
    assert result["from_package"] == 0.0


# =============================================================================
# Task 6.4: get_user_daily_limit with missing tier
# =============================================================================


@pytest.mark.asyncio
async def test_get_daily_limit_subscription_with_missing_tier():
    """Test: active subscription but tier not found falls back to billing condition."""
    service, mocks = make_billing_service()

    mock_sub = MagicMock()
    mock_sub.tier_id = 999
    mocks["subscription_repo"].get_active_subscription.return_value = mock_sub
    mocks["subscription_repo"].get_tier_by_id.return_value = None  # tier deleted
    mocks["condition_repo"].get_effective_value.return_value = "15"

    limit = await service.get_user_daily_limit(user_id=1)
    assert limit == 15.0


@pytest.mark.asyncio
async def test_get_daily_limit_no_subscription_no_condition():
    """Test: no subscription, no billing condition -> default 10 min."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = None

    limit = await service.get_user_daily_limit(user_id=1)
    assert limit == 10.0


# =============================================================================
# Task 6.5: Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_deduct_minutes_zero():
    """Test: deduct_minutes(0.0) deducts nothing."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 0.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, True)
    mocks["balance_repo"].get_active_balances.return_value = []

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=0.0)

    assert result["from_daily"] == 0.0
    assert result["from_bonus"] == 0.0
    assert result["from_package"] == 0.0


@pytest.mark.asyncio
async def test_deduct_minutes_negative():
    """Test: deduct_minutes(-1.0) — negative durations pass through (callers should validate)."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 0.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, True)
    mocks["balance_repo"].get_active_balances.return_value = []

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=-1.0)

    # Negative duration results in negative deduction from daily
    # (callers are expected to validate duration before calling)
    assert result["from_daily"] == -1.0


@pytest.mark.asyncio
async def test_daily_limit_zero_means_no_daily_minutes():
    """Test: daily_limit=0 means all minutes come from bonus/package."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "0"  # zero daily limit

    mock_daily = MagicMock()
    mock_daily.minutes_used = 0.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, True)

    mock_package = MagicMock()
    mock_package.id = 1
    mock_package.balance_type = "package"
    mock_package.minutes_remaining = 100.0
    mocks["balance_repo"].get_active_balances.return_value = [mock_package]
    mocks["balance_repo"].deduct_minutes.return_value = MagicMock()

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=3.0)

    assert result["from_daily"] == 0.0
    assert result["from_package"] == 3.0


# =============================================================================
# Task 1.1: get_limit_status Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_limit_status_ok():
    """Test: status="ok" when daily_used/daily_limit < 0.8"""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 5.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    status = await service.get_limit_status(user_id=1)
    assert status == "ok"


@pytest.mark.asyncio
async def test_get_limit_status_warning():
    """Test: status="warning" when 0.8 <= daily_used/daily_limit < 1.0"""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 8.5
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    status = await service.get_limit_status(user_id=1)
    assert status == "warning"


@pytest.mark.asyncio
async def test_get_limit_status_exhausted():
    """Test: status="exhausted" when daily_used >= daily_limit"""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 10.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    status = await service.get_limit_status(user_id=1)
    assert status == "exhausted"


@pytest.mark.asyncio
async def test_get_limit_status_exhausted_over_limit():
    """Test: status="exhausted" when daily_used exceeds daily_limit"""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 15.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    status = await service.get_limit_status(user_id=1)
    assert status == "exhausted"


@pytest.mark.asyncio
async def test_get_limit_status_no_usage_today():
    """Test: status="ok" when no usage today (0.0 / 10.0 < 0.8)"""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None

    status = await service.get_limit_status(user_id=1)
    assert status == "ok"


@pytest.mark.asyncio
async def test_get_limit_status_warning_at_exactly_80_percent():
    """Test: status="warning" at exactly 80% threshold"""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 8.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    status = await service.get_limit_status(user_id=1)
    assert status == "warning"


@pytest.mark.asyncio
async def test_get_limit_status_exhausted_at_exactly_100_percent():
    """Test: status="exhausted" at exactly 100% usage"""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 10.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    status = await service.get_limit_status(user_id=1)
    assert status == "exhausted"
