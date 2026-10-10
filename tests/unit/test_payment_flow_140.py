"""#140 волна 4: платёжный поток на purchase_subscription + единая сессия выдачи.

Интеграционные тесты на in-memory SQLite (паттерн test_subscription_purchase_140):
- abandoned-регресс find_pending_purchase;
- идемпотентность повторной обработки provider_transaction_id;
- атомарность: сбой mark-фазы → подписка не видна в новой сессии (rollback).
"""

from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager

from src.services.payments.base import PaymentType, PurchaseStatus
from src.services.payments.payment_service import PaymentService
from src.services.subscription_service import SubscriptionService
from src.storage.billing_repositories import (
    MinutePackageRepository,
    PurchaseRepository,
    SubscriptionRepository,
    UserMinuteBalanceRepository,
)
from src.storage.models import Purchase, SubscriptionTier, User, UserSubscription

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


async def _create_purchase(
    session: AsyncSession,
    user_id: int,
    item_id: int,
    provider: str = PROVIDER,
    transaction_id: str | None = None,
    status: PurchaseStatus = PurchaseStatus.PENDING,
) -> Purchase:
    purchase = Purchase(
        user_id=user_id,
        purchase_type="subscription",
        item_id=item_id,
        amount=10000,
        currency="RUB",
        payment_provider=provider,
        provider_transaction_id=transaction_id,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    session.add(purchase)
    await session.flush()
    return purchase


@pytest_asyncio.fixture
async def tier(async_session):
    return await _create_tier(async_session, "Basic", 1, 101)


@pytest_asyncio.fixture
def subscription_service(async_session):
    """SubscriptionService с готовыми репозиториями (тестовый путь _repos)."""
    return SubscriptionService(
        subscription_repo=SubscriptionRepository(async_session),
        balance_repo=UserMinuteBalanceRepository(async_session),
        purchase_repo=PurchaseRepository(async_session),
    )


@pytest_asyncio.fixture
def payment_service(async_session, subscription_service):
    """PaymentService с готовыми репозиториями (тестовый путь _repos)."""
    return PaymentService(
        purchase_repo=PurchaseRepository(async_session),
        subscription_repo=SubscriptionRepository(async_session),
        balance_repo=UserMinuteBalanceRepository(async_session),
        package_repo=MinutePackageRepository(async_session),
        subscription_service=subscription_service,
    )


@pytest_asyncio.fixture
async def committing_session_factory(async_engine):
    """Фабрика сессий с commit-on-success — как прод get_session (#121-паттерн)."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

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


async def _subs(async_session, user_id: int) -> list[UserSubscription]:
    result = await async_session.execute(
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


class TestAbandonedRegression:
    async def test_find_pending_skips_abandoned(self, async_session, tier):
        """Юзер с pending + abandoned покупками: find_pending возвращает только pending."""
        user = await _create_user(async_session)
        await _create_purchase(
            async_session,
            user.id,
            tier.id,
            status=PurchaseStatus.ABANDONED,
        )
        pending = await _create_purchase(async_session, user.id, tier.id)

        repo = PurchaseRepository(async_session)
        found = await repo.find_pending_purchase(
            user_id=user.id,
            purchase_type="subscription",
            item_id=tier.id,
        )
        assert found is not None
        assert found.id == pending.id
        assert found.status == PurchaseStatus.PENDING

    async def test_find_pending_returns_none_when_all_abandoned(self, async_session, tier):
        """Только abandoned → pending не найден (инвойс не «оживится» задним числом)."""
        user = await _create_user(async_session, telegram_id=43)
        await _create_purchase(
            async_session,
            user.id,
            tier.id,
            status=PurchaseStatus.ABANDONED,
        )
        repo = PurchaseRepository(async_session)
        found = await repo.find_pending_purchase(
            user_id=user.id,
            purchase_type="subscription",
            item_id=tier.id,
        )
        assert found is None


class TestIdempotency:
    async def test_repeated_transaction_id_is_noop(self, payment_service, async_session, tier):
        """Повторная обработка того же provider_transaction_id — no-op (return True)."""
        user = await _create_user(async_session)
        await _create_purchase(async_session, user.id, tier.id)
        await async_session.commit()

        # Первая обработка: fulfilment + mark_completed.
        ok1 = await payment_service.handle_successful_payment(
            provider_name=PROVIDER,
            user_id=user.id,
            payment_type=PaymentType.SUBSCRIPTION,
            item_id=tier.id,
            provider_transaction_id="tx-1",
        )
        assert ok1 is True

        # Фактическая семантика: idempotency-чек находит purchase по tx_id и
        # возвращает True без создания второй подписки.
        ok2 = await payment_service.handle_successful_payment(
            provider_name=PROVIDER,
            user_id=user.id,
            payment_type=PaymentType.SUBSCRIPTION,
            item_id=tier.id,
            provider_transaction_id="tx-1",
        )
        assert ok2 is True

        # Фиксируем: одна строка подписки, одна completed-покупка.
        assert len(await _subs(async_session, user.id)) == 1
        repo = PurchaseRepository(async_session)
        tx = await repo.find_by_transaction_id("tx-1")
        assert tx is not None
        assert tx.status == PurchaseStatus.COMPLETED


class TestTransactionality:
    async def test_mark_phase_failure_rolls_back_subscription(
        self, committing_session_factory, async_engine, tier, monkeypatch
    ):
        """Сбой mark-фазы в общей сессии: rollback — подписки нет в новой сессии.

        purchase_subscription_with_repo и mark_completed живут в одной сессии
        payment_service._repos(); исключение в mark-фазе откатывает и INSERT
        подписки (commit был бы только на выходе из контекста).
        """
        maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

        # Seed user + tier + pending purchase в отдельной сессии.
        async with maker() as seed:
            user = User(telegram_id=777, username="tx-user")
            seed.add(user)
            await seed.flush()
            user_id = user.id
            await seed.commit()

        service = PaymentService(
            session_factory=committing_session_factory,
            subscription_service=SubscriptionService(session_factory=committing_session_factory),
        )

        async with maker() as seed:
            purchase = Purchase(
                user_id=user_id,
                purchase_type="subscription",
                item_id=tier.id,
                amount=10000,
                currency="RUB",
                payment_provider=PROVIDER,
                status=PurchaseStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            seed.add(purchase)
            await seed.flush()
            purchase_id = purchase.id
            await seed.commit()

        # Мокаем mark_completed: падает в mark-фазе общей сессии.
        async def boom(self, purchase):
            raise RuntimeError("mark phase exploded")

        monkeypatch.setattr(PurchaseRepository, "mark_completed", boom)

        ok = await service.handle_successful_payment(
            provider_name=PROVIDER,
            user_id=user_id,
            payment_type=PaymentType.SUBSCRIPTION,
            item_id=tier.id,
            provider_transaction_id="tx-rollback",
        )
        assert ok is False

        # Новая сессия: подписка НЕ видна (rollback общей сессии откатил INSERT).
        # Покупка помечена failed catch-блоком (компенсация в новой сессии).
        async with maker() as check:
            subs = await check.execute(
                select(UserSubscription).where(UserSubscription.user_id == user_id)
            )
            assert list(subs.scalars().all()) == []
            # Покупка помечена failed: mark_completed в общей сессии откатился
            # (INSERT подписки + запись tx_id исчезли), компенсирующий
            # mark_failed выполнен в отдельной сессии и закоммичен.
            tx = await check.execute(select(Purchase).where(Purchase.id == purchase_id))
            failed_purchase = tx.scalars().first()
            assert failed_purchase is not None
            assert failed_purchase.status == PurchaseStatus.FAILED
            assert failed_purchase.provider_transaction_id is None
