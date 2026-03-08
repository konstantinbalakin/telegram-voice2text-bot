"""
Tests for database optimization: constraints, PRAGMA, price versioning.
"""

import pytest
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import DailyUsage, Purchase, SubscriptionTier, User
from src.storage.billing_repositories import (
    DailyUsageRepository,
    SubscriptionRepository,
    MinutePackageRepository,
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


# =============================================================================
# UNIQUE constraint on daily_usage(user_id, date)
# =============================================================================


@pytest.mark.asyncio
async def test_daily_usage_unique_constraint_prevents_duplicate(
    async_session: AsyncSession,
) -> None:
    """Inserting duplicate (user_id, date) raises IntegrityError."""
    user = await _create_user(async_session)
    today = date.today()

    usage1 = DailyUsage(user_id=user.id, date=today, minutes_used=0.0)
    async_session.add(usage1)
    await async_session.flush()

    usage2 = DailyUsage(user_id=user.id, date=today, minutes_used=1.0)
    async_session.add(usage2)

    with pytest.raises(IntegrityError):
        await async_session.flush()


# =============================================================================
# Helpers for Phase 3
# =============================================================================


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
# Price versioning: subscription prices
# =============================================================================


@pytest.mark.asyncio
async def test_effective_prices_current_price(async_session: AsyncSession) -> None:
    """Current valid price is returned."""
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    await repo.create_price(tier_id=tier.id, period="month", amount_rub=29900, amount_stars=150)

    prices = await repo.get_effective_prices(tier_id=tier.id)
    assert len(prices) == 1
    assert prices[0].amount_rub == 29900


@pytest.mark.asyncio
async def test_effective_prices_expired_excluded(async_session: AsyncSession) -> None:
    """Expired price (valid_to in past) is excluded."""
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    from src.storage.models import SubscriptionPrice

    expired_price = SubscriptionPrice(
        tier_id=tier.id,
        period="month",
        amount_rub=19900,
        amount_stars=100,
        is_active=True,
        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2025, 12, 31, tzinfo=timezone.utc),
    )
    async_session.add(expired_price)
    await async_session.flush()

    prices = await repo.get_effective_prices(tier_id=tier.id)
    assert len(prices) == 0


@pytest.mark.asyncio
async def test_effective_prices_future_excluded(async_session: AsyncSession) -> None:
    """Future price (valid_from in future) is excluded."""
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    from src.storage.models import SubscriptionPrice

    future_price = SubscriptionPrice(
        tier_id=tier.id,
        period="month",
        amount_rub=39900,
        amount_stars=200,
        is_active=True,
        valid_from=datetime(2027, 1, 1, tzinfo=timezone.utc),
        valid_to=None,
    )
    async_session.add(future_price)
    await async_session.flush()

    prices = await repo.get_effective_prices(tier_id=tier.id)
    assert len(prices) == 0


@pytest.mark.asyncio
async def test_effective_prices_individual_overrides_global(async_session: AsyncSession) -> None:
    """Individual price (user_id) takes priority over global."""
    user = await _create_user(async_session)
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    from src.storage.models import SubscriptionPrice

    # Global price
    global_price = SubscriptionPrice(
        tier_id=tier.id,
        period="month",
        amount_rub=29900,
        amount_stars=150,
        is_active=True,
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user_id=None,
    )
    # Individual price for user
    individual_price = SubscriptionPrice(
        tier_id=tier.id,
        period="month",
        amount_rub=19900,
        amount_stars=100,
        is_active=True,
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user_id=user.id,
    )
    async_session.add_all([global_price, individual_price])
    await async_session.flush()

    # With user_id → individual price
    prices = await repo.get_effective_prices(tier_id=tier.id, user_id=user.id)
    assert len(prices) == 1
    assert prices[0].amount_rub == 19900

    # Without user_id → global price
    prices_global = await repo.get_effective_prices(tier_id=tier.id)
    assert len(prices_global) == 1
    assert prices_global[0].amount_rub == 29900


