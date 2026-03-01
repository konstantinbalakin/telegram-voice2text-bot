"""
Billing Service - core billing logic: limits, deductions, balances.
"""

import logging
import math
from datetime import date
from typing import Optional

from src.storage.billing_repositories import (
    BillingConditionRepository,
    SubscriptionRepository,
    UserMinuteBalanceRepository,
    DailyUsageRepository,
    DeductionLogRepository,
)

logger = logging.getLogger(__name__)

DEFAULT_DAILY_FREE_MINUTES = 10.0


class BillingService:
    """Core billing service: check limits, deduct minutes, get balances."""

    def __init__(
        self,
        condition_repo: BillingConditionRepository,
        subscription_repo: SubscriptionRepository,
        balance_repo: UserMinuteBalanceRepository,
        daily_usage_repo: DailyUsageRepository,
        deduction_log_repo: DeductionLogRepository,
        billing_enabled: bool = True,
        warning_threshold: float = 0.8,
    ):
        self.condition_repo = condition_repo
        self.subscription_repo = subscription_repo
        self.balance_repo = balance_repo
        self.daily_usage_repo = daily_usage_repo
        self.deduction_log_repo = deduction_log_repo
        self.billing_enabled = billing_enabled
        self.warning_threshold = warning_threshold

    @staticmethod
    def round_minutes(minutes: float) -> float:
        """Round up to tenths of a minute."""
        return math.ceil(minutes * 10) / 10

    async def get_user_daily_limit(self, user_id: int) -> float:
        """Get user's daily limit in minutes.

        Subscription replaces (not sums with) the free daily limit.
        """
        # Check active subscription first
        active_sub = await self.subscription_repo.get_active_subscription(user_id=user_id)
        if active_sub:
            tier = await self.subscription_repo.get_tier_by_id(active_sub.tier_id)
            if tier:
                return tier.daily_limit_minutes

        # Fall back to billing condition
        value = await self.condition_repo.get_effective_value(
            key="daily_free_minutes", user_id=user_id
        )
        if value is not None:
            return float(value)

        return DEFAULT_DAILY_FREE_MINUTES

    async def get_user_balance(self, user_id: int) -> dict:
        """Get full user balance breakdown."""
        daily_limit = await self.get_user_daily_limit(user_id=user_id)

        daily_usage = await self.daily_usage_repo.get_by_user_and_date(
            user_id=user_id, usage_date=date.today()
        )
        daily_used = daily_usage.minutes_used if daily_usage else 0.0
        daily_remaining = max(0.0, daily_limit - daily_used)

        bonus_minutes = await self.balance_repo.get_total_minutes(
            user_id=user_id, balance_type="bonus"
        )
        package_minutes = await self.balance_repo.get_total_minutes(
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
        """Deduct minutes from user's sources: daily → bonus → package.

        Returns breakdown of deduction by source.
        """
        if not self.billing_enabled:
            return {"from_daily": 0.0, "from_bonus": 0.0, "from_package": 0.0}

        duration = self.round_minutes(duration_minutes)
        remaining = duration

        daily_limit = await self.get_user_daily_limit(user_id=user_id)
        daily_usage, _ = await self.daily_usage_repo.get_or_create(
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
            balances = await self.balance_repo.get_active_balances(user_id=user_id)
            for balance in balances:
                if remaining <= 0:
                    break
                deduct = min(remaining, balance.minutes_remaining)
                if deduct > 0:
                    await self.balance_repo.deduct_minutes(balance_id=balance.id, minutes=deduct)
                    await self.deduction_log_repo.create(
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

        # Log daily deduction
        if from_daily > 0:
            await self.deduction_log_repo.create(
                user_id=user_id,
                usage_id=usage_id,
                source_type="daily",
                minutes_deducted=from_daily,
            )

        # Update daily usage record
        await self.daily_usage_repo.add_usage(
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
        daily_limit = await self.get_user_daily_limit(user_id=user_id)
        if daily_limit <= 0:
            return False

        daily_usage = await self.daily_usage_repo.get_by_user_and_date(
            user_id=user_id, usage_date=date.today()
        )
        daily_used = daily_usage.minutes_used if daily_usage else 0.0

        return (daily_used / daily_limit) >= self.warning_threshold
