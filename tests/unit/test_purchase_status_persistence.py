"""
Regression test for issue #121 (secondary bug): Purchase status must be
persisted as completed with provider_transaction_id.

The old implementation mutated a Purchase instance loaded in a *previous*
(detached) session — mark_completed() on a new session's flush never saw it,
so completed purchases stayed `pending` forever and idempotency by
transaction id never worked.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.payments.base import PaymentType
from src.services.payments.payment_service import PaymentService
from src.storage.billing_repositories import (
    PurchaseRepository,
    UserMinuteBalanceRepository,
)
from src.storage.models import Purchase


@pytest_asyncio.fixture
async def session_factory(async_engine):
    """Session factory that commits on exit — mirrors prod src.storage.database.get_session."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return factory


async def _seed_user_and_package(session_factory) -> tuple[int, int]:
    """Create user (via User table) and a minute package; return (user_id, package_id)."""
    from src.storage.models import MinutePackage, User
    from datetime import datetime, timezone

    async with session_factory() as session:
        user = User(
            telegram_id=123456,
            username="testuser",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(user)
        pkg = MinutePackage(
            name="500 минут",
            minutes=500.0,
            price_rub=40000,
            price_stars=192,
            display_order=1,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(pkg)
        await session.commit()
        return user.id, pkg.id


@pytest.mark.asyncio
async def test_handle_successful_payment_persists_completed_status(session_factory):
    """After fulfillment, a fresh query must see status=completed + transaction id."""
    user_id, package_id = await _seed_user_and_package(session_factory)

    service = PaymentService(session_factory=session_factory)

    # Create pending purchase (simulating create_payment step)
    async with session_factory() as session:
        purchase = await PurchaseRepository(session).create(
            user_id=user_id,
            purchase_type="package",
            item_id=package_id,
            amount=40000,
            currency="RUB",
            payment_provider="yookassa",
        )
        await session.commit()
        purchase_id = purchase.id

    success = await service.handle_successful_payment(
        provider_name="yookassa",
        user_id=user_id,
        payment_type=PaymentType.PACKAGE,
        item_id=package_id,
        provider_transaction_id="charge_121_regression",
    )

    assert success is True

    # Verify persisted state from a completely fresh session
    async with session_factory() as session:
        result = await session.execute(select(Purchase).where(Purchase.id == purchase_id))
        persisted = result.scalar_one()
        assert (
            persisted.status == "completed"
        ), f"Purchase stayed in '{persisted.status}' — detached-instance bug (issue #121)"
        assert persisted.provider_transaction_id == "charge_121_regression"
        assert persisted.completed_at is not None

        # Minutes actually credited to the user
        balance_repo = UserMinuteBalanceRepository(session)
        balances = await balance_repo.get_active_balances(user_id)
        assert any(b.minutes_remaining == 500.0 for b in balances)

    # Idempotency: replaying the same transaction must not double-credit
    replay = await service.handle_successful_payment(
        provider_name="yookassa",
        user_id=user_id,
        payment_type=PaymentType.PACKAGE,
        item_id=package_id,
        provider_transaction_id="charge_121_regression",
    )
    assert replay is True

    async with session_factory() as session:
        balance_repo = UserMinuteBalanceRepository(session)
        balances = await balance_repo.get_active_balances(user_id)
        total = sum(b.minutes_remaining for b in balances)
        assert total == 500.0, f"Double credit detected: {total} minutes"


@pytest.mark.asyncio
async def test_handle_successful_payment_marks_failed_persistently(session_factory):
    """On fulfillment error, purchase must be persisted as failed (not stuck pending)."""
    user_id, _ = await _seed_user_and_package(session_factory)

    service = PaymentService(session_factory=session_factory)

    async with session_factory() as session:
        purchase = await PurchaseRepository(session).create(
            user_id=user_id,
            purchase_type="package",
            item_id=9999,  # nonexistent package → ValueError → mark_failed
            amount=40000,
            currency="RUB",
            payment_provider="yookassa",
        )
        await session.commit()
        purchase_id = purchase.id

    success = await service.handle_successful_payment(
        provider_name="yookassa",
        user_id=user_id,
        payment_type=PaymentType.PACKAGE,
        item_id=9999,
        provider_transaction_id="charge_121_fail",
    )

    assert success is False

    async with session_factory() as session:
        result = await session.execute(select(Purchase).where(Purchase.id == purchase_id))
        persisted = result.scalar_one()
        assert persisted.status == "failed"
