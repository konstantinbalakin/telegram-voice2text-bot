"""
Subscription Service - manage subscriptions: create, cancel, renew, upgrade/downgrade.
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Callable, Optional

from src.services.payments.base import SubscriptionPeriod, SubscriptionStatus
from src.storage.billing_repositories import (
    SubscriptionRepository,
    UserMinuteBalanceRepository,
    PurchaseRepository,
)
from src.storage.models import (
    SubscriptionTier,
    SubscriptionPrice,
    UserSubscription,
)

logger = logging.getLogger(__name__)

# Type alias for session factory (e.g. database.get_session)
SessionFactory = Callable[..., Any]


@dataclass(frozen=True)
class PurchasePreview:
    """Pre-purchase preview of what a subscription purchase would do (#140, волна 5).

    Показывается юзеру ДО создания инвойса. Сценарии:
    - "fresh"     — активной подписки нет, новая начнётся сразу
    - "renewal"   — тот же тир: новая подписка встанет в очередь на конец текущей
    - "upgrade"   — новый тир выше: вступит в силу сразу, остаток дней переносится
    - "downgrade" — новый тир ниже: смена с даты окончания текущей
    """

    scenario: str
    tier_id: int
    period: str
    started_at: Optional[datetime] = None  # None = «сразу» (fresh/upgrade)
    expires_at: Optional[datetime] = None
    carried_days: int = 0  # только upgrade: остаток дней текущей подписки


def remaining_days(expires_at: datetime, now: datetime) -> timedelta:
    """Carry-over remainder of an active subscription on upgrade (#140, 3.3).

    Полный остаток (дни+часы), не округляем: юзер за него заплатил.
    SQLite возвращает naive datetime — нормализуем оба аргумента.
    """
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return expires_at - now


class SubscriptionService:
    """Manage user subscriptions: create, cancel, renew, upgrade/downgrade.

    Accepts either a session_factory (production) or pre-built repos (testing).
    """

    def __init__(
        self,
        *,
        session_factory: Optional[SessionFactory] = None,
        subscription_repo: Optional[SubscriptionRepository] = None,
        balance_repo: Optional[UserMinuteBalanceRepository] = None,
        purchase_repo: Optional[PurchaseRepository] = None,
    ):
        self._session_factory = session_factory
        self._subscription_repo = subscription_repo
        self._balance_repo = balance_repo
        self._purchase_repo = purchase_repo

    @asynccontextmanager
    async def _repos(
        self,
    ) -> AsyncGenerator[
        tuple[SubscriptionRepository, UserMinuteBalanceRepository, PurchaseRepository],
        None,
    ]:
        """Get repositories — per-request session or pre-built (tests)."""
        if self._session_factory:
            async with self._session_factory() as session:
                yield (
                    SubscriptionRepository(session),
                    UserMinuteBalanceRepository(session),
                    PurchaseRepository(session),
                )
        else:
            assert self._subscription_repo is not None
            assert self._balance_repo is not None
            assert self._purchase_repo is not None
            yield (
                self._subscription_repo,
                self._balance_repo,
                self._purchase_repo,
            )

    async def get_available_tiers(self) -> list[SubscriptionTier]:
        """Get all active subscription tiers."""
        async with self._repos() as (subscription_repo, _, __):
            return await subscription_repo.get_active_tiers()

    async def get_tier_prices(
        self, tier_id: int, user_id: Optional[int] = None
    ) -> list[SubscriptionPrice]:
        """Get prices for a specific tier, with optional personal pricing."""
        async with self._repos() as (subscription_repo, _, __):
            return await subscription_repo.get_effective_prices(tier_id=tier_id, user_id=user_id)

    async def _activate_due_queue_for_user(
        self, subscription_repo: SubscriptionRepository, user_id: int
    ) -> Optional[UserSubscription]:
        """Activate the earliest due queued row for user (#140, волна 3).

        Инвариант: у юзера ≤1 active и ≤1 queued. Прочие due queued (если
        вдруг несколько) гасим — activate только самая ранняя по started_at.
        Д1: started_at/expires_at плановые, не пересчитываются.
        """
        due = await subscription_repo.get_due_queued_subscriptions(user_id)
        if not due:
            return None
        activated = await subscription_repo.activate_subscription(due[0])
        for extra in due[1:]:
            await subscription_repo.cancel_subscription_row(extra)
            logger.info(
                "Cancelled extra queued subscription %s for user %s (one-queued rule)",
                extra.id,
                user_id,
            )
        logger.info(
            "Activated queued subscription %s for user %s (expires_at=%s, dates kept)",
            activated.id,
            user_id,
            activated.expires_at,
        )
        return activated

    async def get_active_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """Get user's active subscription (#140, волна 3: ленивая активация).

        Если active нет, но есть queued со стартом <= now — активируем её
        (страховка на случай, когда крон ещё не успел). Даты плановые, Д1.
        """
        async with self._repos() as (subscription_repo, _, __):
            active = await subscription_repo.get_active_subscription(user_id=user_id)
            if active is not None:
                return active
            if await self._activate_due_queue_for_user(subscription_repo, user_id):
                return await subscription_repo.get_active_subscription(user_id=user_id)
            return None

    async def get_tier_by_id(self, tier_id: int) -> Optional[SubscriptionTier]:
        """Get tier by ID."""
        async with self._repos() as (subscription_repo, _, __):
            return await subscription_repo.get_tier_by_id(tier_id=tier_id)

    async def create_subscription(
        self,
        user_id: int,
        tier_id: int,
        period: str,
        payment_provider: str,
    ) -> UserSubscription:
        """Create a new subscription. Cancels existing if any."""
        async with self._repos() as (subscription_repo, _, __):
            existing = await subscription_repo.get_active_subscription(user_id=user_id)
            if existing:
                await subscription_repo.deactivate_subscription(existing)
                logger.info(f"Deactivated existing subscription {existing.id} for user {user_id}")

            days = SubscriptionPeriod(period).days
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)

            subscription = await subscription_repo.create_subscription(
                user_id=user_id,
                tier_id=tier_id,
                period=period,
                payment_provider=payment_provider,
                expires_at=expires_at,
                auto_renew=False,
            )

            logger.info(
                f"Created subscription {subscription.id} for user {user_id}: "
                f"tier={tier_id}, period={period}, expires={expires_at}"
            )
            return subscription

    async def purchase_subscription(
        self,
        user_id: int,
        tier_id: int,
        period: str,
        payment_provider: str,
    ) -> UserSubscription:
        """Paid subscription purchase (#140): routes scenarios 3.1-3.5.

        - 3.1 нет active (или истекла) → INSERT active
        - 3.2 тот же тир при живой active → INSERT queued (старт = конец текущей)
        - 3.3 апгрейд → старая replaced, новая active + перенос остатка дней
        - 3.4 даунгрейд → next_tier на active (без новой строки)
        - 3.5 пограничный: stale-active строки гасятся deactivate_all_active

        Инварианты: ≤1 active (индекс БД), ≤1 queued (отменяем старую, Д3).
        """
        async with self._repos() as (subscription_repo, _, __):
            return await self._purchase_impl(
                subscription_repo,
                user_id=user_id,
                tier_id=tier_id,
                period=period,
                payment_provider=payment_provider,
            )

    async def purchase_subscription_with_repo(
        self,
        subscription_repo: SubscriptionRepository,
        user_id: int,
        tier_id: int,
        period: str,
        payment_provider: str,
    ) -> UserSubscription:
        """Same as purchase_subscription but in the caller's session (#140).

        Платёжный поток (PaymentService.handle_successful_payment) открывает
        одну сессию и для выдачи подписки, и для mark_completed — так обе
        операции атомарны (commit/rollback вместе).
        """
        return await self._purchase_impl(
            subscription_repo,
            user_id=user_id,
            tier_id=tier_id,
            period=period,
            payment_provider=payment_provider,
        )

    async def _purchase_impl(
        self,
        subscription_repo: SubscriptionRepository,
        user_id: int,
        tier_id: int,
        period: str,
        payment_provider: str,
    ) -> UserSubscription:
        """Тело purchase_subscription; репозиторий передаётся снаружи."""
        # 3.5: погасить просроченные-but-active всегда — первопричина бага
        stale = await subscription_repo.get_stale_active_subscriptions(user_id)
        for sub in stale:
            await subscription_repo.expire_subscription(sub)
            logger.info(
                "Expired stale active subscription %s for user %s before purchase",
                sub.id,
                user_id,
            )

        active = await subscription_repo.get_active_subscription(user_id)
        now = datetime.now(timezone.utc)
        days = SubscriptionPeriod(period).days

        if active is None:
            # 3.1: чистая покупка
            subscription = await subscription_repo.create_subscription(
                user_id=user_id,
                tier_id=tier_id,
                period=period,
                payment_provider=payment_provider,
                expires_at=now + timedelta(days=days),
            )
            logger.info("Created active subscription for user %s: tier=%s", user_id, tier_id)
            return subscription

        # есть живая active — сравнить тиры
        if active.tier_id == tier_id:
            # 3.2: продление → queued (Д1: старт = плановый конец текущей)
            queued = await subscription_repo.get_queued_subscription(user_id)
            if queued is not None:
                await subscription_repo.cancel_subscription_row(queued)
                logger.info(
                    "Cancelled previous queued %s for user %s (one-queued rule)",
                    queued.id,
                    user_id,
                )
            subscription = await subscription_repo.create_subscription(
                user_id=user_id,
                tier_id=tier_id,
                period=period,
                payment_provider=payment_provider,
                expires_at=active.expires_at + timedelta(days=days),
                status=SubscriptionStatus.QUEUED,
                started_at=active.expires_at,
            )
            logger.info(
                "Queued renewal for user %s: start=%s end=%s",
                user_id,
                active.expires_at,
                active.expires_at + timedelta(days=days),
            )
            return subscription

        new_tier = await subscription_repo.get_tier_by_id(tier_id)
        current_tier = await subscription_repo.get_tier_by_id(active.tier_id)
        new_order = new_tier.display_order if new_tier else 0
        cur_order = current_tier.display_order if current_tier else 0

        if new_order > cur_order:
            # 3.3: апгрейд — старая replaced, новая active с остатком дней
            await subscription_repo.replace_subscription(active)
            remaining = max(remaining_days(active.expires_at, now), timedelta(0))
            expires = now + timedelta(days=days) + remaining
            subscription = await subscription_repo.create_subscription(
                user_id=user_id,
                tier_id=tier_id,
                period=period,
                payment_provider=payment_provider,
                expires_at=expires,
            )
            logger.info(
                "Upgrade for user %s: old %s replaced, new tier=%s expires=%s " "(+%s carried)",
                user_id,
                active.id,
                tier_id,
                expires,
                remaining,
            )
            return subscription

        # 3.4: даунгрейд — next_tier на текущей, новую строку не создаём
        queued = await subscription_repo.get_queued_subscription(user_id)
        if queued is not None:
            await subscription_repo.cancel_subscription_row(queued)
            logger.info("Cancelled queued %s for user %s before downgrade", queued.id, user_id)
        updated = await subscription_repo.set_next_tier(active, next_tier_id=tier_id)
        logger.info(
            "Downgrade for user %s: next tier=%s from %s",
            user_id,
            tier_id,
            active.expires_at,
        )
        return updated

    async def cancel_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """Cancel active subscription. Remains active until expiry."""
        async with self._repos() as (subscription_repo, _, __):
            active = await subscription_repo.get_active_subscription(user_id=user_id)
            if not active:
                logger.info(f"No active subscription to cancel for user {user_id}")
                return None

            cancelled = await subscription_repo.cancel_subscription(active)
            logger.info(f"Cancelled subscription {active.id} for user {user_id}")
            return cancelled

    async def renew_subscription(self, subscription: UserSubscription) -> UserSubscription:
        """Renew a subscription. Applies downgrade if next_subscription_tier_id is set."""
        async with self._repos() as (subscription_repo, _, __):
            tier_id = subscription.tier_id
            if subscription.next_subscription_tier_id:
                tier_id = subscription.next_subscription_tier_id
                logger.info(
                    f"Applying tier change on renewal: {subscription.tier_id} -> {tier_id} "
                    f"for user {subscription.user_id}"
                )

            days = SubscriptionPeriod(subscription.period).days
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)

            new_sub = await subscription_repo.create_subscription(
                user_id=subscription.user_id,
                tier_id=tier_id,
                period=subscription.period,
                payment_provider=subscription.payment_provider,
                expires_at=expires_at,
                auto_renew=False,
            )

            logger.info(
                f"Renewed subscription for user {subscription.user_id}: "
                f"old={subscription.id} -> new={new_sub.id}"
            )
            return new_sub

    async def check_expired_subscriptions(self) -> int:
        """Check and mark expired subscriptions, then activate queue (#140, волна 3).

        Returns count of expired. После пометки expired: юзерам без active,
        но с due queued (started_at<=now) активируем самую раннюю — даты
        плановые (Д1), после прогона ≤1 active и ≤1 queued.
        """
        async with self._repos() as (subscription_repo, _, __):
            expired_subs = await subscription_repo.get_expired_subscriptions()
            count = 0
            for sub in expired_subs:
                if sub.auto_renew:
                    logger.info(
                        f"Subscription {sub.id} expired but auto_renew=True, skipping expire"
                    )
                    continue
                await subscription_repo.expire_subscription(sub)
                count += 1
                logger.info(f"Marked subscription {sub.id} as expired for user {sub.user_id}")

            # Волна 3: активация очереди у юзеров, оставшихся без active
            # (только у тех, чьи строки реально погашены; auto_renew-строки
            # пропущены и юзера не трогаем — их жизненный цикл ведёт renew)
            expired_users: set[int] = set()
            for sub in expired_subs:
                if sub.auto_renew:
                    continue
                expired_users.add(sub.user_id)
            for user_id in expired_users:
                if await subscription_repo.get_active_subscription(user_id) is not None:
                    continue  # что-то ещё живо — очередь не трогаем
                await self._activate_due_queue_for_user(subscription_repo, user_id)
            return count

    async def handle_upgrade(
        self,
        user_id: int,
        new_tier_id: int,
        new_period: str,
        payment_provider: str,
    ) -> UserSubscription:
        """Handle upgrade — applies immediately (cancels old, creates new)."""
        return await self.create_subscription(
            user_id=user_id,
            tier_id=new_tier_id,
            period=new_period,
            payment_provider=payment_provider,
        )

    async def handle_downgrade(self, user_id: int, new_tier_id: int) -> Optional[UserSubscription]:
        """Handle downgrade — saved for next renewal via next_subscription_tier_id."""
        async with self._repos() as (subscription_repo, _, __):
            active = await subscription_repo.get_active_subscription(user_id=user_id)
            if not active:
                logger.info(f"No active subscription for downgrade, user {user_id}")
                return None

            updated = await subscription_repo.set_next_tier(active, next_tier_id=new_tier_id)
            logger.info(
                f"Set downgrade for user {user_id}: "
                f"current tier={active.tier_id} -> next tier={new_tier_id}"
            )
            return updated

    async def get_expiring_subscriptions(self, days_ahead: int = 3) -> list[UserSubscription]:
        """Get subscriptions expiring within N days."""
        async with self._repos() as (subscription_repo, _, __):
            return await subscription_repo.get_expiring_subscriptions(days_ahead=days_ahead)

    async def get_expiring_subscriptions_stars(self, days_ahead: int = 3) -> list[UserSubscription]:
        """Get Telegram Stars subscriptions expiring within N days (need manual renewal)."""
        all_expiring = await self.get_expiring_subscriptions(days_ahead=days_ahead)
        return [sub for sub in all_expiring if sub.payment_provider == "telegram_stars"]

    async def preview_purchase(
        self,
        user_id: int,
        tier_id: int,
        period: str,
    ) -> Optional[PurchasePreview]:
        """Preview what a purchase would do, WITHOUT writing to DB (#140, волна 5).

        UX-слой бота вызывает это ДО создания инвойса, чтобы показать
        подтверждение с датами. Сценарии зеркалят purchase_subscription (3.1-3.4):

        - fresh     — нет живой active (None из get_active_subscription, который
                      сам лениво активирует due-queued)
        - renewal   — тот же тир: started_at = конец текущей, expires = +период
        - upgrade   — display_order выше: сразу, expires = now+период+остаток
        - downgrade — display_order ниже или равен (но тир другой): с даты
                      окончания текущей

        Returns:
            PurchasePreview, если есть живая active (нужно подтверждение).
            None — если активной подписки нет (обычный флоу, подтверждение
            не показывается).
        """
        async with self._repos() as (subscription_repo, _, __):
            active = await subscription_repo.get_active_subscription(user_id=user_id)
            if active is None:
                return None

            now = datetime.now(timezone.utc)
            days = SubscriptionPeriod(period).days
            expires_at_norm = (
                active.expires_at.replace(tzinfo=timezone.utc)
                if active.expires_at.tzinfo is None
                else active.expires_at
            )

            if active.tier_id == tier_id:
                # 3.2: продление — встанет в очередь на конец текущей
                return PurchasePreview(
                    scenario="renewal",
                    tier_id=tier_id,
                    period=period,
                    started_at=expires_at_norm,
                    expires_at=expires_at_norm + timedelta(days=days),
                )

            new_tier = await subscription_repo.get_tier_by_id(tier_id=tier_id)
            current_tier = await subscription_repo.get_tier_by_id(tier_id=active.tier_id)
            new_order = new_tier.display_order if new_tier else 0
            cur_order = current_tier.display_order if current_tier else 0

            if new_order > cur_order:
                # 3.3: апгрейд — вступит в силу сразу, остаток переносится
                remaining = max(remaining_days(active.expires_at, now), timedelta(0))
                carried_days = int(remaining.total_seconds() // 86400)
                return PurchasePreview(
                    scenario="upgrade",
                    tier_id=tier_id,
                    period=period,
                    started_at=now,
                    expires_at=now + timedelta(days=days) + remaining,
                    carried_days=carried_days,
                )

            # 3.4: даунгрейд — смена тира с даты окончания текущей
            return PurchasePreview(
                scenario="downgrade",
                tier_id=tier_id,
                period=period,
                started_at=expires_at_norm,
                expires_at=None,
            )
