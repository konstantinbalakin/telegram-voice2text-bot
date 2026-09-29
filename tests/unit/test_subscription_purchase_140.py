"""#140: сценарии покупки подписки (purchase_subscription, 3.1-3.5).

Интеграционные тесты на in-memory SQLite (паттерн conftest.py):
сервис + репозиторий + реальная схема, мокается только session factory.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.payments.base import SubscriptionStatus
from src.services.subscription_service import SubscriptionService
from src.storage.models import SubscriptionTier, User, UserSubscription

PROVIDER = "test-provider"


async def _create_user(session: AsyncSession, telegram_id: int = 42) -> User:
    user = User(telegram_id=telegram_id, username="tester")
    session.add(user)
    await session.flush()
    return user


async def _create_tier(
    session: AsyncSession, name: str, order: int, tier_id: int
) -> SubscriptionTier:
    tier = SubscriptionTier(id=tier_id, name=name, daily_limit_minutes=30.0, display_order=order)
    session.add(tier)
    await session.flush()
    return tier


@pytest_asyncio.fixture
async def tiers(async_session):
    """Простой (order=1) и Про (order=2) тиры."""
    return {
        "basic": await _create_tier(async_session, "Basic", 1, 101),
        "pro": await _create_tier(async_session, "Pro", 2, 102),
    }


@pytest_asyncio.fixture
def service(async_session):
    """SubscriptionService с готовыми репозиториями (тестовый путь _repos)."""
    from src.storage.billing_repositories import (
        PurchaseRepository,
        SubscriptionRepository,
        UserMinuteBalanceRepository,
    )

    return SubscriptionService(
        subscription_repo=SubscriptionRepository(async_session),
        balance_repo=UserMinuteBalanceRepository(async_session),
        purchase_repo=PurchaseRepository(async_session),
    )


async def _rows(async_session, user_id: int) -> list[UserSubscription]:
    result = await async_session.execute(
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id)
        .order_by(UserSubscription.id)
    )
    return list(result.scalars().all())


class TestScenario31FreshPurchase:
    async def test_no_active_creates_active(self, async_session, service, tiers):
        user = await _create_user(async_session)
        sub = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.started_at <= datetime.now(timezone.utc) < sub.expires_at
        rows = await _rows(async_session, user.id)
        assert len(rows) == 1

    async def test_expired_row_allows_new_active(self, async_session, service, tiers):
        # истёкшая строка (expired) не мешает новой покупке
        user = await _create_user(async_session, telegram_id=43)
        old = UserSubscription(
            user_id=user.id,
            tier_id=tiers["basic"].id,
            period="month",
            started_at=datetime.now(timezone.utc) - timedelta(days=40),
            expires_at=datetime.now(timezone.utc) - timedelta(days=10),
            payment_provider=PROVIDER,
            status=SubscriptionStatus.EXPIRED,
        )
        async_session.add(old)
        await async_session.flush()

        sub = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        assert sub.status == SubscriptionStatus.ACTIVE


class TestScenario32Renewal:
    async def test_same_tier_creates_queued(self, async_session, service, tiers):
        user = await _create_user(async_session)
        first = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        second = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        assert second.status == SubscriptionStatus.QUEUED
        # Д1: старт = плановый конец текущей, срок не пересчитывается
        assert second.started_at == first.expires_at
        assert second.expires_at == first.expires_at + timedelta(days=30)
        # инварианты: 1 active, 1 queued
        rows = await _rows(async_session, user.id)
        statuses = [r.status for r in rows]
        assert statuses.count(SubscriptionStatus.ACTIVE) == 1
        assert statuses.count(SubscriptionStatus.QUEUED) == 1

    async def test_second_renewal_replaces_queued(self, async_session, service, tiers):
        user = await _create_user(async_session)
        await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        third = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        rows = await _rows(async_session, user.id)
        statuses = [r.status for r in rows]
        # Д3-правило: старая queued отменена, новая одна
        assert statuses.count(SubscriptionStatus.QUEUED) == 1
        assert statuses.count(SubscriptionStatus.CANCELLED) == 1
        assert third.status == SubscriptionStatus.QUEUED


class TestScenario33Upgrade:
    async def test_upgrade_replaces_and_carries_days(self, async_session, service, tiers):
        user = await _create_user(async_session)
        first = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        before = datetime.now(timezone.utc)
        upgraded = await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)
        rows = await _rows(async_session, user.id)
        old = rows[0]
        assert old.status == SubscriptionStatus.REPLACED  # Д2
        assert upgraded.status == SubscriptionStatus.ACTIVE
        assert upgraded.tier_id == tiers["pro"].id
        # остаток старой перенесён: expires > now + 30d
        assert upgraded.expires_at > before + timedelta(days=30)
        assert upgraded.expires_at < first.expires_at + timedelta(days=30) + timedelta(minutes=1)

    async def test_upgrade_to_same_expires_bounds(self, async_session, service, tiers):
        # границы переноса: остаток старой (≤30 дн. для свежей) + 30 дн. новой
        user = await _create_user(async_session, telegram_id=77)
        await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        before = datetime.now(timezone.utc)
        up = await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)
        # верхняя граница: перенос не больше полного остатка старой (30 дн.)
        assert up.expires_at - before <= timedelta(days=60)
        # нижняя: без переноса было бы ровно 30 дн.
        assert up.expires_at - before > timedelta(days=30)


class TestScenario34Downgrade:
    async def test_downgrade_sets_next_tier_no_new_row(self, async_session, service, tiers):
        user = await _create_user(async_session)
        await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)
        result = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        rows = await _rows(async_session, user.id)
        assert len(rows) == 1  # новая строка не создаётся
        assert rows[0].status == SubscriptionStatus.ACTIVE
        assert rows[0].next_subscription_tier_id == tiers["basic"].id
        assert result.id == rows[0].id

    async def test_downgrade_cancels_existing_queued(self, async_session, service, tiers):
        user = await _create_user(async_session, telegram_id=78)
        await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)
        await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)  # queued
        await service.purchase_subscription(
            user.id, tiers["basic"].id, "month", PROVIDER
        )  # downgrade
        rows = await _rows(async_session, user.id)
        statuses = [r.status for r in rows]
        assert statuses.count(SubscriptionStatus.CANCELLED) == 1  # queued отменена
        assert statuses.count(SubscriptionStatus.QUEUED) == 0
        assert rows[0].next_subscription_tier_id == tiers["basic"].id


class TestScenario35StaleActive:
    async def test_stale_active_expired_then_purchase_ok(self, async_session, service, tiers):
        # первопричина бага: active с прошедшим expires_at
        user = await _create_user(async_session, telegram_id=79)
        stale = UserSubscription(
            user_id=user.id,
            tier_id=tiers["basic"].id,
            period="month",
            started_at=datetime.now(timezone.utc) - timedelta(days=60),
            expires_at=datetime.now(timezone.utc) - timedelta(days=30),
            payment_provider=PROVIDER,
            status=SubscriptionStatus.ACTIVE,
        )
        async_session.add(stale)
        await async_session.flush()

        sub = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        rows = await _rows(async_session, user.id)
        # старая погашена (expired), новая active, IntegrityError нет
        assert rows[0].status == SubscriptionStatus.EXPIRED
        assert rows[1].status == SubscriptionStatus.ACTIVE
        assert sub.id == rows[1].id


class TestInvariants:
    async def test_at_most_one_active_one_queued(self, async_session, service, tiers):
        user = await _create_user(async_session, telegram_id=80)
        # серия покупок: basic, basic (queued), upgrade pro, pro (queued)
        await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)
        await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)
        await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)
        rows = await _rows(async_session, user.id)
        statuses = [r.status for r in rows]
        assert statuses.count(SubscriptionStatus.ACTIVE) == 1
        assert statuses.count(SubscriptionStatus.QUEUED) == 1
