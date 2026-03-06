"""
Tests for database optimization Phase 1: constraints, PRAGMA, race conditions.
"""

import pytest
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import DailyUsage, Purchase, User
from src.storage.billing_repositories import DailyUsageRepository


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
            amount=100.0,
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
        amount=100.0,
        currency="RUB",
        payment_provider="test",
        status="pending",
    )
    async_session.add(p)

    with pytest.raises(IntegrityError):
        await async_session.flush()
