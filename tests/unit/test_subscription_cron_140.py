"""#140 волна 3: активация очереди подписок (крон + ленивая страховка).

Интеграционные тесты на in-memory SQLite (паттерн test_subscription_purchase_140.py):
сервис + репозиторий + реальная схема. SQLite возвращает naive datetime —
сравнения через datetime.now(timezone.utc) делаем аккуратно (плановые даты
проверяем на равенство, окна — с допуском).
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
        "basic": await _create_tier(async_session, "Basic", 1, 201),
        "pro": await _create_tier(async_session, "Pro", 2, 202),
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


def _naive(dt: datetime) -> datetime:
    """SQLite хранит/возвращает naive datetime — нормализуем для сравнений."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


async def _add_row(
    session: AsyncSession,
    user_id: int,
    tier_id: int,
    *,
    status: SubscriptionStatus,
    started_at: datetime,
    expires_at: datetime,
    auto_renew: bool = False,
) -> UserSubscription:
    row = UserSubscription(
        user_id=user_id,
        tier_id=tier_id,
        period="month",
        started_at=started_at,
        expires_at=expires_at,
        auto_renew=auto_renew,
        payment_provider=PROVIDER,
        status=status,
    )
    session.add(row)
    await session.flush()
    return row


class TestCronQueueActivation:
    async def test_expired_active_activates_queued_keeps_dates(self, async_session, service, tiers):
        """(a) expired active + due queued → queued становится active с прежним expires_at."""
        user = await _create_user(async_session, telegram_id=301)
        now = datetime.now(timezone.utc)
        await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.ACTIVE,
            started_at=now - timedelta(days=40),
            expires_at=now - timedelta(days=10),
        )
        planned_start = now - timedelta(days=1)  # старт уже наступил
        planned_expires = planned_start + timedelta(days=30)
        queued = await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.QUEUED,
            started_at=planned_start,
            expires_at=planned_expires,
        )

        expired_count = await service.check_expired_subscriptions()

        assert expired_count == 1
        rows = await _rows(async_session, user.id)
        assert rows[0].status == SubscriptionStatus.EXPIRED
        assert rows[1].id == queued.id
        assert rows[1].status == SubscriptionStatus.ACTIVE
        # Д1: даты плановые, не пересчитаны
        assert _naive(rows[1].started_at) == _naive(planned_start)
        assert _naive(rows[1].expires_at) == _naive(planned_expires)
        assert rows[1].auto_renew is False

    async def test_future_queued_not_activated(self, async_session, service, tiers):
        """(b) queued со started_at в будущем НЕ активируется кроном."""
        user = await _create_user(async_session, telegram_id=302)
        now = datetime.now(timezone.utc)
        await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.ACTIVE,
            started_at=now - timedelta(days=40),
            expires_at=now - timedelta(days=10),
        )
        queued = await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.QUEUED,
            started_at=now + timedelta(days=5),
            expires_at=now + timedelta(days=35),
        )

        expired_count = await service.check_expired_subscriptions()

        assert expired_count == 1
        rows = await _rows(async_session, user.id)
        assert rows[0].status == SubscriptionStatus.EXPIRED
        assert rows[1].status == SubscriptionStatus.QUEUED
        assert rows[1].id == queued.id

    async def test_live_active_blocks_queue_activation(self, async_session, service, tiers):
        """Юзер с живой active (auto_renew) — очередь не трогается."""
        user = await _create_user(async_session, telegram_id=303)
        now = datetime.now(timezone.utc)
        await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.ACTIVE,
            started_at=now - timedelta(days=40),
            expires_at=now - timedelta(days=10),
            auto_renew=True,  # крон пропустит expired-пометку
        )
        await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.QUEUED,
            started_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29),
        )

        expired_count = await service.check_expired_subscriptions()

        assert expired_count == 0
        rows = await _rows(async_session, user.id)
        assert rows[0].status == SubscriptionStatus.ACTIVE  # не тронута
        assert rows[1].status == SubscriptionStatus.QUEUED  # не активирована

    async def test_multiuser_independent(self, async_session, service, tiers):
        """Активация в кроне работает per-user, чужие очереди не задеваются."""
        user_a = await _create_user(async_session, telegram_id=304)
        user_b = await _create_user(async_session, telegram_id=305)
        now = datetime.now(timezone.utc)
        for u in (user_a, user_b):
            await _add_row(
                async_session,
                u.id,
                tiers["basic"].id,
                status=SubscriptionStatus.ACTIVE,
                started_at=now - timedelta(days=40),
                expires_at=now - timedelta(days=10),
            )
            await _add_row(
                async_session,
                u.id,
                tiers["basic"].id,
                status=SubscriptionStatus.QUEUED,
                started_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=29),
            )

        expired_count = await service.check_expired_subscriptions()

        assert expired_count == 2
        for u in (user_a, user_b):
            rows = await _rows(async_session, u.id)
            assert rows[0].status == SubscriptionStatus.EXPIRED
            assert rows[1].status == SubscriptionStatus.ACTIVE


