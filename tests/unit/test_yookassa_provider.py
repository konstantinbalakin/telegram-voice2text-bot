"""
Tests for YooKassaProvider (Native Telegram Payments via provider_token).

The new YooKassaProvider uses Telegram Payments API (sendInvoice)
with currency=RUB and provider_token, similar to TelegramStarsProvider.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram import Bot

from src.services.payments.base import PaymentRequest, PaymentType
from src.services.payments.yookassa_provider import YooKassaProvider


# =============================================================================
# Provider basics
# =============================================================================


def test_provider_name():
    """Test provider name is yookassa."""
    bot = MagicMock(spec=Bot)
    provider = YooKassaProvider(bot=bot, provider_token="test_token")
    assert provider.provider_name == "yookassa"


def test_provider_stores_token():
    """Test provider stores provider_token."""
    bot = MagicMock(spec=Bot)
    provider = YooKassaProvider(bot=bot, provider_token="tok_123")
    assert provider.provider_token == "tok_123"


# =============================================================================
# create_payment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_payment_creates_invoice_link():
    """Test create_payment calls bot.create_invoice_link with RUB currency."""
    bot = MagicMock(spec=Bot)
    bot.create_invoice_link = AsyncMock(return_value="https://t.me/invoice/abc")
    provider = YooKassaProvider(bot=bot, provider_token="tok_test")

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=42,
        amount=14900,  # Amount in kopecks (149.00 RUB)
        currency="RUB",
        description="50 минут транскрипции",
    )

    result = await provider.create_payment(request)

    assert result.success is True
    assert result.payment_url == "https://t.me/invoice/abc"
    bot.create_invoice_link.assert_awaited_once()

    # Verify the invoice was created with correct parameters
    call_kwargs = bot.create_invoice_link.await_args.kwargs
    assert call_kwargs["currency"] == "RUB"
    assert call_kwargs["provider_token"] == "tok_test"
    assert "package:42:1" in call_kwargs["payload"]


@pytest.mark.asyncio
async def test_create_payment_subscription():
    """Test create_payment for subscription type."""
    bot = MagicMock(spec=Bot)
    bot.create_invoice_link = AsyncMock(return_value="https://t.me/invoice/xyz")
    provider = YooKassaProvider(bot=bot, provider_token="tok_test")

    request = PaymentRequest(
        user_id=10,
        payment_type=PaymentType.SUBSCRIPTION,
        item_id=2,
        amount=29900,
        currency="RUB",
        description="Подписка на месяц",
    )

    result = await provider.create_payment(request)

    assert result.success is True
    assert result.payment_url == "https://t.me/invoice/xyz"

    call_kwargs = bot.create_invoice_link.await_args.kwargs
    assert "subscription:2:10" in call_kwargs["payload"]


@pytest.mark.asyncio
async def test_create_payment_failure():
    """Test create_payment handles errors gracefully."""
    bot = MagicMock(spec=Bot)
    bot.create_invoice_link = AsyncMock(side_effect=Exception("Telegram API error"))
    provider = YooKassaProvider(bot=bot, provider_token="tok_test")

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=14900,
        currency="RUB",
        description="Test",
    )

    result = await provider.create_payment(request)

    assert result.success is False
    assert "Telegram API error" in result.error_message


# =============================================================================
# handle_callback Tests
# =============================================================================


@pytest.mark.asyncio
async def test_handle_callback_returns_success():
    """Test handle_callback returns success (managed by Telegram)."""
    bot = MagicMock(spec=Bot)
    provider = YooKassaProvider(bot=bot, provider_token="tok_test")

    result = await provider.handle_callback({})
    assert result.success is True


# =============================================================================
# verify_payment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_verify_payment_returns_success():
    """Test verify_payment returns success (managed by Telegram)."""
    bot = MagicMock(spec=Bot)
    provider = YooKassaProvider(bot=bot, provider_token="tok_test")

    result = await provider.verify_payment("tx_123")
    assert result.success is True
    assert result.provider_transaction_id == "tx_123"


# =============================================================================
# parse_payload Tests
# =============================================================================


def test_parse_payload_valid():
    """Test parsing valid payload."""
    result = YooKassaProvider.parse_payload("package:1:123")
    assert result is not None
    assert result["payment_type"] == "package"
    assert result["item_id"] == 1
    assert result["user_id"] == 123


def test_parse_payload_subscription():
    """Test parsing subscription payload."""
    result = YooKassaProvider.parse_payload("subscription:2:456")
    assert result is not None
    assert result["payment_type"] == "subscription"
    assert result["item_id"] == 2
    assert result["user_id"] == 456


def test_parse_payload_invalid():
    """Test parsing invalid payload returns None."""
    result = YooKassaProvider.parse_payload("invalid")
    assert result is None


def test_parse_payload_malformed():
    """Test parsing malformed payload returns None."""
    result = YooKassaProvider.parse_payload("a:b:c")
    assert result is None
