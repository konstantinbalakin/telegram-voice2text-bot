"""
Tests for YooKassa async wrapper and email handling (Tasks 1.5-1.7).

Verifies that sync YooKassa SDK calls are wrapped in asyncio.to_thread()
and that hardcoded email is replaced with configurable customer_email.
"""

import sys
import pytest
from unittest.mock import MagicMock, patch

from src.services.payments.base import PaymentRequest, PaymentType


@pytest.fixture(autouse=True)
def mock_yookassa_module() -> None:
    """Mock the yookassa module so imports succeed without the real package."""
    mock_module = MagicMock()
    sys.modules["yookassa"] = mock_module
    yield
    sys.modules.pop("yookassa", None)


def _make_provider() -> "YooKassaProvider":
    """Create a YooKassaProvider bypassing __init__ yookassa import."""
    from src.services.payments.yookassa_provider import YooKassaProvider

    provider = YooKassaProvider.__new__(YooKassaProvider)
    provider.shop_id = "test_shop"
    provider.secret_key = "test_secret"
    provider.return_url = "https://return.example.com"
    provider._configured = True
    return provider


# =============================================================================
# Task 1.5/1.6: asyncio.to_thread wrapping
# =============================================================================


class TestYooKassaAsyncWrapper:
    """Verify YooKassa sync calls are wrapped in asyncio.to_thread."""

    @pytest.mark.asyncio
    @patch("src.services.payments.yookassa_provider.asyncio.to_thread")
    async def test_create_payment_uses_to_thread(self, mock_to_thread: MagicMock) -> None:
        """create_payment wraps Payment.create in asyncio.to_thread."""
        mock_payment = MagicMock()
        mock_payment.id = "pay_123"
        mock_payment.confirmation = MagicMock()
        mock_payment.confirmation.confirmation_url = "https://pay.example.com"
        mock_to_thread.return_value = mock_payment

        provider = _make_provider()

        request = PaymentRequest(
            user_id=1,
            payment_type=PaymentType.PACKAGE,
            item_id=1,
            amount=100.0,
            currency="RUB",
            description="Test payment",
            customer_email="test@example.com",
        )

        result = await provider.create_payment(request)

        assert result.success is True
        assert result.provider_transaction_id == "pay_123"
        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.payments.yookassa_provider.asyncio.to_thread")
    async def test_verify_payment_uses_to_thread(self, mock_to_thread: MagicMock) -> None:
        """verify_payment wraps Payment.find_one in asyncio.to_thread."""
        mock_payment = MagicMock()
        mock_payment.status = "succeeded"
        mock_to_thread.return_value = mock_payment

        provider = _make_provider()

        result = await provider.verify_payment("tx_123")

        assert result.success is True
        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_payment_not_configured(self) -> None:
        """create_payment returns error when not configured."""
        provider = _make_provider()
        provider._configured = False

        request = PaymentRequest(
            user_id=1,
            payment_type=PaymentType.PACKAGE,
            item_id=1,
            amount=100.0,
            currency="RUB",
            description="Test",
        )

        result = await provider.create_payment(request)
        assert result.success is False
        assert result.error_message is not None
        assert "not configured" in result.error_message


# =============================================================================
# Task 1.7: customer_email instead of hardcoded email
# =============================================================================


class TestYooKassaCustomerEmail:
    """Verify email is taken from PaymentRequest, not hardcoded."""

    @pytest.mark.asyncio
    @patch("src.services.payments.yookassa_provider.asyncio.to_thread")
    async def test_receipt_includes_customer_email(self, mock_to_thread: MagicMock) -> None:
        """Receipt uses customer_email from PaymentRequest."""
        mock_payment = MagicMock()
        mock_payment.id = "pay_456"
        mock_payment.confirmation = None
        mock_to_thread.return_value = mock_payment

        provider = _make_provider()

        request = PaymentRequest(
            user_id=1,
            payment_type=PaymentType.PACKAGE,
            item_id=1,
            amount=100.0,
            currency="RUB",
            description="Test",
            customer_email="real@customer.com",
        )

        await provider.create_payment(request)

        # Inspect the payment_data passed to Payment.create via to_thread
        call_args = mock_to_thread.call_args
        payment_data = call_args[0][1]  # Second positional arg (first is Payment.create)
        assert "receipt" in payment_data
        assert payment_data["receipt"]["customer"]["email"] == "real@customer.com"

    @pytest.mark.asyncio
    @patch("src.services.payments.yookassa_provider.asyncio.to_thread")
    async def test_no_receipt_without_email(self, mock_to_thread: MagicMock) -> None:
        """No receipt included when customer_email is None."""
        mock_payment = MagicMock()
        mock_payment.id = "pay_789"
        mock_payment.confirmation = None
        mock_to_thread.return_value = mock_payment

        provider = _make_provider()

        request = PaymentRequest(
            user_id=1,
            payment_type=PaymentType.PACKAGE,
            item_id=1,
            amount=100.0,
            currency="RUB",
            description="Test",
            customer_email=None,
        )

        await provider.create_payment(request)

        call_args = mock_to_thread.call_args
        payment_data = call_args[0][1]
        assert "receipt" not in payment_data

    def test_payment_request_email_optional(self) -> None:
        """PaymentRequest customer_email defaults to None."""
        request = PaymentRequest(
            user_id=1,
            payment_type=PaymentType.PACKAGE,
            item_id=1,
            amount=100.0,
            currency="RUB",
            description="Test",
        )
        assert request.customer_email is None
