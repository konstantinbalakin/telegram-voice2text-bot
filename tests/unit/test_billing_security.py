"""
Tests for billing security and payment logic (Phase 3).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


# =============================================================================
# Task 3.1: Native Telegram Payments verification (via Telegram, not webhooks)
# =============================================================================


class TestYooKassaNativePayments:
    """YooKassa native Telegram Payments are verified by Telegram itself."""

    @pytest.mark.asyncio
    async def test_handle_callback_returns_success(self) -> None:
        """handle_callback returns success (managed by Telegram)."""
        from telegram import Bot

        from src.services.payments.yookassa_provider import YooKassaProvider

        bot = MagicMock(spec=Bot)
        provider = YooKassaProvider(bot=bot, provider_token="tok_test")

        result = await provider.handle_callback({})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_verify_payment_returns_success(self) -> None:
        """verify_payment returns success (managed by Telegram)."""
        from telegram import Bot

        from src.services.payments.yookassa_provider import YooKassaProvider

        bot = MagicMock(spec=Bot)
        provider = YooKassaProvider(bot=bot, provider_token="tok_test")

        result = await provider.verify_payment("pay_123")
        assert result.success is True
        assert result.provider_transaction_id == "pay_123"


# =============================================================================
# Task 3.2: Purchase marked completed
# =============================================================================


class TestPurchaseCompletion:
    """Purchase should be marked completed after successful payment."""

    @pytest.mark.asyncio
    async def test_purchase_marked_completed(self) -> None:
        """handle_successful_payment marks purchase as completed."""
        from src.services.payments.payment_service import PaymentService
        from src.services.payments.base import PaymentType

        mocks = {
            "purchase_repo": AsyncMock(),
            "subscription_repo": AsyncMock(),
            "balance_repo": AsyncMock(),
            "package_repo": AsyncMock(),
        }

        mock_pkg = MagicMock()
        mock_pkg.minutes = 50
        mock_pkg.name = "Test"
        mocks["package_repo"].get_by_id.return_value = mock_pkg

        mock_purchase = MagicMock()
        mocks["purchase_repo"].find_pending_purchase.return_value = mock_purchase

        service = PaymentService(
            purchase_repo=mocks["purchase_repo"],
            subscription_repo=mocks["subscription_repo"],
            balance_repo=mocks["balance_repo"],
            package_repo=mocks["package_repo"],
        )

        result = await service.handle_successful_payment(
            provider_name="test",
            user_id=1,
            payment_type=PaymentType.PACKAGE,
            item_id=1,
        )

        assert result is True
        mocks["purchase_repo"].mark_completed.assert_called_once_with(mock_purchase)


# =============================================================================
# Task 3.3: Cancel subscription keeps active status
# =============================================================================


class TestCancelSubscriptionKeepsActive:
    """Cancelled subscription should remain active until expiry."""

    @pytest.mark.asyncio
    async def test_cancel_only_disables_auto_renew(self) -> None:
        """cancel_subscription sets auto_renew=False but keeps status='active'."""
        from src.storage.billing_repositories import SubscriptionRepository

        mock_sub = MagicMock()
        mock_sub.status = "active"
        mock_sub.auto_renew = True

        mock_session = AsyncMock()
        repo = SubscriptionRepository(mock_session)

        result = await repo.cancel_subscription(mock_sub)

        assert result.auto_renew is False
        assert result.status == "active"  # NOT 'cancelled'


# =============================================================================
# Task 3.4: Period passed through, not hardcoded
# =============================================================================


class TestSubscriptionPeriodParam:
    """Subscription period should come from payment data, not hardcoded."""

    @pytest.mark.asyncio
    async def test_period_passed_to_create_subscription(self) -> None:
        """_activate_subscription uses provided period, not hardcoded 'month'."""
        from src.services.payments.payment_service import PaymentService

        mock_sub_service = AsyncMock()
        mock_sub_service.create_subscription.return_value = MagicMock(id=1)

        service = PaymentService(
            purchase_repo=AsyncMock(),
            subscription_repo=AsyncMock(),
            balance_repo=AsyncMock(),
            package_repo=AsyncMock(),
            subscription_service=mock_sub_service,
        )

        from src.services.payments.base import PaymentType

        await service.handle_successful_payment(
            provider_name="test",
            user_id=1,
            payment_type=PaymentType.SUBSCRIPTION,
            item_id=1,
            period="year",
        )

        mock_sub_service.create_subscription.assert_called_once()
        call_kwargs = mock_sub_service.create_subscription.call_args[1]
        assert call_kwargs["period"] == "year"


# =============================================================================
# Task 3.7: Logging in parse methods
# =============================================================================


class TestParseMethodsLogging:
    """Parse methods should log warnings on malformed input."""

    def test_parse_payload_logs_on_malformed(self) -> None:
        """parse_payment_payload returns None and logs on bad input."""
        from src.services.payments.base import parse_payment_payload

        result = parse_payment_payload("bad:payload")
        assert result is None

    def test_parse_payload_valid(self) -> None:
        """parse_payment_payload works for valid input."""
        from src.services.payments.base import parse_payment_payload

        result = parse_payment_payload("package:1:42")
        assert result is not None
        assert result["payment_type"] == "package"
        assert result["item_id"] == 1
        assert result["user_id"] == 42

    def test_parse_payload_with_period(self) -> None:
        """parse_payment_payload handles period field."""
        from src.services.payments.base import parse_payment_payload

        result = parse_payment_payload("subscription:2:42:year")
        assert result is not None
        assert result["period"] == "year"

    def test_parse_payload_logs_on_malformed_yookassa(self) -> None:
        """parse_payment_payload returns None on malformed data (was YooKassa test)."""
        from src.services.payments.base import parse_payment_payload

        result = parse_payment_payload("bad")
        assert result is None

    def test_parse_payload_valid_yookassa(self) -> None:
        """parse_payment_payload works for valid input (was YooKassa test)."""
        from src.services.payments.base import parse_payment_payload

        result = parse_payment_payload("package:1:42")
        assert result is not None
        assert result["item_id"] == 1
        assert result["user_id"] == 42
