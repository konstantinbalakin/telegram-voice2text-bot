"""Tests for billing enum types."""

from enum import Enum

from src.services.payments.base import (
    BalanceType,
    Currency,
    DeductionSource,
    PaymentStatus,
    PaymentType,
    PurchaseStatus,
    SubscriptionPeriod,
    SubscriptionStatus,
)


class TestCurrencyEnum:
    """Tests for Currency enum."""

    def test_currency_values(self) -> None:
        assert Currency.USD == "USD"
        assert Currency.RUB == "RUB"
        assert Currency.XTR == "XTR"

    def test_currency_is_str_enum(self) -> None:
        assert isinstance(Currency.USD, str)
        assert isinstance(Currency.USD, Enum)

    def test_currency_from_string(self) -> None:
        assert Currency("USD") == Currency.USD
        assert Currency("RUB") == Currency.RUB
        assert Currency("XTR") == Currency.XTR

    def test_currency_members_count(self) -> None:
        assert len(Currency) == 3


class TestPurchaseStatusEnum:
    """Tests for PurchaseStatus enum."""

    def test_purchase_status_values(self) -> None:
        assert PurchaseStatus.PENDING == "pending"
        assert PurchaseStatus.COMPLETED == "completed"
        assert PurchaseStatus.FAILED == "failed"
        assert PurchaseStatus.REFUNDED == "refunded"

    def test_purchase_status_is_str_enum(self) -> None:
        assert isinstance(PurchaseStatus.PENDING, str)
        assert isinstance(PurchaseStatus.PENDING, Enum)

    def test_purchase_status_from_string(self) -> None:
        assert PurchaseStatus("pending") == PurchaseStatus.PENDING
        assert PurchaseStatus("completed") == PurchaseStatus.COMPLETED

    def test_purchase_status_members_count(self) -> None:
        assert len(PurchaseStatus) == 4


class TestExistingEnumsUnchanged:
    """Verify existing enums still work correctly after additions."""

    def test_payment_type(self) -> None:
        assert PaymentType.PACKAGE == "package"
        assert PaymentType.SUBSCRIPTION == "subscription"

    def test_payment_status(self) -> None:
        assert PaymentStatus.PENDING == "pending"
        assert PaymentStatus.COMPLETED == "completed"
        assert PaymentStatus.FAILED == "failed"
        assert PaymentStatus.CANCELLED == "cancelled"

    def test_subscription_status(self) -> None:
        assert SubscriptionStatus.ACTIVE == "active"
        assert SubscriptionStatus.EXPIRED == "expired"
        assert SubscriptionStatus.CANCELLED == "cancelled"

    def test_subscription_period_values(self) -> None:
        assert SubscriptionPeriod.WEEK == "week"
        assert SubscriptionPeriod.MONTH == "month"
        assert SubscriptionPeriod.YEAR == "year"

    def test_subscription_period_days(self) -> None:
        assert SubscriptionPeriod.WEEK.days == 7
        assert SubscriptionPeriod.MONTH.days == 30
        assert SubscriptionPeriod.YEAR.days == 365

    def test_balance_type(self) -> None:
        assert BalanceType.BONUS == "bonus"
        assert BalanceType.PACKAGE == "package"

    def test_deduction_source(self) -> None:
        assert DeductionSource.DAILY == "daily"
        assert DeductionSource.BONUS == "bonus"
        assert DeductionSource.PACKAGE == "package"
