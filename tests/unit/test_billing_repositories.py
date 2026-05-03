"""
Tests for billing system repositories
"""

import pytest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import (
    User,
    Usage,
    SubscriptionTier,
)
from src.storage.billing_repositories import (
    BillingConditionRepository,
    SubscriptionRepository,
    MinutePackageRepository,
    UserMinuteBalanceRepository,
    DailyUsageRepository,
    DeductionLogRepository,
    PurchaseRepository,
)


# === Helpers ===


async def _create_user(session: AsyncSession, telegram_id: int = 123456789) -> User:
    user = User(
        telegram_id=telegram_id,
        username="testuser",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()
    return user


async def _create_usage(session: AsyncSession, user_id: int) -> Usage:
    usage = Usage(
        user_id=user_id,
        voice_file_id="file_test",
        voice_duration_seconds=60,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(usage)
    await session.flush()
    return usage


async def _create_tier(
    session: AsyncSession, name: str = "Pro", daily_limit: float = 30.0
) -> SubscriptionTier:
    tier = SubscriptionTier(
        name=name,
        daily_limit_minutes=daily_limit,
        description=f"{name} subscription",
        display_order=1,
        is_active=True,
    )
    session.add(tier)
    await session.flush()
    return tier


# =============================================================================
# BillingConditionRepository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_billing_condition_create_global(async_session):
    """Test creating a global billing condition."""
    repo = BillingConditionRepository(async_session)
    condition = await repo.create(key="daily_free_minutes", value="10")

    assert condition.id is not None
    assert condition.key == "daily_free_minutes"
    assert condition.value == "10"
    assert condition.user_id is None


@pytest.mark.asyncio
async def test_billing_condition_create_individual(async_session):
    """Test creating an individual billing condition."""
    user = await _create_user(async_session)
    repo = BillingConditionRepository(async_session)
    condition = await repo.create(key="daily_free_minutes", value="20", user_id=user.id)

    assert condition.user_id == user.id
    assert condition.value == "20"


@pytest.mark.asyncio
async def test_billing_condition_get_effective_individual_priority(async_session):
    """Test that individual condition overrides global."""
    user = await _create_user(async_session)
    repo = BillingConditionRepository(async_session)

    # Create global condition
    await repo.create(key="daily_free_minutes", value="10")
    # Create individual condition
    await repo.create(key="daily_free_minutes", value="20", user_id=user.id)

    value = await repo.get_effective_value(key="daily_free_minutes", user_id=user.id)
    assert value == "20"


@pytest.mark.asyncio
async def test_billing_condition_get_effective_global_fallback(async_session):
    """Test global condition is used when no individual exists."""
    user = await _create_user(async_session)
    repo = BillingConditionRepository(async_session)

    await repo.create(key="daily_free_minutes", value="10")

    value = await repo.get_effective_value(key="daily_free_minutes", user_id=user.id)
    assert value == "10"


@pytest.mark.asyncio
async def test_billing_condition_get_effective_none(async_session):
    """Test None returned when no condition exists."""
    repo = BillingConditionRepository(async_session)
    value = await repo.get_effective_value(key="nonexistent", user_id=1)
    assert value is None


@pytest.mark.asyncio
async def test_billing_condition_valid_from_to_filter(async_session):
    """Test that expired conditions are excluded."""
    repo = BillingConditionRepository(async_session)

    # Create expired condition
    await repo.create(
        key="daily_free_minutes",
        value="5",
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2025, 12, 31, tzinfo=timezone.utc),
    )
    # Create current condition
    await repo.create(
        key="daily_free_minutes",
        value="10",
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
    )

    value = await repo.get_effective_value(key="daily_free_minutes")
    assert value == "10"


# =============================================================================
# SubscriptionRepository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_subscription_create_tier(async_session):
    """Test creating a subscription tier."""
    repo = SubscriptionRepository(async_session)
    tier = await repo.create_tier(name="Pro", daily_limit_minutes=30.0, description="Pro plan")

    assert tier.id is not None
    assert tier.name == "Pro"
    assert tier.daily_limit_minutes == 30.0


@pytest.mark.asyncio
async def test_subscription_get_active_tiers(async_session):
    """Test getting active tiers sorted by display_order."""
    repo = SubscriptionRepository(async_session)
    await repo.create_tier(name="Pro", daily_limit_minutes=30.0, display_order=1)
    await repo.create_tier(name="Basic", daily_limit_minutes=15.0, display_order=2)
    await repo.create_tier(
        name="Archived", daily_limit_minutes=5.0, display_order=3, is_active=False
    )

    tiers = await repo.get_active_tiers()
    assert len(tiers) == 2
    assert tiers[0].name == "Pro"
    assert tiers[1].name == "Basic"


@pytest.mark.asyncio
async def test_subscription_create_price(async_session):
    """Test creating a subscription price."""
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    price = await repo.create_price(
        tier_id=tier.id, period="month", amount_rub=29900, amount_stars=150
    )

    assert price.id is not None
    assert price.tier_id == tier.id
    assert price.period == "month"


@pytest.mark.asyncio
async def test_subscription_get_tier_prices(async_session):
    """Test getting prices for a tier."""
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)
    await repo.create_price(tier_id=tier.id, period="week", amount_rub=9900, amount_stars=50)
    await repo.create_price(tier_id=tier.id, period="month", amount_rub=29900, amount_stars=150)

    prices = await repo.get_tier_prices(tier_id=tier.id)
    assert len(prices) == 2


