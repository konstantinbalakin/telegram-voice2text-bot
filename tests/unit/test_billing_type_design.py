"""
Tests for Phase 6: Type design и миграции.

Task 6.1: Денежные поля — Integer (копейки).
Task 6.2: CHECK constraints.
Task 6.3: UserBalance computed properties.
Task 6.9: Currency enum usage.
"""

import pytest

from src.services.payments.base import UserBalance, Currency


# =============================================================================
# Task 6.3: UserBalance — computed properties
# =============================================================================


class TestUserBalanceComputedProperties:
    """UserBalance.daily_remaining and total_available must be computed properties."""

    def test_daily_remaining_is_computed(self) -> None:
        """daily_remaining = max(0, daily_limit - daily_used)."""
        balance = UserBalance(
            daily_limit=10.0,
            daily_used=3.0,
            bonus_minutes=0.0,
            package_minutes=0.0,
        )
        assert balance.daily_remaining == 7.0

    def test_daily_remaining_cannot_be_negative(self) -> None:
        """daily_remaining is clamped to 0.0."""
        balance = UserBalance(
            daily_limit=10.0,
            daily_used=15.0,
            bonus_minutes=0.0,
            package_minutes=0.0,
        )
        assert balance.daily_remaining == 0.0

    def test_total_available_is_computed(self) -> None:
        """total_available = daily_remaining + bonus_minutes + package_minutes."""
        balance = UserBalance(
            daily_limit=10.0,
            daily_used=3.0,
            bonus_minutes=20.0,
            package_minutes=50.0,
        )
        assert balance.total_available == 77.0  # 7 + 20 + 50

    def test_frozen_dataclass(self) -> None:
        """UserBalance should be frozen (immutable)."""
        balance = UserBalance(
            daily_limit=10.0,
            daily_used=0.0,
            bonus_minutes=0.0,
            package_minutes=0.0,
        )
        with pytest.raises(AttributeError):
            balance.daily_limit = 20.0  # type: ignore[misc]

    def test_post_init_validates_negative_daily_limit(self) -> None:
        """UserBalance rejects negative daily_limit."""
        with pytest.raises(ValueError):
            UserBalance(
                daily_limit=-1.0,
                daily_used=0.0,
                bonus_minutes=0.0,
                package_minutes=0.0,
            )

    def test_post_init_validates_negative_daily_used(self) -> None:
        """UserBalance rejects negative daily_used."""
        with pytest.raises(ValueError):
            UserBalance(
                daily_limit=10.0,
                daily_used=-1.0,
                bonus_minutes=0.0,
                package_minutes=0.0,
            )

    def test_post_init_validates_negative_bonus(self) -> None:
        """UserBalance rejects negative bonus_minutes."""
        with pytest.raises(ValueError):
            UserBalance(
                daily_limit=10.0,
                daily_used=0.0,
                bonus_minutes=-5.0,
                package_minutes=0.0,
            )


# =============================================================================
# Task 6.9: Currency enum
# =============================================================================


class TestCurrencyEnum:
    """Currency enum values are correct."""

    def test_currency_values(self) -> None:
        assert Currency.RUB == "RUB"
        assert Currency.USD == "USD"
        assert Currency.XTR == "XTR"
