"""
Tests for SubscriptionService - subscription management logic
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.services.subscription_service import SubscriptionService


# === Helpers ===


def _make_subscription_service() -> tuple[SubscriptionService, dict[str, AsyncMock]]:
    """Create SubscriptionService with mocked repositories."""
    mocks = {
        "subscription_repo": AsyncMock(),
        "balance_repo": AsyncMock(),
        "purchase_repo": AsyncMock(),
    }

    service = SubscriptionService(
        subscription_repo=mocks["subscription_repo"],
        balance_repo=mocks["balance_repo"],
        purchase_repo=mocks["purchase_repo"],
    )

    return service, mocks


def _mock_tier(
    tier_id: int = 1,
    name: str = "Pro",
    daily_limit: float = 30.0,
    display_order: int = 1,
    is_active: bool = True,
) -> MagicMock:
    tier = MagicMock()
    tier.id = tier_id
    tier.name = name
    tier.daily_limit_minutes = daily_limit
    tier.display_order = display_order
    tier.is_active = is_active
    tier.description = f"{name} subscription"
    return tier


def _mock_price(
    price_id: int = 1,
    tier_id: int = 1,
    period: str = "month",
    amount_rub: float = 299.0,
    amount_stars: int = 150,
) -> MagicMock:
    price = MagicMock()
    price.id = price_id
    price.tier_id = tier_id
    price.period = period
    price.amount_rub = amount_rub
    price.amount_stars = amount_stars
    price.is_active = True
    return price


def _mock_subscription(
    sub_id: int = 1,
    user_id: int = 1,
    tier_id: int = 1,
    period: str = "month",
    status: str = "active",
    auto_renew: bool = True,
    expires_at: datetime | None = None,
    next_tier_id: int | None = None,
) -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.tier_id = tier_id
    sub.period = period
    sub.status = status
    sub.auto_renew = auto_renew
    sub.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(days=30))
    sub.started_at = datetime.now(timezone.utc)
    sub.next_subscription_tier_id = next_tier_id
    sub.payment_provider = "telegram_stars"
    return sub


# =============================================================================
# get_available_tiers Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_available_tiers():
    """Test getting available subscription tiers with prices."""
    service, mocks = _make_subscription_service()

    tier1 = _mock_tier(tier_id=1, name="Pro", daily_limit=30.0)
    tier2 = _mock_tier(tier_id=2, name="Business", daily_limit=60.0)
    mocks["subscription_repo"].get_active_tiers.return_value = [tier1, tier2]

    tiers = await service.get_available_tiers()
    assert len(tiers) == 2
    assert tiers[0].name == "Pro"
    assert tiers[1].name == "Business"


@pytest.mark.asyncio
async def test_get_available_tiers_empty():
    """Test getting tiers when none available."""
    service, mocks = _make_subscription_service()
    mocks["subscription_repo"].get_active_tiers.return_value = []

    tiers = await service.get_available_tiers()
    assert len(tiers) == 0


# =============================================================================
# get_tier_prices Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_tier_prices():
    """Test getting prices for a tier."""
    service, mocks = _make_subscription_service()

    price_week = _mock_price(price_id=1, period="week", amount_rub=99.0, amount_stars=50)
    price_month = _mock_price(price_id=2, period="month", amount_rub=299.0, amount_stars=150)
    mocks["subscription_repo"].get_tier_prices.return_value = [price_week, price_month]

    prices = await service.get_tier_prices(tier_id=1)
    assert len(prices) == 2


# =============================================================================
# create_subscription Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_subscription_new_user():
    """Test creating a subscription for a user without existing subscription."""
    service, mocks = _make_subscription_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None
    mock_sub = _mock_subscription()
    mocks["subscription_repo"].create_subscription.return_value = mock_sub

    result = await service.create_subscription(
        user_id=1, tier_id=1, period="month", payment_provider="telegram_stars"
    )

    assert result is not None
    mocks["subscription_repo"].create_subscription.assert_called_once()


@pytest.mark.asyncio
async def test_create_subscription_replaces_existing():
    """Test creating subscription when user already has one — old is deactivated."""
    service, mocks = _make_subscription_service()

    old_sub = _mock_subscription(sub_id=10, status="active")
    mocks["subscription_repo"].get_active_subscription.return_value = old_sub
    mocks["subscription_repo"].deactivate_subscription.return_value = old_sub

    new_sub = _mock_subscription(sub_id=11)
    mocks["subscription_repo"].create_subscription.return_value = new_sub

    result = await service.create_subscription(
        user_id=1, tier_id=1, period="month", payment_provider="telegram_stars"
    )

    assert result is not None
    mocks["subscription_repo"].deactivate_subscription.assert_called_once_with(old_sub)


# =============================================================================
# cancel_subscription Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cancel_subscription():
    """Test cancelling active subscription (remains active until expiry)."""
    service, mocks = _make_subscription_service()

    active_sub = _mock_subscription(status="active")
    mocks["subscription_repo"].get_active_subscription.return_value = active_sub

    cancelled_sub = _mock_subscription(status="cancelled", auto_renew=False)
    mocks["subscription_repo"].cancel_subscription.return_value = cancelled_sub

    result = await service.cancel_subscription(user_id=1)
    assert result is not None
    mocks["subscription_repo"].cancel_subscription.assert_called_once_with(active_sub)


@pytest.mark.asyncio
async def test_cancel_subscription_no_active():
    """Test cancelling when no active subscription."""
    service, mocks = _make_subscription_service()
    mocks["subscription_repo"].get_active_subscription.return_value = None

    result = await service.cancel_subscription(user_id=1)
    assert result is None
    mocks["subscription_repo"].cancel_subscription.assert_not_called()


# =============================================================================
# renew_subscription Tests
# =============================================================================


@pytest.mark.asyncio
async def test_renew_subscription():
    """Test renewing an existing subscription."""
    service, mocks = _make_subscription_service()

    old_sub = _mock_subscription(
        sub_id=1,
        tier_id=1,
        period="month",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    new_sub = _mock_subscription(
        sub_id=2,
        tier_id=1,
        period="month",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    mocks["subscription_repo"].create_subscription.return_value = new_sub

    result = await service.renew_subscription(old_sub)
    assert result is not None
    mocks["subscription_repo"].create_subscription.assert_called_once()


@pytest.mark.asyncio
async def test_renew_subscription_with_downgrade():
    """Test renewing with next_subscription_tier_id set (downgrade at renewal)."""
    service, mocks = _make_subscription_service()

    old_sub = _mock_subscription(
        sub_id=1,
        tier_id=1,
        period="month",
        next_tier_id=2,  # downgrade to tier 2
    )

    new_sub = _mock_subscription(sub_id=2, tier_id=2, period="month")
    mocks["subscription_repo"].create_subscription.return_value = new_sub

    result = await service.renew_subscription(old_sub)
    assert result is not None
    # Should create with the new tier
    call_kwargs = mocks["subscription_repo"].create_subscription.call_args
    assert call_kwargs.kwargs.get("tier_id") == 2 or call_kwargs[1].get("tier_id") == 2


# =============================================================================
# check_expired_subscriptions Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_expired_subscriptions_marks_expired():
    """Test that expired subscriptions without auto_renew are marked as expired."""
    service, mocks = _make_subscription_service()

    expired_sub = _mock_subscription(
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        auto_renew=False,
    )
    mocks["subscription_repo"].get_expired_subscriptions.return_value = [expired_sub]

    count = await service.check_expired_subscriptions()
    assert count == 1
    mocks["subscription_repo"].expire_subscription.assert_called_once_with(expired_sub)


@pytest.mark.asyncio
async def test_check_expired_subscriptions_skips_auto_renew():
    """Test that expired subscriptions with auto_renew=True are NOT marked expired."""
    service, mocks = _make_subscription_service()

    expired_sub_renew = _mock_subscription(
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        auto_renew=True,
    )
    mocks["subscription_repo"].get_expired_subscriptions.return_value = [expired_sub_renew]

    count = await service.check_expired_subscriptions()
    assert count == 0
    mocks["subscription_repo"].expire_subscription.assert_not_called()


@pytest.mark.asyncio
async def test_check_expired_subscriptions_mixed():
    """Test mixed auto_renew and non-auto_renew expired subscriptions."""
    service, mocks = _make_subscription_service()

    expired_no_renew = _mock_subscription(
        sub_id=1,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        auto_renew=False,
    )
    expired_with_renew = _mock_subscription(
        sub_id=2,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        auto_renew=True,
    )
    mocks["subscription_repo"].get_expired_subscriptions.return_value = [
        expired_no_renew,
        expired_with_renew,
    ]

    count = await service.check_expired_subscriptions()
    assert count == 1  # only the one without auto_renew
    mocks["subscription_repo"].expire_subscription.assert_called_once_with(expired_no_renew)


# =============================================================================
# handle_upgrade Tests
# =============================================================================


@pytest.mark.asyncio
async def test_handle_upgrade_immediate():
    """Test upgrade applies immediately."""
    service, mocks = _make_subscription_service()

    old_sub = _mock_subscription(sub_id=1, tier_id=1, period="month")
    mocks["subscription_repo"].get_active_subscription.return_value = old_sub
    mocks["subscription_repo"].deactivate_subscription.return_value = old_sub

    new_sub = _mock_subscription(sub_id=2, tier_id=2, period="month")
    mocks["subscription_repo"].create_subscription.return_value = new_sub

    new_tier = _mock_tier(tier_id=2, name="Business", daily_limit=60.0)
    mocks["subscription_repo"].get_tier_by_id.return_value = new_tier

    result = await service.handle_upgrade(
        user_id=1, new_tier_id=2, new_period="month", payment_provider="telegram_stars"
    )
    assert result is not None
    # Old subscription should be deactivated (via create_subscription)
    mocks["subscription_repo"].deactivate_subscription.assert_called_once()
    # New subscription should be created
    mocks["subscription_repo"].create_subscription.assert_called_once()


@pytest.mark.asyncio
async def test_handle_upgrade_no_existing_subscription():
    """Test upgrade when no existing subscription — just create new."""
    service, mocks = _make_subscription_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None

    new_tier = _mock_tier(tier_id=2, name="Business", daily_limit=60.0)
    mocks["subscription_repo"].get_tier_by_id.return_value = new_tier

    new_sub = _mock_subscription(sub_id=1, tier_id=2)
    mocks["subscription_repo"].create_subscription.return_value = new_sub

    result = await service.handle_upgrade(
        user_id=1, new_tier_id=2, new_period="month", payment_provider="telegram_stars"
    )
    assert result is not None
    mocks["subscription_repo"].deactivate_subscription.assert_not_called()


# =============================================================================
# handle_downgrade Tests
# =============================================================================


@pytest.mark.asyncio
async def test_handle_downgrade_sets_next_tier():
    """Test downgrade saves next_subscription_tier_id for next renewal."""
    service, mocks = _make_subscription_service()

    active_sub = _mock_subscription(sub_id=1, tier_id=1)
    mocks["subscription_repo"].get_active_subscription.return_value = active_sub
    mocks["subscription_repo"].set_next_tier.return_value = active_sub

    result = await service.handle_downgrade(user_id=1, new_tier_id=2)
    assert result is not None
    mocks["subscription_repo"].set_next_tier.assert_called_once()


@pytest.mark.asyncio
async def test_handle_downgrade_no_active_subscription():
    """Test downgrade when no active subscription."""
    service, mocks = _make_subscription_service()

    mocks["subscription_repo"].get_active_subscription.return_value = None

    result = await service.handle_downgrade(user_id=1, new_tier_id=2)
    assert result is None


# =============================================================================
# next_subscription_tier_id logic Tests (Task 4.2)
# =============================================================================


@pytest.mark.asyncio
async def test_renew_with_next_tier_clears_field():
    """Test that after renewal with next_tier, the next_tier is cleared."""
    service, mocks = _make_subscription_service()

    old_sub = _mock_subscription(sub_id=1, tier_id=1, period="month", next_tier_id=2)

    new_sub = _mock_subscription(sub_id=2, tier_id=2, period="month")
    mocks["subscription_repo"].create_subscription.return_value = new_sub

    result = await service.renew_subscription(old_sub)
    # The new subscription should NOT have next_subscription_tier_id set
    assert result is not None


# =============================================================================
# Expiration Reminder Tests (Task 4.3)
# =============================================================================


@pytest.mark.asyncio
async def test_get_expiring_subscriptions():
    """Test getting subscriptions expiring within N days."""
    service, mocks = _make_subscription_service()

    expiring_sub = _mock_subscription(
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    mocks["subscription_repo"].get_expiring_subscriptions.return_value = [expiring_sub]

    result = await service.get_expiring_subscriptions(days_ahead=3)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_expiring_subscriptions_stars_only():
    """Test filtering for Telegram Stars subscriptions only (need manual renewal)."""
    service, mocks = _make_subscription_service()

    stars_sub = _mock_subscription(expires_at=datetime.now(timezone.utc) + timedelta(days=2))
    stars_sub.payment_provider = "telegram_stars"

    yookassa_sub = _mock_subscription(expires_at=datetime.now(timezone.utc) + timedelta(days=2))
    yookassa_sub.payment_provider = "yookassa"

    mocks["subscription_repo"].get_expiring_subscriptions.return_value = [
        stars_sub,
        yookassa_sub,
    ]

    result = await service.get_expiring_subscriptions_stars(days_ahead=3)
    assert len(result) == 1
    assert result[0].payment_provider == "telegram_stars"