@pytest.mark.asyncio
async def test_subscription_create_user_subscription(async_session):
    """Test creating a user subscription."""
    user = await _create_user(async_session)
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    sub = await repo.create_subscription(
        user_id=user.id,
        tier_id=tier.id,
        period="month",
        payment_provider="telegram_stars",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    assert sub.id is not None
    assert sub.status == "active"
    assert sub.auto_renew is False


@pytest.mark.asyncio
async def test_subscription_get_active_subscription(async_session):
    """Test getting active subscription for a user."""
    user = await _create_user(async_session)
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    await repo.create_subscription(
        user_id=user.id,
        tier_id=tier.id,
        period="month",
        payment_provider="telegram_stars",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    active = await repo.get_active_subscription(user_id=user.id)
    assert active is not None
    assert active.tier_id == tier.id
    assert active.status == "active"


@pytest.mark.asyncio
async def test_subscription_no_active_subscription(async_session):
    """Test None returned when no active subscription."""
    user = await _create_user(async_session)
    repo = SubscriptionRepository(async_session)

    active = await repo.get_active_subscription(user_id=user.id)
    assert active is None


@pytest.mark.asyncio
async def test_subscription_cancel(async_session):
    """Test cancelling a subscription."""
    user = await _create_user(async_session)
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    sub = await repo.create_subscription(
        user_id=user.id,
        tier_id=tier.id,
        period="month",
        payment_provider="telegram_stars",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    cancelled = await repo.cancel_subscription(sub)
    assert cancelled.status == "active"  # Remains active until expiry
    assert cancelled.auto_renew is False


# =============================================================================
# MinutePackageRepository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_minute_package_create(async_session):
    """Test creating a minute package."""
    repo = MinutePackageRepository(async_session)
    package = await repo.create(name="50 минут", minutes=50.0, price_rub=14900, price_stars=75)

    assert package.id is not None
    assert package.name == "50 минут"
    assert package.minutes == 50.0


@pytest.mark.asyncio
async def test_minute_package_get_active(async_session):
    """Test getting active packages sorted by display_order."""
    repo = MinutePackageRepository(async_session)
    await repo.create(name="50 мин", minutes=50.0, price_rub=14900, price_stars=75, display_order=1)
    await repo.create(
        name="100 мин", minutes=100.0, price_rub=24900, price_stars=125, display_order=2
    )
    await repo.create(
        name="Archived", minutes=10.0, price_rub=4900, price_stars=25, is_active=False
    )

    packages = await repo.get_active_packages()
    assert len(packages) == 2
    assert packages[0].name == "50 мин"


@pytest.mark.asyncio
async def test_minute_package_get_by_id(async_session):
    """Test getting a package by ID."""
    repo = MinutePackageRepository(async_session)
    package = await repo.create(name="50 мин", minutes=50.0, price_rub=14900, price_stars=75)

    found = await repo.get_by_id(package.id)
    assert found is not None
    assert found.name == "50 мин"


# =============================================================================
# UserMinuteBalanceRepository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_balance_create(async_session):
    """Test creating a minute balance."""
    user = await _create_user(async_session)
    repo = UserMinuteBalanceRepository(async_session)

    balance = await repo.create(
        user_id=user.id,
        balance_type="bonus",
        minutes_remaining=60.0,
        source_description="Welcome bonus",
    )

    assert balance.id is not None
    assert balance.minutes_remaining == 60.0


@pytest.mark.asyncio
async def test_balance_get_user_balances(async_session):
    """Test getting all active balances for a user."""
    user = await _create_user(async_session)
    repo = UserMinuteBalanceRepository(async_session)

    await repo.create(
        user_id=user.id, balance_type="bonus", minutes_remaining=60.0, source_description="Bonus"
    )
    await repo.create(
        user_id=user.id,
        balance_type="package",
        minutes_remaining=100.0,
        source_description="Package",
    )
    # Zero balance should be excluded
    await repo.create(
        user_id=user.id, balance_type="bonus", minutes_remaining=0.0, source_description="Empty"
    )

    balances = await repo.get_active_balances(user_id=user.id)
    assert len(balances) == 2


@pytest.mark.asyncio
async def test_balance_get_total_by_type(async_session):
    """Test getting total balance by type."""
    user = await _create_user(async_session)
    repo = UserMinuteBalanceRepository(async_session)

    await repo.create(
        user_id=user.id, balance_type="bonus", minutes_remaining=30.0, source_description="B1"
    )
    await repo.create(
        user_id=user.id, balance_type="bonus", minutes_remaining=20.0, source_description="B2"
    )
    await repo.create(
        user_id=user.id, balance_type="package", minutes_remaining=100.0, source_description="P1"
    )

    bonus_total = await repo.get_total_minutes(user_id=user.id, balance_type="bonus")
    assert bonus_total == 50.0

    package_total = await repo.get_total_minutes(user_id=user.id, balance_type="package")
    assert package_total == 100.0


@pytest.mark.asyncio
async def test_balance_deduct(async_session):
    """Test deducting minutes from a balance."""
    user = await _create_user(async_session)
    repo = UserMinuteBalanceRepository(async_session)

    balance = await repo.create(
        user_id=user.id, balance_type="bonus", minutes_remaining=60.0, source_description="Bonus"
    )

    updated = await repo.deduct_minutes(balance_id=balance.id, minutes=10.0)
    assert updated.minutes_remaining == 50.0


# =============================================================================
# DailyUsageRepository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_daily_usage_get_or_create(async_session):
    """Test get_or_create for daily usage."""
    user = await _create_user(async_session)
    repo = DailyUsageRepository(async_session)

    usage, created = await repo.get_or_create(user_id=user.id, usage_date=date.today())
    assert created is True
    assert usage.minutes_used == 0.0

    usage2, created2 = await repo.get_or_create(user_id=user.id, usage_date=date.today())
    assert created2 is False
    assert usage2.id == usage.id


@pytest.mark.asyncio
async def test_daily_usage_add_minutes(async_session):
    """Test adding minutes to daily usage."""
    user = await _create_user(async_session)
    repo = DailyUsageRepository(async_session)

    usage, _ = await repo.get_or_create(user_id=user.id, usage_date=date.today())
    updated = await repo.add_usage(
        daily_usage=usage,
        minutes_used=5.5,
        from_daily=5.0,
        from_bonus=0.5,
        from_package=0.0,
    )

    assert updated.minutes_used == 5.5
    assert updated.minutes_from_daily == 5.0
    assert updated.minutes_from_bonus == 0.5


# =============================================================================
# DeductionLogRepository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_deduction_log_create(async_session):
    """Test creating a deduction log entry."""
    user = await _create_user(async_session)
    usage = await _create_usage(async_session, user.id)
    repo = DeductionLogRepository(async_session)

    log = await repo.create(
        user_id=user.id,
        usage_id=usage.id,
        source_type="daily",
        minutes_deducted=3.5,
    )

    assert log.id is not None
    assert log.source_type == "daily"
    assert log.minutes_deducted == 3.5


@pytest.mark.asyncio
async def test_deduction_log_get_by_usage(async_session):
    """Test getting deduction logs for a usage record."""
    user = await _create_user(async_session)
    usage = await _create_usage(async_session, user.id)
    repo = DeductionLogRepository(async_session)

    await repo.create(user_id=user.id, usage_id=usage.id, source_type="daily", minutes_deducted=5.0)
    await repo.create(
        user_id=user.id, usage_id=usage.id, source_type="bonus", minutes_deducted=2.0, source_id=1
    )

    logs = await repo.get_by_usage_id(usage_id=usage.id)
    assert len(logs) == 2


# =============================================================================
# PurchaseRepository Tests
# =============================================================================


@pytest.mark.asyncio
async def test_purchase_create(async_session):
    """Test creating a purchase record."""
    user = await _create_user(async_session)
    repo = PurchaseRepository(async_session)

    purchase = await repo.create(
        user_id=user.id,
        purchase_type="package",
        item_id=1,
        amount=14900,
        currency="RUB",
        payment_provider="telegram_stars",
    )

    assert purchase.id is not None
    assert purchase.status == "pending"


@pytest.mark.asyncio
async def test_purchase_mark_completed(async_session):
    """Test marking a purchase as completed."""
    user = await _create_user(async_session)
    repo = PurchaseRepository(async_session)

    purchase = await repo.create(
        user_id=user.id,
        purchase_type="package",
        item_id=1,
        amount=14900,
        currency="RUB",
        payment_provider="telegram_stars",
    )

    completed = await repo.mark_completed(purchase)
    assert completed.status == "completed"
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_purchase_get_by_user(async_session):
    """Test getting purchases for a user."""
    user = await _create_user(async_session)
    repo = PurchaseRepository(async_session)

    await repo.create(
        user_id=user.id,
        purchase_type="package",
        item_id=1,
        amount=14900,
        currency="RUB",
        payment_provider="telegram_stars",
    )
    await repo.create(
        user_id=user.id,
        purchase_type="subscription",
        item_id=2,
        amount=29900,
        currency="RUB",
        payment_provider="yookassa",
    )

    purchases = await repo.get_by_user_id(user_id=user.id)
    assert len(purchases) == 2
