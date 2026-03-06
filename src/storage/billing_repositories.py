"""
Billing system repositories for database access
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.payments.base import (
    PurchaseStatus,
    SubscriptionStatus,
)
from src.storage.models import (
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

logger = logging.getLogger(__name__)


class BillingConditionRepository:
    """Repository for BillingCondition model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        key: str,
        value: str,
        user_id: Optional[int] = None,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None,
    ) -> BillingCondition:
        """Create a billing condition."""
        condition = BillingCondition(
            key=key,
            value=value,
            user_id=user_id,
            valid_from=valid_from or datetime.now(timezone.utc),
            valid_to=valid_to,
        )
        self.session.add(condition)
        await self.session.flush()
        return condition

    async def get_effective_value(
        self,
        key: str,
        user_id: Optional[int] = None,
    ) -> Optional[str]:
        """Get effective condition value with individual priority over global.

        Priority: individual (user_id match) > global (user_id is None).
        Only returns conditions where valid_from <= now and (valid_to is None or valid_to > now).
        """
        now = datetime.now(timezone.utc)

        validity_filter = and_(
            BillingCondition.valid_from <= now,
            (BillingCondition.valid_to.is_(None)) | (BillingCondition.valid_to > now),
        )

        # Try individual condition first
        if user_id is not None:
            result = await self.session.execute(
                select(BillingCondition.value)
                .where(
                    and_(
                        BillingCondition.key == key,
                        BillingCondition.user_id == user_id,
                        validity_filter,
                    )
                )
                .order_by(BillingCondition.created_at.desc())
                .limit(1)
            )
            value = result.scalar_one_or_none()
            if value is not None:
                return value

        # Fall back to global condition
        result = await self.session.execute(
            select(BillingCondition.value)
            .where(
                and_(
                    BillingCondition.key == key,
                    BillingCondition.user_id.is_(None),
                    validity_filter,
                )
            )
            .order_by(BillingCondition.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class SubscriptionRepository:
    """Repository for subscription tiers, prices, and user subscriptions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Tiers ---

    async def create_tier(
        self,
        name: str,
        daily_limit_minutes: float,
        description: Optional[str] = None,
        display_order: int = 0,
        is_active: bool = True,
    ) -> SubscriptionTier:
        """Create a subscription tier."""
        tier = SubscriptionTier(
            name=name,
            daily_limit_minutes=daily_limit_minutes,
            description=description,
            display_order=display_order,
            is_active=is_active,
        )
        self.session.add(tier)
        await self.session.flush()
        return tier

    async def get_active_tiers(self) -> list[SubscriptionTier]:
        """Get all active tiers sorted by display_order."""
        result = await self.session.execute(
            select(SubscriptionTier)
            .where(SubscriptionTier.is_active.is_(True))
            .order_by(SubscriptionTier.display_order)
        )
        return list(result.scalars().all())

    async def get_tier_by_id(self, tier_id: int) -> Optional[SubscriptionTier]:
        """Get tier by ID."""
        result = await self.session.execute(
            select(SubscriptionTier).where(SubscriptionTier.id == tier_id)
        )
        return result.scalar_one_or_none()

    # --- Prices ---

    async def create_price(
        self,
        tier_id: int,
        period: str,
        amount_rub: float,
        amount_stars: int,
        description: Optional[str] = None,
        is_active: bool = True,
    ) -> SubscriptionPrice:
        """Create a subscription price."""
        price = SubscriptionPrice(
            tier_id=tier_id,
            period=period,
            amount_rub=amount_rub,
            amount_stars=amount_stars,
            description=description,
            is_active=is_active,
        )
        self.session.add(price)
        await self.session.flush()
        return price

    async def get_tier_prices(self, tier_id: int) -> list[SubscriptionPrice]:
        """Get active prices for a tier."""
        result = await self.session.execute(
            select(SubscriptionPrice).where(
                and_(
                    SubscriptionPrice.tier_id == tier_id,
                    SubscriptionPrice.is_active.is_(True),
                )
            )
        )
        return list(result.scalars().all())

    # --- User Subscriptions ---

    async def create_subscription(
        self,
        user_id: int,
        tier_id: int,
        period: str,
        payment_provider: str,
        expires_at: datetime,
        auto_renew: bool = False,
    ) -> UserSubscription:
        """Create a user subscription."""
        subscription = UserSubscription(
            user_id=user_id,
            tier_id=tier_id,
            period=period,
            started_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            auto_renew=auto_renew,
            payment_provider=payment_provider,
            status=SubscriptionStatus.ACTIVE,
        )
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def get_active_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """Get the active subscription for a user.

        Raises MultipleResultsFound if duplicates exist (fail-fast).
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(UserSubscription).where(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.expires_at > now,
                )
            )
        )
        return result.scalar_one_or_none()

    async def deactivate_subscription(self, subscription: UserSubscription) -> UserSubscription:
        """Deactivate a subscription immediately (e.g. replaced by a new one).

        Sets status to CANCELLED and disables auto-renewal.
        Unlike cancel_subscription, the subscription stops being active right away.
        """
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.auto_renew = False
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return subscription

    async def cancel_subscription(self, subscription: UserSubscription) -> UserSubscription:
        """Cancel a subscription: disable auto-renewal but keep active until expiry.

        Status remains 'active' so the user retains their tier benefits until expires_at.
        """
        subscription.auto_renew = False
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return subscription

    async def set_next_tier(
        self, subscription: UserSubscription, next_tier_id: int
    ) -> UserSubscription:
        """Set next_subscription_tier_id for downgrade at next renewal."""
        subscription.next_subscription_tier_id = next_tier_id
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return subscription

    async def get_expired_subscriptions(self) -> list[UserSubscription]:
        """Get active subscriptions that have expired."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(UserSubscription).where(
                and_(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.expires_at <= now,
                )
            )
        )
        return list(result.scalars().all())

    async def expire_subscription(self, subscription: UserSubscription) -> UserSubscription:
        """Mark a subscription as expired."""
        subscription.status = SubscriptionStatus.EXPIRED
        subscription.auto_renew = False
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return subscription

    async def get_expiring_subscriptions(self, days_ahead: int = 3) -> list[UserSubscription]:
        """Get subscriptions expiring within N days."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_ahead)
        result = await self.session.execute(
            select(UserSubscription).where(
                and_(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.expires_at <= cutoff,
                    UserSubscription.expires_at > now,
                )
            )
        )
        return list(result.scalars().all())


