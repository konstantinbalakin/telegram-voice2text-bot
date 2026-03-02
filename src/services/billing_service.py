"""
Billing Service - core billing logic: limits, deductions, balances.
"""

import logging
import math
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Callable, Optional

from src.storage.billing_repositories import (
    BillingConditionRepository,
    SubscriptionRepository,
    UserMinuteBalanceRepository,
    DailyUsageRepository,
    DeductionLogRepository,
)
from src.storage.models import UserMinuteBalance

logger = logging.getLogger(__name__)

DEFAULT_DAILY_FREE_MINUTES = 10.0

# Type alias for session factory (e.g. database.get_session)
SessionFactory = Callable[..., Any]


class BillingService:
    """Core billing service: check limits, deduct minutes, get balances.

    Accepts either a session_factory (production) or pre-built repos (testing).
    When session_factory is provided, each method creates a fresh DB session.
    """

    def __init__(
        self,
        *,
        session_factory: Optional[SessionFactory] = None,
        condition_repo: Optional[BillingConditionRepository] = None,
        subscription_repo: Optional[SubscriptionRepository] = None,
        balance_repo: Optional[UserMinuteBalanceRepository] = None,
        daily_usage_repo: Optional[DailyUsageRepository] = None,
        deduction_log_repo: Optional[DeductionLogRepository] = None,
        billing_enabled: bool = True,
        warning_threshold: float = 0.8,
    ):
        self._session_factory = session_factory
        self._condition_repo = condition_repo
        self._subscription_repo = subscription_repo
        self._balance_repo = balance_repo
        self._daily_usage_repo = daily_usage_repo
        self._deduction_log_repo = deduction_log_repo
        self.billing_enabled = billing_enabled
        self.warning_threshold = warning_threshold

    @asynccontextmanager
    async def _repos(
        self,
    ) -> AsyncGenerator[
        tuple[
            BillingConditionRepository,
            SubscriptionRepository,
            UserMinuteBalanceRepository,
            DailyUsageRepository,
            DeductionLogRepository,
        ],
        None,
    ]:
        """Get repositories — per-request session or pre-built (tests)."""
        if self._session_factory:
            async with self._session_factory() as session:
                yield (
                    BillingConditionRepository(session),
                    SubscriptionRepository(session),
                    UserMinuteBalanceRepository(session),
                    DailyUsageRepository(session),
                    DeductionLogRepository(session),
                )
        else:
            assert self._condition_repo is not None
            assert self._subscription_repo is not None
            assert self._balance_repo is not None
            assert self._daily_usage_repo is not None
            assert self._deduction_log_repo is not None
            yield (
                self._condition_repo,
                self._subscription_repo,
                self._balance_repo,
                self._daily_usage_repo,
                self._deduction_log_repo,
            )

    @staticmethod
    def round_minutes(minutes: float) -> float:
        """Round up to tenths of a minute."""
        return math.ceil(minutes * 10) / 10

    async def get_user_daily_limit(self, user_id: int) -> float:
        """Get user's daily limit in minutes.

        Subscription replaces (not sums with) the free daily limit.
        """
        async with self._repos() as (
            condition_repo,
            subscription_repo,
            _balance_repo,
            _daily_usage_repo,
            _deduction_log_repo,
        ):
            # Check active subscription first
            active_sub = await subscription_repo.get_active_subscription(user_id=user_id)
            if active_sub:
                tier = await subscription_repo.get_tier_by_id(active_sub.tier_id)
                if tier:
                    return tier.daily_limit_minutes

            # Fall back to billing condition
            value = await condition_repo.get_effective_value(
                key="daily_free_minutes", user_id=user_id
            )
            if value is not None:
                return float(value)

            return DEFAULT_DAILY_FREE_MINUTES

    async def get_user_balance(self, user_id: int) -> dict:
        """Get full user balance breakdown."""
        async with self._repos() as (
            condition_repo,
            subscription_repo,
            balance_repo,
            daily_usage_repo,
            _deduction_log_repo,
        ):
            daily_limit = await self._get_daily_limit_with_repos(
                user_id, condition_repo, subscription_repo
            )

            daily_usage = await daily_usage_repo.get_by_user_and_date(
                user_id=user_id, usage_date=date.today()
            )
            daily_used = daily_usage.minutes_used if daily_usage else 0.0
            daily_remaining = max(0.0, daily_limit - daily_used)

            bonus_minutes = await balance_repo.get_total_minutes(
                user_id=user_id, balance_type="bonus"
            )
            package_minutes = await balance_repo.get_total_minutes(
                user_id=user_id, balance_type="package"
            )

            total_available = daily_remaining + bonus_minutes + package_minutes

            return {
                "daily_limit": daily_limit,
                "daily_used": daily_used,
                "daily_remaining": daily_remaining,
                "bonus_minutes": bonus_minutes,
                "package_minutes": package_minutes,
                "total_available": total_available,
            }

    async def check_can_transcribe(
        self, user_id: int, duration_minutes: float
    ) -> tuple[bool, Optional[str]]:
        """Check if user has enough minutes for transcription.

        Returns: (can_transcribe, reason_if_not)
        """
        if not self.billing_enabled:
            return True, None

        duration = self.round_minutes(duration_minutes)
        balance = await self.get_user_balance(user_id=user_id)

        if balance["total_available"] >= duration:
            return True, None

        return False, (
            f"Недостаточно минут. Требуется: {duration:.1f} мин, "
            f"доступно: {balance['total_available']:.1f} мин."
        )

    async def deduct_minutes(self, user_id: int, usage_id: int, duration_minutes: float) -> dict:
        """Deduct minutes from user's sources: daily -> bonus -> package.

        Returns breakdown of deduction by source.
        """
        if not self.billing_enabled:
            return {"from_daily": 0.0, "from_bonus": 0.0, "from_package": 0.0}

        duration = self.round_minutes(duration_minutes)
        remaining = duration

        async with self._repos() as (
            condition_repo,
            subscription_repo,
            balance_repo,
            daily_usage_repo,
            deduction_log_repo,
        ):
            daily_limit = await self._get_daily_limit_with_repos(
                user_id, condition_repo, subscription_repo
            )
            daily_usage, _ = await daily_usage_repo.get_or_create(
                user_id=user_id, usage_date=date.today()
            )
            daily_available = max(0.0, daily_limit - daily_usage.minutes_used)

            # 1. Deduct from daily
            from_daily = min(remaining, daily_available)
            remaining -= from_daily

            from_bonus = 0.0
            from_package = 0.0

            # 2. Deduct from bonus, then package
            if remaining > 0:
                balances = await balance_repo.get_active_balances(user_id=user_id)
                for balance in balances:
                    if remaining <= 0:
                        break
                    deduct = min(remaining, balance.minutes_remaining)
                    if deduct > 0:
                        await balance_repo.deduct_minutes(balance_id=balance.id, minutes=deduct)
                        await deduction_log_repo.create(
                            user_id=user_id,
                            usage_id=usage_id,
                            source_type=balance.balance_type,
                            source_id=balance.id,
                            minutes_deducted=deduct,
                        )
                        if balance.balance_type == "bonus":
                            from_bonus += deduct
                        else:
                            from_package += deduct
                        remaining -= deduct

            # Log deduction shortfall if minutes couldn't be fully covered
            if remaining > 0:
                logger.warning(
                    f"Deduction shortfall for user {user_id}: "
                    f"requested={duration:.1f}, unfunded={remaining:.1f}"
                )

            # Log daily deduction
            if from_daily > 0:
                await deduction_log_repo.create(
                    user_id=user_id,
                    usage_id=usage_id,
                    source_type="daily",
                    minutes_deducted=from_daily,
                )

            # Update daily usage record
            await daily_usage_repo.add_usage(
                daily_usage=daily_usage,
                minutes_used=duration,
                from_daily=from_daily,
                from_bonus=from_bonus,
                from_package=from_package,
            )

        logger.info(
            f"Deducted {duration:.1f} min for user {user_id}: "
            f"daily={from_daily:.1f}, bonus={from_bonus:.1f}, package={from_package:.1f}"
        )

        return {
            "from_daily": from_daily,
            "from_bonus": from_bonus,
            "from_package": from_package,
        }

    async def should_warn_limit(self, user_id: int) -> bool:
        """Check if user should be warned about approaching daily limit."""
        async with self._repos() as (
            condition_repo,
            subscription_repo,
            _balance_repo,
            daily_usage_repo,
            _deduction_log_repo,
        ):
            daily_limit = await self._get_daily_limit_with_repos(
                user_id, condition_repo, subscription_repo
            )
            if daily_limit <= 0:
                return False

            daily_usage = await daily_usage_repo.get_by_user_and_date(
                user_id=user_id, usage_date=date.today()
            )
            daily_used = daily_usage.minutes_used if daily_usage else 0.0

            return (daily_used / daily_limit) >= self.warning_threshold

    async def grant_welcome_bonus(self, user_id: int) -> Optional[UserMinuteBalance]:
        """Grant welcome bonus to new user. Returns None if already granted or billing disabled."""
        if not self.billing_enabled:
            return None

        async with self._repos() as (
            condition_repo,
            _subscription_repo,
            balance_repo,
            _daily_usage_repo,
            _deduction_log_repo,
        ):
            already_granted = await balance_repo.has_welcome_bonus(user_id=user_id)
            if already_granted:
                logger.info(f"Welcome bonus already granted for user {user_id}")
                return None

            # Get bonus amount from billing conditions
            bonus_minutes_str = await condition_repo.get_effective_value(
                key="welcome_bonus_minutes", user_id=user_id
            )
            bonus_minutes = float(bonus_minutes_str) if bonus_minutes_str else 60.0

            # Get bonus expiry days
            bonus_days_str = await condition_repo.get_effective_value(
                key="welcome_bonus_days", user_id=user_id
            )
            expires_at: Optional[datetime] = None
            if bonus_days_str is not None:
                expires_at = datetime.now(timezone.utc) + timedelta(days=int(bonus_days_str))

            balance = await balance_repo.create(
                user_id=user_id,
                balance_type="bonus",
                minutes_remaining=bonus_minutes,
                expires_at=expires_at,
                source_description="Welcome bonus",
            )

            logger.info(
                f"Granted welcome bonus {bonus_minutes:.1f} min to user {user_id}, "
                f"expires_at={expires_at}"
            )
            return balance

    async def grant_grace_period(self, user_id: int, minutes: float = 60.0) -> UserMinuteBalance:
        """Grant grace period bonus (perpetual) to existing user."""
        async with self._repos() as (
            _condition_repo,
            _subscription_repo,
            balance_repo,
            _daily_usage_repo,
            _deduction_log_repo,
        ):
            balance = await balance_repo.create(
                user_id=user_id,
                balance_type="bonus",
                minutes_remaining=minutes,
                expires_at=None,
                source_description="Grace period bonus",
            )

        logger.info(f"Granted grace period {minutes:.1f} min to user {user_id}")
        return balance

    @staticmethod
    async def _get_daily_limit_with_repos(
        user_id: int,
        condition_repo: BillingConditionRepository,
        subscription_repo: SubscriptionRepository,
    ) -> float:
        """Internal helper: get daily limit using provided repos."""
        active_sub = await subscription_repo.get_active_subscription(user_id=user_id)
        if active_sub:
            tier = await subscription_repo.get_tier_by_id(active_sub.tier_id)
            if tier:
                return tier.daily_limit_minutes

        value = await condition_repo.get_effective_value(
            key="daily_free_minutes", user_id=user_id
        )
        if value is not None:
            return float(value)

        return DEFAULT_DAILY_FREE_MINUTES
