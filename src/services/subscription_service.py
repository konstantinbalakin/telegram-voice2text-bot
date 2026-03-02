"""
Subscription Service - manage subscriptions: create, cancel, renew, upgrade/downgrade.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Callable, Optional

from src.services.payments.base import SubscriptionPeriod
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

    async def get_tier_prices(self, tier_id: int) -> list[SubscriptionPrice]:
        """Get prices for a specific tier."""
        async with self._repos() as (subscription_repo, _, __):
            return await subscription_repo.get_tier_prices(tier_id=tier_id)

    async def get_active_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """Get user's active subscription."""
        async with self._repos() as (subscription_repo, _, __):
            return await subscription_repo.get_active_subscription(user_id=user_id)

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
                await subscription_repo.cancel_subscription(existing)
                logger.info(f"Cancelled existing subscription {existing.id} for user {user_id}")

            days = SubscriptionPeriod(period).days
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)

            subscription = await subscription_repo.create_subscription(
                user_id=user_id,
                tier_id=tier_id,
                period=period,
                payment_provider=payment_provider,
                expires_at=expires_at,
            )

            logger.info(
                f"Created subscription {subscription.id} for user {user_id}: "
                f"tier={tier_id}, period={period}, expires={expires_at}"
            )
            return subscription

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
            )

            logger.info(
                f"Renewed subscription for user {subscription.user_id}: "
                f"old={subscription.id} -> new={new_sub.id}"
            )
            return new_sub

    async def check_expired_subscriptions(self) -> int:
        """Check and mark expired subscriptions. Returns count of expired."""
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
