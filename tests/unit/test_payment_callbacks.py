"""
Tests for PaymentCallbackHandlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User

from src.services.payments.base import PaymentType
from src.bot.payment_callbacks import (
    PaymentCallbackHandlers,
    pre_checkout_query_handler,
    successful_payment_handler,
)


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

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_package_price", new_callable=AsyncMock, return_value=(149.0, 25)
        ),
        patch.object(
            handlers, "_get_package_name", new_callable=AsyncMock, return_value="30 минут"
        ),
        patch.object(
            handlers, "_get_package_description", new_callable=AsyncMock, return_value="Описание"
        ),
    ):
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

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_subscription_price", new_callable=AsyncMock, return_value=(299.0, 50)
        ),
        patch.object(handlers, "_get_tier_name", new_callable=AsyncMock, return_value="Pro"),
        patch.object(
            handlers,
            "_get_subscription_description",
            new_callable=AsyncMock,
            return_value="Описание",
        ),
    ):
        await handlers.buy_subscription_stars_callback(update, context)

    payment_service.create_payment.assert_awaited_once()
    call_args = payment_service.create_payment.await_args
    assert call_args.kwargs["provider_name"] == "telegram_stars"
    request = call_args.kwargs["request"]
    assert request.payment_type == PaymentType.SUBSCRIPTION
    assert request.item_id == 2


@pytest.mark.asyncio
async def test_buy_package_card_callback_creates_payment():
    """Test: buy_package_card_callback creates payment via PaymentService with yookassa provider."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=True, payment_url="https://t.me/invoice/card")
    )

    handlers = PaymentCallbackHandlers(payment_service=payment_service)

    callback_query = _make_callback_query("pkg_card:1")
    update = _make_update(callback_query)
    context = MagicMock()

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_package_price", new_callable=AsyncMock, return_value=(149.0, 25)
        ),
        patch.object(
            handlers, "_get_package_name", new_callable=AsyncMock, return_value="30 минут"
        ),
        patch.object(
            handlers, "_get_package_description", new_callable=AsyncMock, return_value="Описание"
        ),
    ):
        await handlers.buy_package_card_callback(update, context)

    payment_service.create_payment.assert_awaited_once()
    call_args = payment_service.create_payment.await_args
    assert call_args.kwargs["provider_name"] == "yookassa"
    request = call_args.kwargs["request"]
    assert request.payment_type == PaymentType.PACKAGE
    assert request.item_id == 1
    assert request.currency == "RUB"


@pytest.mark.asyncio
async def test_buy_package_card_callback_error_has_back_button():
    """Test: buy_package_card_callback error response includes back:buy button."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=False, payment_url=None, error_message="fail")
    )
    handlers = PaymentCallbackHandlers(payment_service=payment_service)
    callback_query = _make_callback_query("pkg_card:1")
    update = _make_update(callback_query)

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_package_price", new_callable=AsyncMock, return_value=(149.0, 25)
        ),
        patch.object(
            handlers, "_get_package_name", new_callable=AsyncMock, return_value="30 минут"
        ),
        patch.object(
            handlers, "_get_package_description", new_callable=AsyncMock, return_value="Описание"
        ),
    ):
        await handlers.buy_package_card_callback(update, MagicMock())

    call_args = callback_query.edit_message_text.await_args
    markup = call_args.kwargs["reply_markup"]
    back_buttons = [
        btn
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data == "billing:packages"
    ]
    assert len(back_buttons) == 1


@pytest.mark.asyncio
async def test_buy_subscription_card_callback_creates_payment():
    """Test: buy_subscription_card_callback creates payment via PaymentService with yookassa."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=True, payment_url="https://t.me/invoice/card")
    )

    handlers = PaymentCallbackHandlers(payment_service=payment_service)

    callback_query = _make_callback_query("sub_card:2:month")
    update = _make_update(callback_query)
    context = MagicMock()

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_subscription_price", new_callable=AsyncMock, return_value=(299.0, 50)
        ),
        patch.object(handlers, "_get_tier_name", new_callable=AsyncMock, return_value="Pro"),
        patch.object(
            handlers,
            "_get_subscription_description",
            new_callable=AsyncMock,
            return_value="Описание",
        ),
    ):
        await handlers.buy_subscription_card_callback(update, context)

    payment_service.create_payment.assert_awaited_once()
    call_args = payment_service.create_payment.await_args
    assert call_args.kwargs["provider_name"] == "yookassa"
    request = call_args.kwargs["request"]
    assert request.payment_type == PaymentType.SUBSCRIPTION
    assert request.item_id == 2
    assert request.currency == "RUB"