class TestLazyActivation:
    async def test_get_active_subscription_activates_due_queued(
        self, async_session, service, tiers
    ):
        """(c) ленивая активация: get_active_subscription активирует due queued."""
        user = await _create_user(async_session, telegram_id=401)
        now = datetime.now(timezone.utc)
        planned_start = now - timedelta(days=1)
        planned_expires = planned_start + timedelta(days=30)
        queued = await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.QUEUED,
            started_at=planned_start,
            expires_at=planned_expires,
        )

        active = await service.get_active_subscription(user.id)

        assert active is not None
        assert active.id == queued.id
        assert active.status == SubscriptionStatus.ACTIVE
        # Д1: даты плановые, не пересчитаны
        assert _naive(active.started_at) == _naive(planned_start)
        assert _naive(active.expires_at) == _naive(planned_expires)
        assert active.auto_renew is False

    async def test_get_active_subscription_future_queued_stays_none(
        self, async_session, service, tiers
    ):
        """Ленивая активация: queued в будущем не активируется — вернётся None."""
        user = await _create_user(async_session, telegram_id=402)
        now = datetime.now(timezone.utc)
        await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.QUEUED,
            started_at=now + timedelta(days=5),
            expires_at=now + timedelta(days=35),
        )

        active = await service.get_active_subscription(user.id)

        assert active is None
        rows = await _rows(async_session, user.id)
        assert rows[0].status == SubscriptionStatus.QUEUED

    async def test_get_active_subscription_no_changes_when_live_active(
        self, async_session, service, tiers
    ):
        """Живая active возвращается как есть, queued не трогается."""
        user = await _create_user(async_session, telegram_id=403)
        now = datetime.now(timezone.utc)
        active_row = await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.ACTIVE,
            started_at=now - timedelta(days=5),
            expires_at=now + timedelta(days=25),
        )
        await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.QUEUED,
            started_at=now + timedelta(days=25),
            expires_at=now + timedelta(days=55),
        )

        active = await service.get_active_subscription(user.id)

        assert active is not None
        assert active.id == active_row.id
        rows = await _rows(async_session, user.id)
        assert rows[1].status == SubscriptionStatus.QUEUED


class TestInvariants:
    async def test_post_cron_at_most_one_active_one_queued(self, async_session, service, tiers):
        """(d) инвариант после прогона: ≤1 active и ≤1 queued на юзера."""
        user = await _create_user(async_session, telegram_id=501)
        now = datetime.now(timezone.utc)
        # мусорная ситуация: expired active + 3 due queued (нарушение one-queued)
        await _add_row(
            async_session,
            user.id,
            tiers["basic"].id,
            status=SubscriptionStatus.ACTIVE,
            started_at=now - timedelta(days=40),
            expires_at=now - timedelta(days=10),
        )
        for days_ago in (3, 2, 1):
            await _add_row(
                async_session,
                user.id,
                tiers["basic"].id,
                status=SubscriptionStatus.QUEUED,
                started_at=now - timedelta(days=days_ago),
                expires_at=now - timedelta(days=days_ago) + timedelta(days=30),
            )

        await service.check_expired_subscriptions()

        rows = await _rows(async_session, user.id)
        statuses = [r.status for r in rows]
        assert statuses.count(SubscriptionStatus.ACTIVE) == 1
        # самая ранняя по started_at активирована (started_at = now-3d)
        activated = next(r for r in rows if r.status == SubscriptionStatus.ACTIVE)
        assert _naive(activated.started_at) == _naive(now - timedelta(days=3))
        # прочие queued погашены — активной ровно одна, queued ноль
        assert statuses.count(SubscriptionStatus.QUEUED) == 0
        assert statuses.count(SubscriptionStatus.CANCELLED) == 2
