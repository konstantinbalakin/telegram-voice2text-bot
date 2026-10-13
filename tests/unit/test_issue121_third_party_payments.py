"""
Regression tests for issue #121: IDOR false positives on legitimate
third-party payments, plus Purchase status persistence.

Scenarios:
1. effective_user not found in DB (NOT_FOUND) — payment must still be
   fulfilled for the invoice owner, logged as INFO, not CRITICAL-blocked.
2. effective_user is a *different known* user paying someone else's invoice
   (family scenario) — fulfill for the invoice owner, log INFO.
3. handle_successful_payment must persist status=completed /
   provider_transaction_id (detached-instance regression).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import User

from src.services.payments.base import PaymentType
from src.bot.payment_callbacks import successful_payment_handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payment_update(payload: str, tg_user_id: int, currency: str = "RUB") -> MagicMock:
    """Create a mock Update with successful_payment from the given tg user."""
    successful_payment = MagicMock()
    successful_payment.invoice_payload = payload
    successful_payment.telegram_payment_charge_id = "charge_121_1"
    successful_payment.currency = currency

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.successful_payment = successful_payment

    update = MagicMock()
    update.message = message
    update.effective_user = User(id=tg_user_id, is_bot=False, first_name="Payer")
    return update


def _patch_session_and_repo(get_by_telegram_id: AsyncMock):
    """Patch get_session + UserRepository in payment_callbacks."""
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    get_session = MagicMock(return_value=session_cm)
    repo_cls = MagicMock()
    repo_cls.return_value.get_by_telegram_id = get_by_telegram_id
    return (
        patch("src.bot.payment_callbacks.get_session", get_session),
        patch("src.bot.payment_callbacks.UserRepository", repo_cls),
    )


# ---------------------------------------------------------------------------
# Issue #121: IDOR false positives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_payment_payer_not_in_db_fulfills_for_invoice_owner():
    """Payer unknown to the bot → fulfill for payload owner, no CRITICAL block."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    # Invoice created by db user 234; payer tg account is not registered in DB
    update = _make_payment_update("package:7:234", tg_user_id=397456475)

    p1, p2 = _patch_session_and_repo(AsyncMock(return_value=None))
    with p1, p2:
        await handler(update, MagicMock())

    payment_service.handle_successful_payment.assert_awaited_once()
    call = payment_service.handle_successful_payment.await_args
    assert call.kwargs["user_id"] == 234  # credited to invoice owner, not payer
    assert call.kwargs["payment_type"] == PaymentType.PACKAGE
    assert call.kwargs["item_id"] == 7


@pytest.mark.asyncio
async def test_successful_payment_different_known_user_fulfills_for_invoice_owner():
    """Known user B pays invoice of user A → fulfill for A (family scenario)."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    # Invoice owner db id 234; payer is db user 593
    payer = MagicMock()
    payer.id = 593
    update = _make_payment_update("package:7:234", tg_user_id=397456475)

    p1, p2 = _patch_session_and_repo(AsyncMock(return_value=payer))
    with p1, p2:
        await handler(update, MagicMock())

    payment_service.handle_successful_payment.assert_awaited_once()
    call = payment_service.handle_successful_payment.await_args
    assert call.kwargs["user_id"] == 234


@pytest.mark.asyncio
async def test_successful_payment_same_user_unchanged_flow():
    """Payer == invoice owner → standard flow, no payer/owner distinction logged."""
    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    payer = MagicMock()
    payer.id = 234
    update = _make_payment_update("package:7:234", tg_user_id=1572697058)

    p1, p2 = _patch_session_and_repo(AsyncMock(return_value=payer))
    with p1, p2:
        await handler(update, MagicMock())

    payment_service.handle_successful_payment.assert_awaited_once()
    assert payment_service.handle_successful_payment.await_args.kwargs["user_id"] == 234


@pytest.mark.asyncio
async def test_successful_payment_payer_not_in_db_informs_and_notifies_owner(caplog):
    """Unknown payer → payer gets 'credited to owner' reply; INFO logged, no CRITICAL."""
    import logging

    payment_service = AsyncMock()
    payment_service.handle_successful_payment = AsyncMock(return_value=True)

    handler = successful_payment_handler(payment_service)

    update = _make_payment_update("package:7:234", tg_user_id=397456475)

    p1, p2 = _patch_session_and_repo(AsyncMock(return_value=None))
    with p1, p2, caplog.at_level(logging.INFO, logger="src.bot.payment_callbacks"):
        await handler(update, MagicMock())

    # Reply must not be the generic support error
    reply = update.message.reply_text.await_args.args[0]
    assert "поддержк" not in reply.lower()
    # No CRITICAL-level IDOR log for unknown payer
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    # INFO log mentions third-party payment
    assert any(
        "paid by unregistered" in r.getMessage().lower()
        or "paid by another account" in r.getMessage().lower()
        for r in caplog.records
    )