@pytest.mark.asyncio
async def test_buy_subscription_card_callback_error_has_back_button():
    """Test: buy_subscription_card_callback error response includes back:subscribe button."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=False, payment_url=None, error_message="fail")
    )
    handlers = PaymentCallbackHandlers(payment_service=payment_service)
    callback_query = _make_callback_query("sub_card:2:month")
    update = _make_update(callback_query)

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_subscription_price", new_callable=AsyncMock, return_value=(299.0, 50)
        ),
        patch.object(handlers, "_get_tier_name", new_callable=AsyncMock, return_value="Pro"),
        patch.object(
            handlers,
            "_get_subscription_description",
            new_callable=AsyncMock,
            return_value="Описание",
        ),
    ):
        await handlers.buy_subscription_card_callback(update, MagicMock())

    call_args = callback_query.edit_message_text.await_args
    markup = call_args.kwargs["reply_markup"]
    back_buttons = [
        btn
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data == "billing:subscriptions"
    ]
    assert len(back_buttons) == 1


@pytest.mark.asyncio
async def test_buy_package_stars_error_has_back_button():
    """Test: buy_package_stars_callback error response includes back:buy button."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=False, payment_url=None, error_message="fail")
    )
    handlers = PaymentCallbackHandlers(payment_service=payment_service)
    callback_query = _make_callback_query("pkg_stars:1")
    update = _make_update(callback_query)

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_package_price", new_callable=AsyncMock, return_value=(149.0, 25)
        ),
        patch.object(
            handlers, "_get_package_name", new_callable=AsyncMock, return_value="30 минут"
        ),
        patch.object(
            handlers, "_get_package_description", new_callable=AsyncMock, return_value="Описание"
        ),
    ):
        await handlers.buy_package_stars_callback(update, MagicMock())

    call_args = callback_query.edit_message_text.await_args
    markup = call_args.kwargs["reply_markup"]
    back_buttons = [
        btn
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data == "billing:packages"
    ]
    assert len(back_buttons) == 1


@pytest.mark.asyncio
async def test_buy_subscription_stars_error_has_back_button():
    """Test: buy_subscription_stars_callback error response includes back:subscribe button."""
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=False, payment_url=None, error_message="fail")
    )
    handlers = PaymentCallbackHandlers(payment_service=payment_service)
    callback_query = _make_callback_query("sub_stars:2:month")
    update = _make_update(callback_query)

    with (
        patch.object(handlers, "_get_db_user_id", new_callable=AsyncMock, return_value=999),
        patch.object(
            handlers, "_get_subscription_price", new_callable=AsyncMock, return_value=(299.0, 50)
        ),
        patch.object(handlers, "_get_tier_name", new_callable=AsyncMock, return_value="Pro"),
        patch.object(
            handlers,
            "_get_subscription_description",
            new_callable=AsyncMock,
            return_value="Описание",
        ),
    ):
        await handlers.buy_subscription_stars_callback(update, MagicMock())

    call_args = callback_query.edit_message_text.await_args
    markup = call_args.kwargs["reply_markup"]
    back_buttons = [
        btn
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data == "billing:subscriptions"
    ]
    assert len(back_buttons) == 1


# =============================================================================
# Task 2.3: PreCheckout and Successful Payment Handlers Tests
# =============================================================================


@pytest.mark.asyncio
async def test_pre_checkout_query_handler_approves():
    """Test: pre_checkout_query_handler approves valid payload with correct amount."""
    payment_service = AsyncMock()
    handler = pre_checkout_query_handler(payment_service)

    pre_checkout_query = MagicMock()
    pre_checkout_query.invoice_payload = "package:1:123"
    pre_checkout_query.total_amount = 25
    pre_checkout_query.currency = "XTR"
    pre_checkout_query.answer = AsyncMock()

    update = MagicMock()
    update.pre_checkout_query = pre_checkout_query
    context = MagicMock()

    mock_package = MagicMock()
    mock_package.price_stars = 25

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.MinutePackageRepository") as MockPkgRepo:
            MockPkgRepo.return_value.get_by_id = AsyncMock(return_value=mock_package)
            await handler(update, context)

    pre_checkout_query.answer.assert_awaited_once_with(ok=True)


