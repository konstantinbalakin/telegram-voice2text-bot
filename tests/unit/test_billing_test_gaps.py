"""
Tests for billing security fixes — Phase 7: Test gaps.

Covers:
- 7.1: successful_payment_handler with invalid payload
- 7.2: create_payment stores amount as-is (kopecks)
- 7.3: Invalid callback_data format handled (non-integer package_id)
- 7.4: /start grants welcome bonus; bonus error doesn't break /start
- 7.5: successful_payment_handler with invalid payment_type
- 7.6: PaymentResult.__post_init__ validation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User

from src.services.payments.base import (
    Currency,
    PaymentRequest,
    PaymentResult,
    PaymentType,
)
from src.services.payments.payment_service import PaymentService
from src.bot.payment_callbacks import (
    PaymentCallbackHandlers,
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


def _make_update_with_callback(callback_query: MagicMock) -> Update:
    """Create an Update with a callback query."""
    return Update(update_id=1, callback_query=callback_query)


def _make_payment_service_with_mocks() -> tuple[PaymentService, dict[str, AsyncMock]]:
    """Create PaymentService with mocked repos (same pattern as test_payment_service.py)."""
    mocks = {
        "purchase_repo": AsyncMock(),
        "subscription_repo": AsyncMock(),
        "balance_repo": AsyncMock(),
        "package_repo": AsyncMock(),
        "subscription_service": AsyncMock(),
    }

    service = PaymentService(
        purchase_repo=mocks["purchase_repo"],
        subscription_repo=mocks["subscription_repo"],
        balance_repo=mocks["balance_repo"],
        package_repo=mocks["package_repo"],
        subscription_service=mocks["subscription_service"],
    )

    return service, mocks


def _mock_provider(name: str = "test_provider") -> MagicMock:
    """Create a mock payment provider."""
    provider = MagicMock()
    provider.provider_name = name
    provider.create_payment = AsyncMock()
    provider.handle_callback = AsyncMock()
    provider.verify_payment = AsyncMock()
    return provider


# =============================================================================
# Task 7.1: successful_payment_handler with invalid payload
# =============================================================================


@pytest.mark.asyncio
async def test_successful_payment_handler_invalid_payload_replies_error():
    """Task 7.1: successful_payment_handler replies with error when payload is invalid/malformed."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    successful_payment = MagicMock()
    successful_payment.invoice_payload = "invalid_payload"
    successful_payment.telegram_payment_charge_id = "charge_bad"
    successful_payment.currency = "XTR"

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.successful_payment = successful_payment

    update = MagicMock()
    update.message = message
    update.effective_user = User(id=555, is_bot=False, first_name="Test")
    context = MagicMock()

    await handler(update, context)

    # Should NOT process payment
    payment_service.handle_successful_payment.assert_not_awaited()
    # Should reply with error message
    message.reply_text.assert_awaited_once()
    reply_text = message.reply_text.await_args.args[0]
    assert reply_text == "Ошибка обработки платежа. Свяжитесь с поддержкой."


# =============================================================================
# Task 7.2: create_payment stores amount as-is (kopecks)
# =============================================================================


@pytest.mark.asyncio
async def test_create_payment_stores_amount_as_is_kopecks():
    """Task 7.2: create_payment passes amount directly to purchase_repo.create without conversion."""
    service, mocks = _make_payment_service_with_mocks()
    provider = _mock_provider("test_provider")
    provider.create_payment.return_value = PaymentResult(
        success=True, provider_transaction_id="tx_100"
    )
    service.register_provider(provider)

    mock_purchase = MagicMock()
    mock_purchase.id = 1
    mocks["purchase_repo"].create.return_value = mock_purchase

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=14900,
        currency=Currency.RUB,
        description="30 minutes",
    )

    await service.create_payment("test_provider", request)

    mocks["purchase_repo"].create.assert_called_once()
    call_kwargs = mocks["purchase_repo"].create.call_args.kwargs
    assert call_kwargs["amount"] == 14900


# =============================================================================
# Task 7.3: Invalid callback_data format handled (non-integer package_id)
# =============================================================================


@pytest.mark.asyncio
async def test_buy_package_stars_callback_non_integer_package_id():
    """Task 7.3: buy_package_stars_callback handles 'pkg_stars:abc' gracefully."""
    payment_service = AsyncMock()
    handlers = PaymentCallbackHandlers(payment_service=payment_service)

    callback_query = _make_callback_query("pkg_stars:abc")
    update = _make_update_with_callback(callback_query)
    context = MagicMock()

    await handlers.buy_package_stars_callback(update, context)

    # ValueError from int("abc") is caught by the except Exception handler
    callback_query.edit_message_text.assert_awaited_once()
    reply_text = callback_query.edit_message_text.await_args.args[0]
    assert "ошибка" in reply_text.lower() or "Ошибка" in reply_text


