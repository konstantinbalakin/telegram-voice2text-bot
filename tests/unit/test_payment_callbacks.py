"""
Tests for PaymentCallbackHandlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User
from telegram.ext import ContextTypes

from src.services.payments.base import PaymentType, SubscriptionPeriod
from src.bot.payment_callbacks import PaymentCallbackHandlers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_callback_query(
    data: str,
    user_id: int = 12345,
    message_id: int = 100,
) -> MagicMock:
    """Create a mock CallbackQuery for testing."""
    user = User(id=user_id, is_bot=False, first_name="Test")
    message = MagicMock()
    message.chat_id = 12345
    message.message_id = message_id
    message.reply_text = AsyncMock()
    message.edit_text = AsyncMock()

    callback_query = MagicMock()
    callback_query.id = "test_callback_id"
    callback_query.data = data
    callback_query.from_user = user
    callback_query.chat_instance = "test_instance"
    callback_query.message = message
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()
    return callback_query


def _make_update(callback_query: MagicMock) -> Update:
    """Create an Update with a callback query."""
    update = Update(update_id=1, callback_query=callback_query)
    return update


def _make_payment_callbacks() -> PaymentCallbackHandlers:
    """Create PaymentCallbackHandlers with mocked payment service."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=True, payment_url="https://t.me/...")
    )
    return PaymentCallbackHandlers(payment_service=payment_service)


# =============================================================================
# Task 2.1: PaymentCallbackHandlers Tests
# =============================================================================


@pytest.mark.asyncio
async def test_buy_package_stars_callback_creates_payment():
    """Test: buy_package_stars_callback creates payment via PaymentService."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=True, payment_url="https://t.me/...")
    )

    handlers = PaymentCallbackHandlers(payment_service=payment_service)

    callback_query = _make_callback_query("pkg_stars:1")
    update = _make_update(callback_query)
    context = MagicMock()

    with patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999):
        await handlers.buy_package_stars_callback(update, context)

    payment_service.create_payment.assert_awaited_once()
    call_args = payment_service.create_payment.await_args
    assert call_args.kwargs["provider_name"] == "telegram_stars"
    request = call_args.kwargs["request"]
    assert request.payment_type == PaymentType.PACKAGE
    assert request.item_id == 1


@pytest.mark.asyncio
async def test_buy_subscription_stars_callback_creates_payment():
    """Test: buy_subscription_stars_callback creates payment via PaymentService."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=True, payment_url="https://t.me/...")
    )

    handlers = PaymentCallbackHandlers(payment_service=payment_service)

    callback_query = _make_callback_query("sub_stars:2:month")
    update = _make_update(callback_query)
    context = MagicMock()

    with patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999):
        await handlers.buy_subscription_stars_callback(update, context)

    payment_service.create_payment.assert_awaited_once()
    call_args = payment_service.create_payment.await_args
    assert call_args.kwargs["provider_name"] == "telegram_stars"
    request = call_args.kwargs["request"]
    assert request.payment_type == PaymentType.SUBSCRIPTION
    assert request.item_id == 2


@pytest.mark.asyncio
async def test_buy_package_card_callback_shows_stub():
    """Test: buy_package_card_callback shows stub message."""
    payment_service = AsyncMock()
    handlers = PaymentCallbackHandlers(payment_service=payment_service)

    callback_query = _make_callback_query("pkg_card:1")
    update = _make_update(callback_query)
    context = MagicMock()

    await handlers.buy_package_card_callback(update, context)

    payment_service.create_payment.assert_not_awaited()
    callback_query.edit_message_text.assert_awaited_once()
    call_args = callback_query.edit_message_text.await_args
    assert "карт" in call_args.args[0].lower()


@pytest.mark.asyncio
async def test_buy_subscription_card_callback_shows_stub():
    """Test: buy_subscription_card_callback shows stub message."""
    payment_service = AsyncMock()
    handlers = PaymentCallbackHandlers(payment_service=payment_service)

    callback_query = _make_callback_query("sub_card:2:month")
    update = _make_update(callback_query)
    context = MagicMock()

    await handlers.buy_subscription_card_callback(update, context)

    payment_service.create_payment.assert_not_awaited()
    callback_query.edit_message_text.assert_awaited_once()
    call_args = callback_query.edit_message_text.await_args
    assert "карт" in call_args.args[0].lower()


# =============================================================================
# Task 2.3: PreCheckout and Successful Payment Handlers Tests
# =============================================================================


from src.bot.payment_callbacks import (
    pre_checkout_query_handler,
    successful_payment_handler,
)


@pytest.mark.asyncio
async def test_pre_checkout_query_handler_approves():
    """Test: pre_checkout_query_handler always approves queries."""
    payment_service = AsyncMock()
    handler = pre_checkout_query_handler(payment_service)

    pre_checkout_query = MagicMock()
    pre_checkout_query.answer = AsyncMock()

    update = MagicMock()
    update.pre_checkout_query = pre_checkout_query
    context = MagicMock()

    await handler(update, context)

    pre_checkout_query.answer.assert_awaited_once_with(ok=True)


@pytest.mark.asyncio
async def test_successful_payment_handler_parses_payload():
    """Test: successful_payment_handler parses payload and calls handle_successful_payment."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    successful_payment = MagicMock()
    successful_payment.invoice_payload = "package:1:123"
    successful_payment.telegram_payment_charge_id = "charge_123"

    message = MagicMock()
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.successful_payment = successful_payment
    update.message = message
    update.effective_user = User(id=123, is_bot=False, first_name="Test")
    context = MagicMock()

    with patch(
        "src.bot.payment_callbacks._get_user_db_id", new_callable=AsyncMock, return_value=999
    ):
        await handler(update, context)

    payment_service.handle_successful_payment.assert_awaited_once()
    call_args = payment_service.handle_successful_payment.await_args
    assert call_args.kwargs["provider_name"] == "telegram_stars"
    assert call_args.kwargs["user_id"] == 999
    assert call_args.kwargs["payment_type"] == PaymentType.PACKAGE
    assert call_args.kwargs["item_id"] == 1
    assert call_args.kwargs["provider_transaction_id"] == "charge_123"



@pytest.mark.asyncio
async def test_successful_payment_handler_subscription():
    """Test: successful_payment_handler handles subscriptions."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    successful_payment = MagicMock()
    successful_payment.invoice_payload = "subscription:2:999"
    successful_payment.telegram_payment_charge_id = "charge_456"

    message = MagicMock()
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.successful_payment = successful_payment
    update.message = message
    update.effective_user = User(id=123, is_bot=False, first_name="Test")
    context = MagicMock()

    with patch(
        "src.bot.payment_callbacks._get_user_db_id", new_callable=AsyncMock, return_value=999
    ):
        await handler(update, context)

    payment_service.handle_successful_payment.assert_awaited_once()
    call_args = payment_service.handle_successful_payment.await_args
    assert call_args.kwargs["provider_name"] == "telegram_stars"
    assert call_args.kwargs["user_id"] == 999
    assert call_args.kwargs["payment_type"] == PaymentType.SUBSCRIPTION
    assert call_args.kwargs["item_id"] == 2
    assert call_args.kwargs["provider_transaction_id"] == "charge_456"
