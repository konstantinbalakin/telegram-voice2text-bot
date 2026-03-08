"""
Tests for billing system database models
"""

import pytest
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.storage.models import (
    User,
    BillingCondition,
    SubscriptionTier,
    SubscriptionPrice,
    UserSubscription,
    MinutePackage,
    UserMinuteBalance,
    DailyUsage,
    Purchase,
    DeductionLog,
)


# === Helpers ===


def _make_user(telegram_id: int = 123456789, **kwargs) -> User:
    defaults = dict(
        telegram_id=telegram_id,
        username="testuser",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return User(**defaults)


async def _create_user(session, telegram_id: int = 123456789) -> User:
    user = _make_user(telegram_id=telegram_id)
    session.add(user)
    await session.flush()
    return user


async def _create_tier(session, name: str = "Pro", **kwargs) -> SubscriptionTier:
    defaults = dict(
        name=name,
        daily_limit_minutes=30.0,
        description="Pro subscription",
        display_order=1,
        is_active=True,
    )
    defaults.update(kwargs)
    tier = SubscriptionTier(**defaults)
    session.add(tier)
    await session.flush()
    return tier


# === BillingCondition Tests ===


@pytest.mark.asyncio
async def test_billing_condition_global(async_session):
    """Test creating a global billing condition (user_id=None)."""
    condition = BillingCondition(
        key="daily_free_minutes",
        value="10",
        user_id=None,
        valid_from=datetime.now(timezone.utc),
        valid_to=None,
    )
    async_session.add(condition)
    await async_session.commit()

    assert condition.id is not None
    assert condition.key == "daily_free_minutes"
    assert condition.value == "10"
    assert condition.user_id is None
    assert condition.valid_to is None


@pytest.mark.asyncio
async def test_billing_condition_individual(async_session):
    """Test creating an individual billing condition for a specific user."""
    user = await _create_user(async_session)

    condition = BillingCondition(
        key="daily_free_minutes",
        value="20",
        user_id=user.id,
        valid_from=datetime.now(timezone.utc),
        valid_to=None,
    )
    async_session.add(condition)
    await async_session.commit()

    assert condition.user_id == user.id
    assert condition.value == "20"


# === SubscriptionTier Tests ===


@pytest.mark.asyncio
async def test_subscription_tier_creation(async_session):
    """Test creating a subscription tier."""
    tier = SubscriptionTier(
        name="Pro",
        daily_limit_minutes=30.0,
        description="Pro plan with 30 min/day",
        display_order=1,
        is_active=True,
    )
    async_session.add(tier)
    await async_session.commit()

    assert tier.id is not None
    assert tier.name == "Pro"
    assert tier.daily_limit_minutes == 30.0
    assert tier.is_active is True


# === SubscriptionPrice Tests ===


@pytest.mark.asyncio
async def test_subscription_price_creation(async_session):
    """Test creating subscription prices for a tier."""
    tier = await _create_tier(async_session)

    price = SubscriptionPrice(
        tier_id=tier.id,
        period="month",
        amount_rub=29900,
        amount_stars=150,
        is_active=True,
    )
    async_session.add(price)
    await async_session.commit()

    assert price.id is not None
    assert price.tier_id == tier.id
    assert price.period == "month"
    assert price.amount_rub == 29900
    assert price.amount_stars == 150


@pytest.mark.asyncio
async def test_subscription_price_periods(async_session):
    """Test creating prices for all periods (week, month, year)."""
    tier = await _create_tier(async_session)

    periods = [
        ("week", 9900, 50),
        ("month", 29900, 150),
        ("year", 249900, 1200),
    ]
    for period, rub, stars in periods:
        price = SubscriptionPrice(
            tier_id=tier.id,
            period=period,
            amount_rub=rub,
            amount_stars=stars,
            is_active=True,
        )
        async_session.add(price)

    await async_session.commit()

    result = await async_session.execute(
        select(SubscriptionPrice).where(SubscriptionPrice.tier_id == tier.id)
    )
    prices = result.scalars().all()
    assert len(prices) == 3


# === UserSubscription Tests ===


@pytest.mark.asyncio
async def test_user_subscription_creation(async_session):
    """Test creating a user subscription."""
    user = await _create_user(async_session)
    tier = await _create_tier(async_session)

    subscription = UserSubscription(
        user_id=user.id,
        tier_id=tier.id,
        period="month",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        auto_renew=True,
        payment_provider="telegram_stars",
        status="active",
    )
    async_session.add(subscription)
    await async_session.commit()

    assert subscription.id is not None
    assert subscription.user_id == user.id
    assert subscription.tier_id == tier.id
    assert subscription.status == "active"
    assert subscription.auto_renew is True
    assert subscription.next_subscription_tier_id is None


@pytest.mark.asyncio
async def test_user_subscription_with_downgrade(async_session):
    """Test subscription with scheduled downgrade (next_subscription_tier_id)."""
    user = await _create_user(async_session)
    tier_pro = await _create_tier(async_session, name="Pro", daily_limit_minutes=30.0)
    tier_basic = await _create_tier(async_session, name="Basic", daily_limit_minutes=15.0)

    subscription = UserSubscription(
        user_id=user.id,
        tier_id=tier_pro.id,
        period="month",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        auto_renew=True,
        payment_provider="yookassa",
        next_subscription_tier_id=tier_basic.id,
        status="active",
    )
    async_session.add(subscription)
    await async_session.commit()

    assert subscription.next_subscription_tier_id == tier_basic.id


# === MinutePackage Tests ===


@pytest.mark.asyncio
async def test_minute_package_creation(async_session):
    """Test creating a minute package."""
    package = MinutePackage(
        name="50 минут",
        minutes=50.0,
        price_rub=14900,
        price_stars=75,
        display_order=1,
        is_active=True,
    )
    async_session.add(package)
    await async_session.commit()

    assert package.id is not None
    assert package.name == "50 минут"
    assert package.minutes == 50.0
    assert package.price_rub == 14900


# === UserMinuteBalance Tests ===


@pytest.mark.asyncio
async def test_user_minute_balance_bonus(async_session):
    """Test creating a bonus minute balance."""
    user = await _create_user(async_session)

    balance = UserMinuteBalance(
        user_id=user.id,
        balance_type="bonus",
        minutes_remaining=60.0,
        expires_at=None,
        source_description="Welcome bonus",
    )
    async_session.add(balance)
    await async_session.commit()

    assert balance.id is not None
    assert balance.balance_type == "bonus"
    assert balance.minutes_remaining == 60.0
    assert balance.expires_at is None


@pytest.mark.asyncio
async def test_user_minute_balance_package(async_session):
    """Test creating a package minute balance with expiration."""
    user = await _create_user(async_session)

    balance = UserMinuteBalance(
        user_id=user.id,
        balance_type="package",
        minutes_remaining=100.0,
        expires_at=None,
        source_description="100 minute package purchase",
    )
    async_session.add(balance)
    await async_session.commit()

    assert balance.balance_type == "package"
    assert balance.minutes_remaining == 100.0


# === DailyUsage Tests ===


@pytest.mark.asyncio
async def test_daily_usage_creation(async_session):
    """Test creating a daily usage record."""
    user = await _create_user(async_session)

    usage = DailyUsage(
        user_id=user.id,
        date=date.today(),
        minutes_used=5.5,
        minutes_from_daily=5.5,
        minutes_from_bonus=0.0,
        minutes_from_package=0.0,
    )
    async_session.add(usage)
    await async_session.commit()

    assert usage.id is not None
    assert usage.minutes_used == 5.5
    assert usage.minutes_from_daily == 5.5


@pytest.mark.asyncio
async def test_daily_usage_multiple_sources(async_session):
    """Test daily usage distributed across multiple sources."""
    user = await _create_user(async_session)

    usage = DailyUsage(
        user_id=user.id,
        date=date.today(),
        minutes_used=15.0,
        minutes_from_daily=10.0,
        minutes_from_bonus=3.0,
        minutes_from_package=2.0,
    )
    async_session.add(usage)
    await async_session.commit()

    assert usage.minutes_used == 15.0
    assert usage.minutes_from_daily + usage.minutes_from_bonus + usage.minutes_from_package == 15.0


# === Purchase Tests ===


@pytest.mark.asyncio
async def test_purchase_package(async_session):
    """Test creating a package purchase record."""
    user = await _create_user(async_session)

    purchase = Purchase(
        user_id=user.id,
        purchase_type="package",
        item_id=1,
        amount=14900,
        currency="RUB",
        payment_provider="telegram_stars",
        status="completed",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    async_session.add(purchase)
    await async_session.commit()

    assert purchase.id is not None
    assert purchase.purchase_type == "package"
    assert purchase.status == "completed"


@pytest.mark.asyncio
async def test_purchase_subscription(async_session):
    """Test creating a subscription purchase record."""
    user = await _create_user(async_session)

    purchase = Purchase(
        user_id=user.id,
        purchase_type="subscription",
        item_id=1,
        amount=29900,
        currency="RUB",
        payment_provider="yookassa",
        provider_transaction_id="yoo_tx_123",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    async_session.add(purchase)
    await async_session.commit()

    assert purchase.purchase_type == "subscription"
    assert purchase.provider_transaction_id == "yoo_tx_123"
    assert purchase.status == "pending"
    assert purchase.completed_at is None


# === DeductionLog Tests ===


@pytest.mark.asyncio
async def test_deduction_log_creation(async_session):
    """Test creating a deduction log entry."""
    user = await _create_user(async_session)

    log = DeductionLog(
        user_id=user.id,
        usage_id=1,
        source_type="daily",
        source_id=None,
        minutes_deducted=3.5,
        created_at=datetime.now(timezone.utc),
    )
    async_session.add(log)
    await async_session.commit()

    assert log.id is not None
    assert log.source_type == "daily"
    assert log.minutes_deducted == 3.5


@pytest.mark.asyncio
async def test_deduction_log_from_package(async_session):
    """Test deduction log from a package balance."""
    user = await _create_user(async_session)

    balance = UserMinuteBalance(
        user_id=user.id,
        balance_type="package",
        minutes_remaining=100.0,
        source_description="Package",
    )
    async_session.add(balance)
    await async_session.flush()

    log = DeductionLog(
        user_id=user.id,
        usage_id=1,
        source_type="package",
        source_id=balance.id,
        minutes_deducted=2.0,
        created_at=datetime.now(timezone.utc),
    )
    async_session.add(log)
    await async_session.commit()

    assert log.source_type == "package"
    assert log.source_id == balance.id


# === Relationship Tests ===


@pytest.mark.asyncio
async def test_tier_prices_relationship(async_session):
    """Test relationship between SubscriptionTier and SubscriptionPrice."""
    tier = await _create_tier(async_session)

    for period, rub, stars in [("week", 9900, 50), ("month", 29900, 150)]:
        price = SubscriptionPrice(
            tier_id=tier.id, period=period, amount_rub=rub, amount_stars=stars, is_active=True
        )
        async_session.add(price)

    await async_session.commit()

    result = await async_session.execute(
        select(SubscriptionTier)
        .where(SubscriptionTier.id == tier.id)
        .options(selectinload(SubscriptionTier.prices))
    )
    loaded_tier = result.scalar_one()
    assert len(loaded_tier.prices) == 2


@pytest.mark.asyncio
async def test_user_subscriptions_relationship(async_session):
    """Test relationship between User and UserSubscription."""
    user = await _create_user(async_session)
    tier = await _create_tier(async_session)

    sub = UserSubscription(
        user_id=user.id,
        tier_id=tier.id,
        period="month",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        auto_renew=True,
        payment_provider="telegram_stars",
        status="active",
    )
    async_session.add(sub)
    await async_session.commit()

    result = await async_session.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    subs = result.scalars().all()
    assert len(subs) == 1
    assert subs[0].tier_id == tier.id