@pytest.mark.asyncio
async def test_effective_prices_fallback_to_global(async_session: AsyncSession) -> None:
    """When no individual price, global price is returned."""
    user = await _create_user(async_session)
    tier = await _create_tier(async_session)
    repo = SubscriptionRepository(async_session)

    await repo.create_price(tier_id=tier.id, period="month", amount_rub=29900, amount_stars=150)

    prices = await repo.get_effective_prices(tier_id=tier.id, user_id=user.id)
    assert len(prices) == 1
    assert prices[0].amount_rub == 29900


# =============================================================================
# Price versioning: minute packages
# =============================================================================


@pytest.mark.asyncio
async def test_effective_packages_current(async_session: AsyncSession) -> None:
    """Current valid packages are returned."""
    repo = MinutePackageRepository(async_session)
    await repo.create(name="50 мин", minutes=50.0, price_rub=14900, price_stars=75)

    packages = await repo.get_effective_packages()
    assert len(packages) == 1


@pytest.mark.asyncio
async def test_effective_packages_individual_overrides_global(async_session: AsyncSession) -> None:
    """Individual package (user_id) overrides global."""
    user = await _create_user(async_session)
    repo = MinutePackageRepository(async_session)

    from src.storage.models import MinutePackage

    global_pkg = MinutePackage(
        name="50 мин",
        minutes=50.0,
        price_rub=14900,
        price_stars=75,
        is_active=True,
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user_id=None,
    )
    individual_pkg = MinutePackage(
        name="50 мин VIP",
        minutes=50.0,
        price_rub=9900,
        price_stars=50,
        is_active=True,
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user_id=user.id,
    )
    async_session.add_all([global_pkg, individual_pkg])
    await async_session.flush()

    # With user_id → individual
    packages = await repo.get_effective_packages(user_id=user.id)
    assert len(packages) == 1
    assert packages[0].price_rub == 9900

    # Without user_id → global
    packages_global = await repo.get_effective_packages()
    assert len(packages_global) == 1
    assert packages_global[0].price_rub == 14900


@pytest.mark.asyncio
async def test_daily_usage_unique_allows_different_dates(async_session: AsyncSession) -> None:
    """Different dates for same user should succeed."""
    user = await _create_user(async_session)

    usage1 = DailyUsage(user_id=user.id, date=date(2026, 1, 1), minutes_used=0.0)
    usage2 = DailyUsage(user_id=user.id, date=date(2026, 1, 2), minutes_used=0.0)
    async_session.add_all([usage1, usage2])
    await async_session.flush()

    assert usage1.id is not None
    assert usage2.id is not None


# =============================================================================
# get_or_create race condition handling
# =============================================================================


@pytest.mark.asyncio
async def test_get_or_create_returns_existing(async_session: AsyncSession) -> None:
    """get_or_create returns existing record without creating duplicate."""
    user = await _create_user(async_session)
    repo = DailyUsageRepository(async_session)

    usage1, created1 = await repo.get_or_create(user.id, date.today())
    assert created1 is True

    usage2, created2 = await repo.get_or_create(user.id, date.today())
    assert created2 is False
    assert usage2.id == usage1.id


# =============================================================================
# CHECK constraint on purchases.purchase_type
# =============================================================================


@pytest.mark.asyncio
async def test_purchase_check_constraint_valid_types(async_session: AsyncSession) -> None:
    """Valid purchase_type values should succeed."""
    user = await _create_user(async_session)

    for ptype in ("package", "subscription"):
        p = Purchase(
            user_id=user.id,
            purchase_type=ptype,
            item_id=1,
            amount=10000,
            currency="RUB",
            payment_provider="test",
            status="pending",
        )
        async_session.add(p)
    await async_session.flush()


@pytest.mark.asyncio
async def test_purchase_check_constraint_invalid_type(async_session: AsyncSession) -> None:
    """Invalid purchase_type raises IntegrityError."""
    user = await _create_user(async_session)

    p = Purchase(
        user_id=user.id,
        purchase_type="invalid_type",
        item_id=1,
        amount=10000,
        currency="RUB",
        payment_provider="test",
        status="pending",
    )
    async_session.add(p)

    with pytest.raises(IntegrityError):
        await async_session.flush()