class MinutePackageRepository:
    """Repository for MinutePackage model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        name: str,
        minutes: float,
        price_rub: float,
        price_stars: int,
        description: Optional[str] = None,
        display_order: int = 0,
        is_active: bool = True,
    ) -> MinutePackage:
        """Create a minute package."""
        package = MinutePackage(
            name=name,
            minutes=minutes,
            price_rub=price_rub,
            price_stars=price_stars,
            description=description,
            display_order=display_order,
            is_active=is_active,
        )
        self.session.add(package)
        await self.session.flush()
        return package

    async def get_active_packages(self) -> list[MinutePackage]:
        """Get all active packages sorted by display_order."""
        result = await self.session.execute(
            select(MinutePackage)
            .where(MinutePackage.is_active.is_(True))
            .order_by(MinutePackage.display_order)
        )
        return list(result.scalars().all())

    async def get_by_id(self, package_id: int) -> Optional[MinutePackage]:
        """Get package by ID."""
        result = await self.session.execute(
            select(MinutePackage).where(MinutePackage.id == package_id)
        )
        return result.scalar_one_or_none()


class UserMinuteBalanceRepository:
    """Repository for UserMinuteBalance model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        balance_type: str,
        minutes_remaining: float,
        expires_at: Optional[datetime] = None,
        source_description: Optional[str] = None,
    ) -> UserMinuteBalance:
        """Create a minute balance entry."""
        balance = UserMinuteBalance(
            user_id=user_id,
            balance_type=balance_type,
            minutes_remaining=minutes_remaining,
            expires_at=expires_at,
            source_description=source_description,
        )
        self.session.add(balance)
        await self.session.flush()
        return balance

    async def get_active_balances(self, user_id: int) -> list[UserMinuteBalance]:
        """Get all active (non-zero, non-expired) balances for a user.

        Ordered: bonus first, then package (deduction priority).
        Within same type, oldest first (FIFO).
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(UserMinuteBalance)
            .where(
                and_(
                    UserMinuteBalance.user_id == user_id,
                    UserMinuteBalance.minutes_remaining > 0,
                    (UserMinuteBalance.expires_at.is_(None)) | (UserMinuteBalance.expires_at > now),
                )
            )
            .order_by(
                # bonus < package alphabetically, so ASC gives bonus first
                UserMinuteBalance.balance_type.asc(),
                UserMinuteBalance.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_total_minutes(self, user_id: int, balance_type: Optional[str] = None) -> float:
        """Get total remaining minutes for a user, optionally filtered by type."""
        now = datetime.now(timezone.utc)
        query = select(func.coalesce(func.sum(UserMinuteBalance.minutes_remaining), 0.0)).where(
            and_(
                UserMinuteBalance.user_id == user_id,
                UserMinuteBalance.minutes_remaining > 0,
                (UserMinuteBalance.expires_at.is_(None)) | (UserMinuteBalance.expires_at > now),
            )
        )
        if balance_type is not None:
            query = query.where(UserMinuteBalance.balance_type == balance_type)

        result = await self.session.execute(query)
        return float(result.scalar_one())

    async def deduct_minutes(self, balance_id: int, minutes: float) -> UserMinuteBalance:
        """Deduct minutes from a specific balance."""
        result = await self.session.execute(
            select(UserMinuteBalance).where(UserMinuteBalance.id == balance_id)
        )
        balance = result.scalar_one()
        balance.minutes_remaining = max(0.0, balance.minutes_remaining - minutes)
        balance.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return balance

    async def has_welcome_bonus(self, user_id: int) -> bool:
        """Check if user already received a welcome bonus."""
        result = await self.session.execute(
            select(func.count())
            .select_from(UserMinuteBalance)
            .where(
                and_(
                    UserMinuteBalance.user_id == user_id,
                    UserMinuteBalance.source_description == "Welcome bonus",
                )
            )
        )
        return result.scalar_one() > 0


class DailyUsageRepository:
    """Repository for DailyUsage model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: int, usage_date: date) -> tuple[DailyUsage, bool]:
        """Get or create daily usage record. Returns (usage, created).

        Handles race condition: if concurrent INSERT causes IntegrityError
        (UNIQUE constraint on user_id+date), retries with SELECT.
        """
        result = await self.session.execute(
            select(DailyUsage).where(
                and_(
                    DailyUsage.user_id == user_id,
                    DailyUsage.date == usage_date,
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing, False

        try:
            usage = DailyUsage(
                user_id=user_id,
                date=usage_date,
                minutes_used=0.0,
                minutes_from_daily=0.0,
                minutes_from_bonus=0.0,
                minutes_from_package=0.0,
            )
            self.session.add(usage)
            await self.session.flush()
            return usage, True
        except IntegrityError:
            await self.session.rollback()
            result = await self.session.execute(
                select(DailyUsage).where(
                    and_(
                        DailyUsage.user_id == user_id,
                        DailyUsage.date == usage_date,
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing, False
            raise

    async def add_usage(
        self,
        daily_usage: DailyUsage,
        minutes_used: float,
        from_daily: float = 0.0,
        from_bonus: float = 0.0,
        from_package: float = 0.0,
    ) -> DailyUsage:
        """Add usage minutes to a daily usage record."""
        daily_usage.minutes_used += minutes_used
        daily_usage.minutes_from_daily += from_daily
        daily_usage.minutes_from_bonus += from_bonus
        daily_usage.minutes_from_package += from_package
        daily_usage.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return daily_usage

    async def get_by_user_and_date(self, user_id: int, usage_date: date) -> Optional[DailyUsage]:
        """Get daily usage for a specific date."""
        result = await self.session.execute(
            select(DailyUsage).where(
                and_(
                    DailyUsage.user_id == user_id,
                    DailyUsage.date == usage_date,
                )
            )
        )
        return result.scalar_one_or_none()


class DeductionLogRepository:
    """Repository for DeductionLog model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        usage_id: int,
        source_type: str,
        minutes_deducted: float,
        source_id: Optional[int] = None,
    ) -> DeductionLog:
        """Create a deduction log entry."""
        log = DeductionLog(
            user_id=user_id,
            usage_id=usage_id,
            source_type=source_type,
            source_id=source_id,
            minutes_deducted=minutes_deducted,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_by_usage_id(self, usage_id: int) -> list[DeductionLog]:
        """Get all deduction logs for a usage record."""
        result = await self.session.execute(
            select(DeductionLog)
            .where(DeductionLog.usage_id == usage_id)
            .order_by(DeductionLog.created_at)
        )
        return list(result.scalars().all())


class PurchaseRepository:
    """Repository for Purchase model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        purchase_type: str,
        item_id: int,
        amount: float,
        currency: str,
        payment_provider: str,
        provider_transaction_id: Optional[str] = None,
    ) -> Purchase:
        """Create a purchase record."""
        purchase = Purchase(
            user_id=user_id,
            purchase_type=purchase_type,
            item_id=item_id,
            amount=amount,
            currency=currency,
            payment_provider=payment_provider,
            provider_transaction_id=provider_transaction_id,
            status=PurchaseStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(purchase)
        await self.session.flush()
        return purchase

    async def get_by_id(self, purchase_id: int) -> Optional[Purchase]:
        """Get purchase by ID."""
        result = await self.session.execute(select(Purchase).where(Purchase.id == purchase_id))
        return result.scalar_one_or_none()

    async def mark_completed(self, purchase: Purchase) -> Purchase:
        """Mark purchase as completed."""
        purchase.status = PurchaseStatus.COMPLETED
        purchase.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return purchase

    async def mark_failed(self, purchase: Purchase) -> Purchase:
        """Mark purchase as failed."""
        purchase.status = PurchaseStatus.FAILED
        purchase.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return purchase

    async def get_by_user_id(self, user_id: int, limit: int = 20) -> list[Purchase]:
        """Get purchases for a user (most recent first)."""
        result = await self.session.execute(
            select(Purchase)
            .where(Purchase.user_id == user_id)
            .order_by(Purchase.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_pending_purchase(
        self,
        user_id: int,
        purchase_type: str,
        item_id: int,
    ) -> Optional[Purchase]:
        """Find the most recent pending purchase by user, type, and item."""
        result = await self.session.execute(
            select(Purchase)
            .where(
                and_(
                    Purchase.user_id == user_id,
                    Purchase.purchase_type == purchase_type,
                    Purchase.item_id == item_id,
                    Purchase.status == PurchaseStatus.PENDING,
                )
            )
            .order_by(Purchase.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