@pytest.mark.asyncio
async def test_successful_payment_handler_stars():
    """Test: successful_payment_handler detects Stars by XTR currency."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    successful_payment = MagicMock()
    successful_payment.invoice_payload = "package:1:123"
    successful_payment.telegram_payment_charge_id = "charge_123"
    successful_payment.currency = "XTR"

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.successful_payment = successful_payment

    update = MagicMock()
    update.message = message
    update.effective_user = User(id=555, is_bot=False, first_name="Test")
    context = MagicMock()

    # Mock DB lookup: telegram_id=555 → db_user_id=123 (matches payload)
    mock_db_user = MagicMock()
    mock_db_user.id = 123

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.UserRepository") as MockUserRepo:
            MockUserRepo.return_value.get_by_telegram_id = AsyncMock(return_value=mock_db_user)
            await handler(update, context)

    payment_service.handle_successful_payment.assert_awaited_once()
    call_args = payment_service.handle_successful_payment.await_args
    assert call_args.kwargs["provider_name"] == "telegram_stars"
    assert call_args.kwargs["user_id"] == 123
    assert call_args.kwargs["payment_type"] == PaymentType.PACKAGE
    assert call_args.kwargs["item_id"] == 1
    assert call_args.kwargs["provider_transaction_id"] == "charge_123"


@pytest.mark.asyncio
async def test_successful_payment_handler_yookassa():
    """Test: successful_payment_handler detects YooKassa by RUB currency."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    successful_payment = MagicMock()
    successful_payment.invoice_payload = "subscription:2:999"
    successful_payment.telegram_payment_charge_id = "charge_456"
    successful_payment.currency = "RUB"

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.successful_payment = successful_payment

    update = MagicMock()
    update.message = message
    update.effective_user = User(id=555, is_bot=False, first_name="Test")
    context = MagicMock()

    # Mock DB lookup: telegram_id=555 → db_user_id=999 (matches payload)
    mock_db_user = MagicMock()
    mock_db_user.id = 999

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.UserRepository") as MockUserRepo:
            MockUserRepo.return_value.get_by_telegram_id = AsyncMock(return_value=mock_db_user)
            await handler(update, context)

    payment_service.handle_successful_payment.assert_awaited_once()
    call_args = payment_service.handle_successful_payment.await_args
    assert call_args.kwargs["provider_name"] == "yookassa"
    assert call_args.kwargs["user_id"] == 999
    assert call_args.kwargs["payment_type"] == PaymentType.SUBSCRIPTION
    assert call_args.kwargs["item_id"] == 2
    assert call_args.kwargs["provider_transaction_id"] == "charge_456"


# =============================================================================
# Phase 1: Security — Pre-checkout validation, user_id verification, period
# =============================================================================


@pytest.mark.asyncio
async def test_pre_checkout_rejects_malformed_payload():
    """Task 1.1: pre_checkout_query rejects malformed payload."""
    payment_service = AsyncMock()
    handler = pre_checkout_query_handler(payment_service)

    pre_checkout_query = MagicMock()
    pre_checkout_query.invoice_payload = "garbage"
    pre_checkout_query.answer = AsyncMock()

    update = MagicMock()
    update.pre_checkout_query = pre_checkout_query
    context = MagicMock()

    await handler(update, context)

    pre_checkout_query.answer.assert_awaited_once()
    call_kwargs = pre_checkout_query.answer.await_args.kwargs
    assert call_kwargs["ok"] is False
    assert "error_message" in call_kwargs


@pytest.mark.asyncio
async def test_pre_checkout_rejects_nonexistent_package():
    """Task 1.1: pre_checkout_query rejects payload referencing non-existent package."""
    payment_service = AsyncMock()
    handler = pre_checkout_query_handler(payment_service)

    pre_checkout_query = MagicMock()
    pre_checkout_query.invoice_payload = "package:9999:123"
    pre_checkout_query.total_amount = 25
    pre_checkout_query.currency = "XTR"
    pre_checkout_query.answer = AsyncMock()

    update = MagicMock()
    update.pre_checkout_query = pre_checkout_query
    context = MagicMock()

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.MinutePackageRepository") as MockPkgRepo:
            MockPkgRepo.return_value.get_by_id = AsyncMock(return_value=None)
            await handler(update, context)

    pre_checkout_query.answer.assert_awaited_once()
    call_kwargs = pre_checkout_query.answer.await_args.kwargs
    assert call_kwargs["ok"] is False


