"""
Tests for billing integration into the transcription pipeline (Phase 6)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.billing_service import BillingService


# === Helpers ===


def _make_billing_service(
    billing_enabled: bool = True,
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
    )

    return service, mocks


# =============================================================================
# Task 6.1: Billing check before transcription in pipeline
# =============================================================================


@pytest.mark.asyncio
async def test_check_billing_before_transcription_allowed():
    """Test: billing check allows transcription when minutes available."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=5.0)
    assert can is True
    assert reason is None


@pytest.mark.asyncio
async def test_check_billing_before_transcription_blocked():
    """Test: billing check blocks transcription when no minutes."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 10.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=5.0)
    assert can is False
    assert "Недостаточно минут" in reason


@pytest.mark.asyncio
async def test_check_billing_disabled_always_allows():
    """Test: billing disabled always allows transcription."""
    service, _ = _make_billing_service(billing_enabled=False)

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=100.0)
    assert can is True


# =============================================================================
# Task 6.2: Sequential deduction after transcription
# =============================================================================


@pytest.mark.asyncio
async def test_deduct_after_transcription():
    """Test: deduction happens after successful transcription."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 0.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)
    mocks["daily_usage_repo"].add_usage.return_value = mock_daily
    mocks["balance_repo"].get_active_balances.return_value = []

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=3.5)

    assert result["from_daily"] == 3.5
    assert result["from_bonus"] == 0.0
    assert result["from_package"] == 0.0


# =============================================================================
# Task 6.3: Seamless transcription when enough minutes
# =============================================================================


@pytest.mark.asyncio
async def test_transcription_seamless_with_enough_minutes():
    """Test: transcription proceeds seamlessly when user has enough minutes."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = None
    mocks["balance_repo"].get_total_minutes.side_effect = [60.0, 100.0]

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=8.0)
    assert can is True


# =============================================================================
# Task 6.4: Block when not enough minutes
# =============================================================================


@pytest.mark.asyncio
async def test_transcription_blocked_with_purchase_info():
    """Test: transcription blocked message includes info about available balance."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 10.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=5.0)
    assert can is False
    assert "5.0" in reason  # duration mentioned
    assert "0.0" in reason  # available mentioned


# =============================================================================
# Task 6.5: Warning at 80%+ daily limit usage
# =============================================================================


@pytest.mark.asyncio
async def test_warning_at_80_percent():
    """Test: warning triggered when 80%+ of daily limit used."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 8.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    should_warn = await service.should_warn_limit(user_id=1)
    assert should_warn is True


@pytest.mark.asyncio
async def test_no_warning_below_threshold():
    """Test: no warning when below threshold."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 5.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    should_warn = await service.should_warn_limit(user_id=1)
    assert should_warn is False


@pytest.mark.asyncio
async def test_warning_after_deduction():
    """Test: warning check after deduction shows correct state."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    # After deduction: 9 of 10 min used
    mock_daily = MagicMock()
    mock_daily.minutes_used = 9.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily

    should_warn = await service.should_warn_limit(user_id=1)
    assert should_warn is True


# =============================================================================
# Task 6.6-6.9: Integration helpers (utility methods)
# =============================================================================


@pytest.mark.asyncio
async def test_get_purchase_buttons_text():
    """Test generating purchase suggestion text when minutes are insufficient."""
    service, mocks = _make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 10.0
    mocks["daily_usage_repo"].get_by_user_and_date.return_value = mock_daily
    mocks["balance_repo"].get_total_minutes.side_effect = [0.0, 0.0]

    balance = await service.get_user_balance(user_id=1)
    assert balance.total_available == 0.0
    assert balance.daily_remaining == 0.0
