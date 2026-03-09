"""
Tests for Welcome Bonus and Grace Period functionality
"""

import pytest
from unittest.mock import MagicMock

from tests.conftest import make_billing_service


# =============================================================================
# Welcome Bonus Tests (Task 5.1)
# =============================================================================


@pytest.mark.asyncio
async def test_grant_welcome_bonus():
    """Test granting welcome bonus to new user."""
    service, mocks = make_billing_service()

    mocks["condition_repo"].get_effective_value.side_effect = [
        "60",  # welcome_bonus_minutes
        None,  # welcome_bonus_days (null = no expiry)
    ]

    mock_balance = MagicMock()
    mock_balance.id = 1
    mock_balance.minutes_remaining = 60.0
    mocks["balance_repo"].create.return_value = mock_balance

    # Check no existing bonus
    mocks["balance_repo"].has_welcome_bonus.return_value = False

    result = await service.grant_welcome_bonus(user_id=1)
    assert result is not None
    assert result.minutes_remaining == 60.0
    mocks["balance_repo"].create.assert_called_once()


@pytest.mark.asyncio
async def test_grant_welcome_bonus_already_granted():
    """Test that welcome bonus is not granted twice."""
    service, mocks = make_billing_service()

    mocks["balance_repo"].has_welcome_bonus.return_value = True

    result = await service.grant_welcome_bonus(user_id=1)
    assert result is None
    mocks["balance_repo"].create.assert_not_called()


@pytest.mark.asyncio
async def test_grant_welcome_bonus_billing_disabled():
    """Test that bonus is not granted when billing is disabled."""
    service, mocks = make_billing_service(billing_enabled=False)

    result = await service.grant_welcome_bonus(user_id=1)
    assert result is None
    mocks["balance_repo"].create.assert_not_called()


# =============================================================================
# Configurable Bonus Expiry Tests (Task 5.2)
# =============================================================================


@pytest.mark.asyncio
async def test_welcome_bonus_with_expiry_days():
    """Test welcome bonus with 7-day expiry."""
    service, mocks = make_billing_service()

    mocks["condition_repo"].get_effective_value.side_effect = [
        "60",  # welcome_bonus_minutes
        "7",  # welcome_bonus_days
    ]
    mocks["balance_repo"].has_welcome_bonus.return_value = False

    mock_balance = MagicMock()
    mock_balance.id = 1
    mock_balance.minutes_remaining = 60.0
    mocks["balance_repo"].create.return_value = mock_balance

    result = await service.grant_welcome_bonus(user_id=1)
    assert result is not None

    # Verify expires_at was passed
    call_kwargs = mocks["balance_repo"].create.call_args.kwargs
    assert call_kwargs["expires_at"] is not None


@pytest.mark.asyncio
async def test_welcome_bonus_no_expiry():
    """Test welcome bonus with no expiry (perpetual)."""
    service, mocks = make_billing_service()

    mocks["condition_repo"].get_effective_value.side_effect = [
        "60",  # welcome_bonus_minutes
        None,  # welcome_bonus_days (null = no expiry)
    ]
    mocks["balance_repo"].has_welcome_bonus.return_value = False

    mock_balance = MagicMock()
    mock_balance.id = 1
    mock_balance.minutes_remaining = 60.0
    mocks["balance_repo"].create.return_value = mock_balance

    result = await service.grant_welcome_bonus(user_id=1)
    assert result is not None

    # Verify expires_at is None
    call_kwargs = mocks["balance_repo"].create.call_args.kwargs
    assert call_kwargs["expires_at"] is None


@pytest.mark.asyncio
async def test_welcome_bonus_custom_minutes():
    """Test welcome bonus with custom amount from billing condition."""
    service, mocks = make_billing_service()

    mocks["condition_repo"].get_effective_value.side_effect = [
        "30",  # custom welcome_bonus_minutes
        None,
    ]
    mocks["balance_repo"].has_welcome_bonus.return_value = False

    mock_balance = MagicMock()
    mock_balance.id = 1
    mock_balance.minutes_remaining = 30.0
    mocks["balance_repo"].create.return_value = mock_balance

    result = await service.grant_welcome_bonus(user_id=1)
    assert result is not None

    call_kwargs = mocks["balance_repo"].create.call_args.kwargs
    assert call_kwargs["minutes_remaining"] == 30.0


# =============================================================================
# Grace Period Tests (Task 5.3)
# =============================================================================


@pytest.mark.asyncio
async def test_grant_grace_period():
    """Test granting grace period (60 perpetual minutes) to existing user."""
    service, mocks = make_billing_service()

    mock_balance = MagicMock()
    mock_balance.id = 1
    mock_balance.minutes_remaining = 60.0
    mocks["balance_repo"].create.return_value = mock_balance

    result = await service.grant_grace_period(user_id=1, minutes=60.0)
    assert result is not None
    assert result.minutes_remaining == 60.0

    call_kwargs = mocks["balance_repo"].create.call_args.kwargs
    assert call_kwargs["balance_type"] == "bonus"
    assert call_kwargs["expires_at"] is None
    assert call_kwargs["minutes_remaining"] == 60.0


@pytest.mark.asyncio
async def test_grant_grace_period_custom_minutes():
    """Test granting grace period with custom minutes."""
    service, mocks = make_billing_service()

    mock_balance = MagicMock()
    mock_balance.id = 1
    mock_balance.minutes_remaining = 120.0
    mocks["balance_repo"].create.return_value = mock_balance

    result = await service.grant_grace_period(user_id=1, minutes=120.0)
    assert result is not None

    call_kwargs = mocks["balance_repo"].create.call_args.kwargs
    assert call_kwargs["minutes_remaining"] == 120.0