@pytest.mark.asyncio
async def test_pre_checkout_rejects_wrong_stars_amount():
    """Task 1.1: pre_checkout_query rejects mismatched Stars amount."""
    payment_service = AsyncMock()
    handler = pre_checkout_query_handler(payment_service)

    pre_checkout_query = MagicMock()
    pre_checkout_query.invoice_payload = "package:1:123"
    pre_checkout_query.total_amount = 999  # wrong amount
    pre_checkout_query.currency = "XTR"
    pre_checkout_query.answer = AsyncMock()

    update = MagicMock()
    update.pre_checkout_query = pre_checkout_query
    context = MagicMock()

    mock_package = MagicMock()
    mock_package.price_stars = 25  # correct amount is 25, sent 999

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.MinutePackageRepository") as MockPkgRepo:
            MockPkgRepo.return_value.get_by_id = AsyncMock(return_value=mock_package)
            await handler(update, context)

    pre_checkout_query.answer.assert_awaited_once()
    call_kwargs = pre_checkout_query.answer.await_args.kwargs
    assert call_kwargs["ok"] is False


@pytest.mark.asyncio
async def test_pre_checkout_approves_valid_package():
    """Task 1.1: pre_checkout_query approves valid payload with correct amount."""
    payment_service = AsyncMock()
    handler = pre_checkout_query_handler(payment_service)

    pre_checkout_query = MagicMock()
    pre_checkout_query.invoice_payload = "package:1:123"
    pre_checkout_query.total_amount = 25
    pre_checkout_query.currency = "XTR"
    pre_checkout_query.answer = AsyncMock()

    update = MagicMock()
    update.pre_checkout_query = pre_checkout_query
    context = MagicMock()

    mock_package = MagicMock()
    mock_package.price_stars = 25

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.MinutePackageRepository") as MockPkgRepo:
            MockPkgRepo.return_value.get_by_id = AsyncMock(return_value=mock_package)
            await handler(update, context)

    pre_checkout_query.answer.assert_awaited_once_with(ok=True)


@pytest.mark.asyncio
async def test_successful_payment_rejects_user_id_mismatch():
    """Task 1.2: successful_payment_handler rejects when effective_user.id != payload user_id."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    successful_payment = MagicMock()
    successful_payment.invoice_payload = "package:1:999"  # user_id=999 in payload
    successful_payment.telegram_payment_charge_id = "charge_123"
    successful_payment.currency = "XTR"

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.successful_payment = successful_payment

    update = MagicMock()
    update.message = message
    # effective_user has telegram_id=555, which maps to db_user_id=777 (not 999)
    update.effective_user = User(id=555, is_bot=False, first_name="Attacker")
    context = MagicMock()

    mock_db_user = MagicMock()
    mock_db_user.id = 777  # DB id differs from payload user_id=999

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.UserRepository") as MockUserRepo:
            MockUserRepo.return_value.get_by_telegram_id = AsyncMock(return_value=mock_db_user)
            await handler(update, context)

    # Should NOT call handle_successful_payment when user_id doesn't match
    payment_service.handle_successful_payment.assert_not_awaited()
    # Should reply with error
    message.reply_text.assert_awaited_once()
    reply_text = message.reply_text.await_args.args[0]
    assert "ошибка" in reply_text.lower() or "Ошибка" in reply_text


@pytest.mark.asyncio
async def test_successful_payment_passes_period_for_subscription():
    """Task 1.3: successful_payment_handler passes period from payload for subscriptions."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    # New payload format with period: subscription:2:999:year
    successful_payment = MagicMock()
    successful_payment.invoice_payload = "subscription:2:999:year"
    successful_payment.telegram_payment_charge_id = "charge_789"
    successful_payment.currency = "XTR"

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.successful_payment = successful_payment

    update = MagicMock()
    update.message = message
    update.effective_user = User(id=555, is_bot=False, first_name="Test")
    context = MagicMock()

    mock_db_user = MagicMock()
    mock_db_user.id = 999  # matches payload user_id

    with patch("src.bot.payment_callbacks.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.payment_callbacks.UserRepository") as MockUserRepo:
            MockUserRepo.return_value.get_by_telegram_id = AsyncMock(return_value=mock_db_user)
            await handler(update, context)

    payment_service.handle_successful_payment.assert_awaited_once()
    call_kwargs = payment_service.handle_successful_payment.await_args.kwargs
    assert call_kwargs["period"] == "year"
