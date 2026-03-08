"""
Tests for Phase 5: Качество кода и error handling.

Task 5.1: Error messages пользователю не содержат внутренних деталей.
Task 5.3: Callback except-блоки показывают ошибку пользователю.
Task 5.4: Нет assert в production коде (payment_service, billing_service).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.payments.telegram_stars import TelegramStarsProvider
from src.services.payments.yookassa_provider import YooKassaProvider
from src.services.payments.base import PaymentRequest, PaymentType


# =============================================================================
# Task 5.1: Error messages do not leak internal details
# =============================================================================


@pytest.mark.asyncio
async def test_telegram_stars_error_no_internal_details():
    """TelegramStarsProvider error_message must not contain exception text."""
    bot = AsyncMock()
    bot.create_invoice_link.side_effect = Exception("Connection refused: host=api.telegram.org:443")

    provider = TelegramStarsProvider(bot=bot)
    request = PaymentRequest(
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        user_id=123,
        amount=100,
        currency="XTR",
        description="Test",
    )

    result = await provider.create_payment(request)

    assert result.success is False
    assert result.error_message is not None
    # Must NOT contain exception details
    assert "Connection refused" not in result.error_message
    assert "api.telegram.org" not in result.error_message


@pytest.mark.asyncio
async def test_yookassa_error_no_internal_details():
    """YooKassaProvider error_message must not contain exception text."""
    bot = AsyncMock()
    bot.create_invoice_link.side_effect = Exception("Timeout connecting to payment gateway")

    provider = YooKassaProvider(bot=bot, provider_token="test_token")
    request = PaymentRequest(
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        user_id=123,
        amount=10000,
        currency="RUB",
        description="Test",
    )

    result = await provider.create_payment(request)

    assert result.success is False
    assert result.error_message is not None
    assert "Timeout" not in result.error_message
    assert "payment gateway" not in result.error_message


# =============================================================================
# Task 5.3: Callback except-blocks show error to user
# =============================================================================


@pytest.mark.asyncio
async def test_callback_error_shows_message_to_user():
    """Callback handlers must edit_message_text with error on exception."""
    from src.bot.billing_commands import BillingCommands

    billing_service = AsyncMock()
    subscription_service = AsyncMock()
    payment_service = AsyncMock()

    commands = BillingCommands(
        billing_service=billing_service,
        subscription_service=subscription_service,
        payment_service=payment_service,
    )

    # Test back_to_main_callback
    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123

    # Make build_balance_text_and_markup raise
    with patch.object(commands, "build_balance_text_and_markup", side_effect=Exception("DB error")):
        await commands.back_to_main_callback(update, MagicMock())

    # Must show error to user
    update.callback_query.edit_message_text.assert_called()


@pytest.mark.asyncio
async def test_subscriptions_callback_error_shows_message():
    """subscriptions_catalog_callback must edit_message_text on exception."""
    from src.bot.billing_commands import BillingCommands

    commands = BillingCommands(
        billing_service=AsyncMock(),
        subscription_service=AsyncMock(),
        payment_service=AsyncMock(),
    )

    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123

    with patch.object(commands, "_build_subscriptions_catalog", side_effect=Exception("DB error")):
        await commands.subscriptions_catalog_callback(update, MagicMock())

    update.callback_query.edit_message_text.assert_called()


@pytest.mark.asyncio
async def test_packages_callback_error_shows_message():
    """packages_catalog_callback must edit_message_text on exception."""
    from src.bot.billing_commands import BillingCommands

    commands = BillingCommands(
        billing_service=AsyncMock(),
        subscription_service=AsyncMock(),
        payment_service=AsyncMock(),
    )

    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123

    with patch.object(commands, "_build_packages_catalog", side_effect=Exception("DB error")):
        await commands.packages_catalog_callback(update, MagicMock())

    update.callback_query.edit_message_text.assert_called()


# =============================================================================
# Task 5.4: No assert in production code
# =============================================================================


@pytest.mark.asyncio
async def test_payment_service_repos_raises_runtime_error_not_assert():
    """PaymentService._repos must raise RuntimeError, not AssertionError, when repos missing."""
    from src.services.payments.payment_service import PaymentService

    service = PaymentService()  # no repos, no session_factory

    with pytest.raises(RuntimeError):
        async with service._repos() as _:
            pass


@pytest.mark.asyncio
async def test_payment_service_activate_subscription_raises_runtime_error():
    """_activate_subscription must raise RuntimeError when subscription_service is None."""
    from src.services.payments.payment_service import PaymentService

    service = PaymentService(
        purchase_repo=AsyncMock(),
        subscription_repo=AsyncMock(),
        balance_repo=AsyncMock(),
        package_repo=AsyncMock(),
    )

    with pytest.raises(RuntimeError):
        await service._activate_subscription(user_id=1, tier_id=1, payment_provider="test")


@pytest.mark.asyncio
async def test_billing_service_repos_raises_runtime_error_not_assert():
    """BillingService._repos must raise RuntimeError, not AssertionError, when repos missing."""
    from src.services.billing_service import BillingService

    service = BillingService()  # no repos, no session_factory

    with pytest.raises(RuntimeError):
        async with service._repos() as _:
            pass
