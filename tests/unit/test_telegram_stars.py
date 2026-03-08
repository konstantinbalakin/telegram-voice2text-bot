"""
Tests for TelegramStarsProvider (Phase 8)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.payments.base import Currency, PaymentRequest, PaymentType
from src.services.payments.telegram_stars import TelegramStarsProvider


# === Helpers ===


def _make_stars_provider() -> tuple[TelegramStarsProvider, MagicMock]:
    """Create TelegramStarsProvider with mocked bot."""
    mock_bot = MagicMock()
    mock_bot.create_invoice_link = AsyncMock()
    provider = TelegramStarsProvider(bot=mock_bot)
    return provider, mock_bot


# =============================================================================
# Provider basics
# =============================================================================


def test_provider_name():
    """Test provider name is telegram_stars."""
    provider, _ = _make_stars_provider()
    assert provider.provider_name == "telegram_stars"


# =============================================================================
# create_payment (sendInvoice) Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_invoice_success():
    """Test creating a Telegram Stars invoice."""
    provider, mock_bot = _make_stars_provider()
    mock_bot.create_invoice_link.return_value = "https://t.me/$invoice_123"

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=75,  # Stars amount
        currency=Currency.XTR,
        description="50 minutes package",
    )

    result = await provider.create_payment(request)
    assert result.success is True
    assert result.payment_url == "https://t.me/$invoice_123"
    mock_bot.create_invoice_link.assert_called_once()


@pytest.mark.asyncio
async def test_create_invoice_failure():
    """Test handling invoice creation failure."""
    provider, mock_bot = _make_stars_provider()
    mock_bot.create_invoice_link.side_effect = Exception("API error")

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=75,
        currency=Currency.XTR,
        description="50 minutes",
    )

    result = await provider.create_payment(request)
    assert result.success is False
    assert result.error_message is not None


@pytest.mark.asyncio
async def test_create_subscription_invoice():
    """Test creating subscription invoice."""
    provider, mock_bot = _make_stars_provider()
    mock_bot.create_invoice_link.return_value = "https://t.me/$sub_123"

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.SUBSCRIPTION,
        item_id=1,
        amount=150,
        currency=Currency.XTR,
        description="Pro subscription (month)",
    )

    result = await provider.create_payment(request)
    assert result.success is True

    # Verify payload format
    call_kwargs = mock_bot.create_invoice_link.call_args.kwargs
    assert "subscription:1:1" in call_kwargs["payload"]


# =============================================================================
# handle_callback (pre_checkout_query / successful_payment) Tests
# =============================================================================


@pytest.mark.asyncio
async def test_handle_callback():
    """Test handling payment callback."""
    provider, _ = _make_stars_provider()
    result = await provider.handle_callback({})
    assert result.success is True


# =============================================================================
# verify_payment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_verify_payment():
    """Test verifying Stars payment."""
    provider, _ = _make_stars_provider()
    result = await provider.verify_payment("tx_123")
    assert result.success is True
    assert result.provider_transaction_id == "tx_123"


# =============================================================================
# Payload parsing Tests
# =============================================================================


def test_parse_payload_package():
    """Test parsing package payment payload."""
    from src.services.payments.base import parse_payment_payload

    result = parse_payment_payload("package:1:123")
    assert result is not None
    assert result["payment_type"] == "package"
    assert result["item_id"] == 1
    assert result["user_id"] == 123


def test_parse_payload_subscription():
    """Test parsing subscription payment payload."""
    from src.services.payments.base import parse_payment_payload

    result = parse_payment_payload("subscription:2:456")
    assert result is not None
    assert result["payment_type"] == "subscription"
    assert result["item_id"] == 2
    assert result["user_id"] == 456


def test_parse_payload_subscription_with_period():
    """Test parsing subscription payload with period."""
    from src.services.payments.base import parse_payment_payload

    result = parse_payment_payload("subscription:2:456:year")
    assert result is not None
    assert result["payment_type"] == "subscription"
    assert result["item_id"] == 2
    assert result["user_id"] == 456
    assert result["period"] == "year"


def test_parse_payload_invalid():
    """Test parsing invalid payload."""
    from src.services.payments.base import parse_payment_payload

    assert parse_payment_payload("invalid") is None
    assert parse_payment_payload("a:b:c") is None
    assert parse_payment_payload("") is None


# =============================================================================
# Expiration reminder Tests (Task 8.4-8.5)
# =============================================================================


@pytest.mark.asyncio
async def test_expiration_reminder_for_stars():
    """Test that expiration reminder logic filters Stars subscriptions.

    This is tested in test_subscription_service.py
    (get_expiring_subscriptions_stars). Here we just verify
    the provider name matches what SubscriptionService filters on.
    """
    provider, _ = _make_stars_provider()
    assert provider.provider_name == "telegram_stars"
