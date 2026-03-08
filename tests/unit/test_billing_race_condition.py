"""
Tests for Phase 4: Race condition и атомарность списания.

Task 4.1: Параллельные запросы одного пользователя не приводят к overspend.
Task 4.4: deduct_minutes возвращает shortfall как часть результата.
"""

import asyncio

import pytest
from unittest.mock import MagicMock

from tests.conftest import make_billing_service


# =============================================================================
# Task 4.1: Race condition — parallel deductions are serialized per user
# =============================================================================


@pytest.mark.asyncio
async def test_parallel_deductions_same_user_serialized():
    """Two parallel deduct_minutes calls for the same user must not overspend.

    Setup: user has 10.0 daily minutes, 0 used.
    Two concurrent requests each want 7.0 min.
    Without lock: both see 10.0 available → both deduct 7.0 → total 14.0 (overspend).
    With lock: first gets 7.0, second sees only 3.0 left → deducts 3.0.
    """
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    # Track actual minutes_used across calls
    daily_state = {"minutes_used": 0.0}

    mock_daily = MagicMock()
    mock_daily.minutes_used = 0.0

    async def mock_get_or_create(user_id, usage_date):
        mock_daily.minutes_used = daily_state["minutes_used"]
        return mock_daily, False

    async def mock_add_usage(
        daily_usage, minutes_used, from_daily=0.0, from_bonus=0.0, from_package=0.0
    ):
        daily_state["minutes_used"] += from_daily
        return daily_usage

    mocks["daily_usage_repo"].get_or_create.side_effect = mock_get_or_create
    mocks["daily_usage_repo"].add_usage.side_effect = mock_add_usage
    mocks["balance_repo"].get_active_balances.return_value = []

    # Run two deductions concurrently
    results = await asyncio.gather(
        service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=7.0),
        service.deduct_minutes(user_id=1, usage_id=101, duration_minutes=7.0),
    )

    total_from_daily = sum(r["from_daily"] for r in results)

    # With per-user lock, total daily deduction must not exceed daily limit (10.0)
    assert (
        total_from_daily <= 10.0
    ), f"Overspend detected: total_from_daily={total_from_daily} > daily_limit=10.0"


@pytest.mark.asyncio
async def test_parallel_deductions_different_users_independent():
    """Parallel deductions for different users should not block each other."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 0.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)
    mocks["balance_repo"].get_active_balances.return_value = []

    # Both should complete successfully and independently
    results = await asyncio.gather(
        service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0),
        service.deduct_minutes(user_id=2, usage_id=101, duration_minutes=5.0),
    )

    assert results[0]["from_daily"] == 5.0
    assert results[1]["from_daily"] == 5.0


# =============================================================================
# Task 4.4: deduct_minutes returns shortfall in result
# =============================================================================


@pytest.mark.asyncio
async def test_deduct_minutes_returns_shortfall():
    """deduct_minutes should return shortfall amount when minutes can't be fully covered."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "5"  # 5 min daily

    mock_daily = MagicMock()
    mock_daily.minutes_used = 5.0  # daily fully used
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)

    # Only 2 bonus minutes available
    mock_bonus = MagicMock()
    mock_bonus.id = 1
    mock_bonus.balance_type = "bonus"
    mock_bonus.minutes_remaining = 2.0
    mocks["balance_repo"].get_active_balances.return_value = [mock_bonus]
    mocks["balance_repo"].deduct_minutes.return_value = MagicMock()

    # Request 5 min but only 2 available
    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0)

    assert result["from_daily"] == 0.0
    assert result["from_bonus"] == 2.0
    assert result["from_package"] == 0.0
    assert result["shortfall"] == 3.0  # 5.0 - 2.0 = 3.0


@pytest.mark.asyncio
async def test_deduct_minutes_no_shortfall():
    """deduct_minutes should return shortfall=0.0 when fully covered."""
    service, mocks = make_billing_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mocks["condition_repo"].get_effective_value.return_value = "10"

    mock_daily = MagicMock()
    mock_daily.minutes_used = 0.0
    mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)
    mocks["balance_repo"].get_active_balances.return_value = []

    result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0)

    assert result["from_daily"] == 5.0
    assert result["shortfall"] == 0.0
