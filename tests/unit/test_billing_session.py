"""
Tests for per-request session pattern in billing services (Task 1.2).

Verifies that each service method creates a fresh DB session via session_factory,
preventing use-after-free bugs from closed sessions.
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.billing_service import BillingService
from src.services.subscription_service import SubscriptionService
from src.services.payments.payment_service import PaymentService


# === Helpers ===


def _counting_session_factory():
    """Create a session factory that counts calls."""
    call_count = 0

    @asynccontextmanager
    async def factory():
        nonlocal call_count
        call_count += 1
        yield MagicMock()

    factory.call_count = lambda: call_count  # type: ignore[attr-defined]
    return factory


# =============================================================================
# BillingService: per-request session tests
# =============================================================================


class TestBillingServicePerRequestSession:
    """Verify BillingService creates a fresh session per method call."""

    @pytest.mark.asyncio
    async def test_session_factory_accepted(self) -> None:
        """BillingService can be constructed with session_factory."""
        factory = _counting_session_factory()
        service = BillingService(session_factory=factory, billing_enabled=True)
        assert service._session_factory is factory

    @pytest.mark.asyncio
    @patch("src.services.billing_service.SubscriptionRepository")
    @patch("src.services.billing_service.BillingConditionRepository")
    async def test_each_call_creates_new_session(
        self, mock_cond_cls: MagicMock, mock_sub_cls: MagicMock
    ) -> None:
        """Each method call must create a new session (not reuse a shared one)."""
        factory = _counting_session_factory()

        # Mock repo returns
        mock_sub_cls.return_value.get_active_subscription = AsyncMock(return_value=None)
        mock_sub_cls.return_value.get_active_subscription_with_tier = AsyncMock(return_value=None)
        mock_cond_cls.return_value.get_effective_value = AsyncMock(return_value="10")

        service = BillingService(session_factory=factory, billing_enabled=True)

        await service.get_user_daily_limit(user_id=1)
        assert factory.call_count() == 1  # type: ignore[attr-defined]

        await service.get_user_daily_limit(user_id=2)
        assert factory.call_count() == 2  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("src.services.billing_service.DeductionLogRepository")
    @patch("src.services.billing_service.DailyUsageRepository")
    @patch("src.services.billing_service.UserMinuteBalanceRepository")
    @patch("src.services.billing_service.SubscriptionRepository")
    @patch("src.services.billing_service.BillingConditionRepository")
    async def test_get_user_balance_uses_session_factory(
        self,
        mock_cond_cls: MagicMock,
        mock_sub_cls: MagicMock,
        mock_bal_cls: MagicMock,
        mock_daily_cls: MagicMock,
        mock_ded_cls: MagicMock,
    ) -> None:
        """get_user_balance creates repos from session_factory session."""
        factory = _counting_session_factory()

        mock_sub_cls.return_value.get_active_subscription = AsyncMock(return_value=None)
        mock_sub_cls.return_value.get_active_subscription_with_tier = AsyncMock(return_value=None)
        mock_cond_cls.return_value.get_effective_value = AsyncMock(return_value="10")
        mock_daily_cls.return_value.get_by_user_and_date = AsyncMock(return_value=None)
        mock_bal_cls.return_value.get_total_minutes = AsyncMock(return_value=0.0)
        mock_bal_cls.return_value.get_nearest_expires_at = AsyncMock(return_value=None)

        service = BillingService(session_factory=factory, billing_enabled=True)
        balance = await service.get_user_balance(user_id=1)

        assert factory.call_count() == 1  # type: ignore[attr-defined]
        assert balance.daily_limit == 10.0
        assert balance.total_available == 10.0

    @pytest.mark.asyncio
    @patch("src.services.billing_service.DeductionLogRepository")
    @patch("src.services.billing_service.DailyUsageRepository")
    @patch("src.services.billing_service.UserMinuteBalanceRepository")
    @patch("src.services.billing_service.SubscriptionRepository")
    @patch("src.services.billing_service.BillingConditionRepository")
    async def test_deduct_minutes_uses_session_factory(
        self,
        mock_cond_cls: MagicMock,
        mock_sub_cls: MagicMock,
        mock_bal_cls: MagicMock,
        mock_daily_cls: MagicMock,
        mock_ded_cls: MagicMock,
    ) -> None:
        """deduct_minutes creates repos from session_factory session."""
        factory = _counting_session_factory()

        mock_sub_cls.return_value.get_active_subscription = AsyncMock(return_value=None)
        mock_sub_cls.return_value.get_active_subscription_with_tier = AsyncMock(return_value=None)
        mock_cond_cls.return_value.get_effective_value = AsyncMock(return_value="10")

        mock_daily = MagicMock()
        mock_daily.minutes_used = 0.0
        mock_daily_cls.return_value.get_or_create = AsyncMock(return_value=(mock_daily, False))
        mock_daily_cls.return_value.add_usage = AsyncMock()
        mock_bal_cls.return_value.get_active_balances = AsyncMock(return_value=[])
        mock_ded_cls.return_value.create = AsyncMock()

        service = BillingService(session_factory=factory, billing_enabled=True)
        result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=3.0)

        assert factory.call_count() == 1  # type: ignore[attr-defined]
        assert result["from_daily"] == 3.0


# =============================================================================
# SubscriptionService: per-request session tests
# =============================================================================


class TestSubscriptionServicePerRequestSession:
    """Verify SubscriptionService creates a fresh session per method call."""

    @pytest.mark.asyncio
    async def test_session_factory_accepted(self) -> None:
        """SubscriptionService can be constructed with session_factory."""
        factory = _counting_session_factory()
        service = SubscriptionService(session_factory=factory)
        assert service._session_factory is factory

    @pytest.mark.asyncio
    @patch("src.services.subscription_service.SubscriptionRepository")
    async def test_get_available_tiers_uses_session(self, mock_sub_cls: MagicMock) -> None:
        """get_available_tiers creates a fresh session."""
        factory = _counting_session_factory()
        mock_sub_cls.return_value.get_active_tiers = AsyncMock(return_value=[])

        service = SubscriptionService(session_factory=factory)
        tiers = await service.get_available_tiers()

        assert factory.call_count() == 1  # type: ignore[attr-defined]
        assert tiers == []

    @pytest.mark.asyncio
    @patch("src.services.subscription_service.SubscriptionRepository")
    async def test_each_call_creates_new_session(self, mock_sub_cls: MagicMock) -> None:
        """Each method call creates a separate session."""
        factory = _counting_session_factory()
        mock_sub_cls.return_value.get_active_tiers = AsyncMock(return_value=[])
        mock_sub_cls.return_value.get_active_subscription = AsyncMock(return_value=None)

        service = SubscriptionService(session_factory=factory)
        await service.get_available_tiers()
        await service.get_active_subscription(user_id=1)

        assert factory.call_count() == 2  # type: ignore[attr-defined]


# =============================================================================
# PaymentService: per-request session tests
# =============================================================================


class TestPaymentServicePerRequestSession:
    """Verify PaymentService creates a fresh session per method call."""

    @pytest.mark.asyncio
    async def test_session_factory_accepted(self) -> None:
        """PaymentService can be constructed with session_factory."""
        factory = _counting_session_factory()
        service = PaymentService(session_factory=factory)
        assert service._session_factory is factory

    @pytest.mark.asyncio
    @patch("src.services.payments.payment_service.MinutePackageRepository")
    @patch("src.services.payments.payment_service.UserMinuteBalanceRepository")
    @patch("src.services.payments.payment_service.SubscriptionRepository")
    @patch("src.services.payments.payment_service.PurchaseRepository")
    async def test_get_active_packages_uses_session(
        self,
        mock_purchase_cls: MagicMock,
        mock_sub_cls: MagicMock,
        mock_bal_cls: MagicMock,
        mock_pkg_cls: MagicMock,
    ) -> None:
        """get_active_packages creates a fresh session."""
        factory = _counting_session_factory()
        mock_pkg_cls.return_value.get_effective_packages = AsyncMock(return_value=[])

        service = PaymentService(session_factory=factory)
        packages = await service.get_active_packages()

        assert factory.call_count() == 1  # type: ignore[attr-defined]
        assert packages == []
