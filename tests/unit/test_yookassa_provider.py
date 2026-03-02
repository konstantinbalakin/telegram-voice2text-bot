"""
Tests for YooKassaProvider (Phase 9)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.payments.base import PaymentRequest, PaymentType
from src.services.payments.yookassa_provider import YooKassaProvider


# =============================================================================
# Provider basics
# =============================================================================


def test_provider_name():
    """Test provider name is yookassa."""
    # Create without SDK (will log warning but not fail)
    provider = YooKassaProvider(shop_id="test", secret_key="test")
    assert provider.provider_name == "yookassa"


# =============================================================================
# create_payment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_payment_not_configured():
    """Test payment creation when SDK not installed."""
    provider = YooKassaProvider(shop_id="test", secret_key="test")
    # _configured will be False since yookassa package is not installed

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=149.0,
        currency="RUB",
        description="50 minutes",
    )

    result = await provider.create_payment(request)
    assert result.success is False
    assert "not configured" in result.error_message


@pytest.mark.asyncio
async def test_create_payment_with_mock_sdk():
    """Test payment creation with mocked YooKassa SDK."""
    provider = YooKassaProvider(shop_id="test", secret_key="test")
    provider._configured = True  # Force configured

    mock_payment = MagicMock()
    mock_payment.id = "pay_123"
    mock_payment.confirmation = MagicMock()
    mock_payment.confirmation.confirmation_url = "https://yookassa.ru/pay/123"

    with patch(
        "src.services.payments.yookassa_provider.Payment",
        create=True,
    ):
        # Patch the import inside create_payment
        import sys

        mock_yookassa = MagicMock()
        mock_yookassa.Payment = MagicMock()
        mock_yookassa.Payment.create = MagicMock(return_value=mock_payment)
        sys.modules["yookassa"] = mock_yookassa

        try:
            request = PaymentRequest(
                user_id=1,
                payment_type=PaymentType.PACKAGE,
                item_id=1,
                amount=149.0,
                currency="RUB",
                description="50 minutes",
            )

            result = await provider.create_payment(request)
            assert result.success is True
            assert result.provider_transaction_id == "pay_123"
            assert result.payment_url == "https://yookassa.ru/pay/123"
        finally:
            del sys.modules["yookassa"]


# =============================================================================
# handle_callback (webhook) Tests
# =============================================================================


@pytest.mark.asyncio
async def test_handle_callback_payment_succeeded():
    """Test handling successful payment webhook."""
    provider = YooKassaProvider(shop_id="test", secret_key="test")

    result = await provider.handle_callback(
        {
            "event": "payment.succeeded",
            "object": {"id": "pay_123", "status": "succeeded"},
        }
    )

    assert result.success is True
    assert result.provider_transaction_id == "pay_123"


@pytest.mark.asyncio
async def test_handle_callback_payment_canceled():
    """Test handling cancelled payment webhook."""
    provider = YooKassaProvider(shop_id="test", secret_key="test")

    result = await provider.handle_callback(
        {
            "event": "payment.canceled",
            "object": {"id": "pay_456", "status": "canceled"},
        }
    )

    assert result.success is False
    assert "cancelled" in result.error_message.lower()


@pytest.mark.asyncio
async def test_handle_callback_unknown_event():
    """Test handling unknown event."""
    provider = YooKassaProvider(shop_id="test", secret_key="test")

    result = await provider.handle_callback(
        {
            "event": "refund.succeeded",
            "object": {"id": "ref_789"},
        }
    )

    assert result.success is False
    assert "Unknown event" in result.error_message


# =============================================================================
# verify_payment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_verify_payment_not_configured():
    """Test verify when SDK not configured."""
    provider = YooKassaProvider(shop_id="test", secret_key="test")

    result = await provider.verify_payment("pay_123")
    assert result.success is False


# =============================================================================
# parse_metadata Tests
# =============================================================================


def test_parse_metadata_valid():
    """Test parsing valid metadata."""
    result = YooKassaProvider.parse_metadata(
        {"payment_type": "package", "item_id": "1", "user_id": "123"}
    )
    assert result is not None
    assert result["payment_type"] == "package"
    assert result["item_id"] == 1
    assert result["user_id"] == 123


def test_parse_metadata_subscription():
    """Test parsing subscription metadata."""
    result = YooKassaProvider.parse_metadata(
        {"payment_type": "subscription", "item_id": "2", "user_id": "456"}
    )
    assert result is not None
    assert result["payment_type"] == "subscription"


def test_parse_metadata_invalid():
    """Test parsing invalid metadata."""
    result = YooKassaProvider.parse_metadata({"invalid": "data"})
    assert result is not None  # Returns with defaults
    assert result["item_id"] == 0


def test_parse_metadata_none_values():
    """Test parsing metadata with None values."""
    result = YooKassaProvider.parse_metadata({})
    assert result is not None
    assert result["payment_type"] == ""
    assert result["item_id"] == 0