# =============================================================================
# Task 7.4: /start grants welcome bonus; bonus error doesn't break /start
# =============================================================================


@pytest.mark.asyncio
async def test_start_command_grants_welcome_bonus_for_new_user():
    """Task 7.4a: /start for new user calls billing_service.grant_welcome_bonus(db_user.id)."""
    billing_service = AsyncMock()
    billing_service.grant_welcome_bonus = AsyncMock()
    subscription_service = AsyncMock()
    payment_service = AsyncMock()

    from src.bot.billing_commands import BillingCommands

    commands = BillingCommands(
        billing_service=billing_service,
        subscription_service=subscription_service,
        payment_service=payment_service,
    )

    user = User(id=555, is_bot=False, first_name="New", username="newuser")
    message = MagicMock()
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_user = user
    update.message = message
    context = MagicMock()

    mock_db_user = MagicMock()
    mock_db_user.id = 42

    with patch("src.bot.billing_commands.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
            # First call: user not found (new user)
            MockUserRepo.return_value.get_by_telegram_id = AsyncMock(return_value=None)
            # Second call: create returns db_user
            MockUserRepo.return_value.create = AsyncMock(return_value=mock_db_user)

            await commands.start_command_with_billing(update, context)

    billing_service.grant_welcome_bonus.assert_awaited_once_with(42)
    # Welcome message should still be sent
    message.reply_text.assert_awaited_once()
    reply_text = message.reply_text.await_args.args[0]
    assert "Привет" in reply_text


@pytest.mark.asyncio
async def test_start_command_bonus_error_doesnt_break_start():
    """Task 7.4b: if grant_welcome_bonus raises, /start still sends welcome message."""
    billing_service = AsyncMock()
    billing_service.grant_welcome_bonus = AsyncMock(side_effect=RuntimeError("Bonus DB error"))
    subscription_service = AsyncMock()
    payment_service = AsyncMock()

    from src.bot.billing_commands import BillingCommands

    commands = BillingCommands(
        billing_service=billing_service,
        subscription_service=subscription_service,
        payment_service=payment_service,
    )

    user = User(id=555, is_bot=False, first_name="New", username="newuser")
    message = MagicMock()
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_user = user
    update.message = message
    context = MagicMock()

    mock_db_user = MagicMock()
    mock_db_user.id = 42

    with patch("src.bot.billing_commands.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
            MockUserRepo.return_value.get_by_telegram_id = AsyncMock(return_value=None)
            MockUserRepo.return_value.create = AsyncMock(return_value=mock_db_user)

            await commands.start_command_with_billing(update, context)

    # Welcome message should still be sent despite bonus error
    message.reply_text.assert_awaited_once()
    reply_text = message.reply_text.await_args.args[0]
    assert "Привет" in reply_text


# =============================================================================
# Task 7.5: successful_payment_handler with invalid payment_type
# =============================================================================


@pytest.mark.asyncio
async def test_successful_payment_handler_invalid_payment_type():
    """Task 7.5: when payment_type in payload is invalid, handler replies with error."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    # Payload with valid structure but unknown payment_type
    successful_payment = MagicMock()
    successful_payment.invoice_payload = "unknown_type:1:123"
    successful_payment.telegram_payment_charge_id = "charge_bad_type"
    successful_payment.currency = "XTR"

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.successful_payment = successful_payment

    update = MagicMock()
    update.message = message
    update.effective_user = User(id=555, is_bot=False, first_name="Test")
    context = MagicMock()

    await handler(update, context)

    # PaymentType("unknown_type") raises ValueError, caught by except Exception
    payment_service.handle_successful_payment.assert_not_awaited()
    message.reply_text.assert_awaited_once()
    reply_text = message.reply_text.await_args.args[0]
    assert "Ошибка" in reply_text


# =============================================================================
# Task 7.6: PaymentResult.__post_init__ validation
# =============================================================================


def test_payment_result_post_init_rejects_success_with_error_message():
    """Task 7.6: PaymentResult(success=True, error_message='oops') raises ValueError."""
    with pytest.raises(ValueError, match="success=True is incompatible with error_message"):
        PaymentResult(success=True, error_message="oops")


def test_payment_result_post_init_allows_success_without_error():
    """Task 7.6: PaymentResult(success=True) without error_message is valid."""
    result = PaymentResult(success=True)
    assert result.success is True
    assert result.error_message is None


def test_payment_result_post_init_allows_failure_with_error():
    """Task 7.6: PaymentResult(success=False, error_message='fail') is valid."""
    result = PaymentResult(success=False, error_message="fail")
    assert result.success is False
    assert result.error_message == "fail"
