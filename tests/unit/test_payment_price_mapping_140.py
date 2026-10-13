"""it-001 regression: provider → price/currency mapping must not swap (#140).

Полигон: рублёвая покупка ушла с ценой 90 stars → 0.9₽. Причина —
перепутанная распаковка кортежа (amount_rub, amount_stars) в
_do_buy_subscription при добавлении YooKassa-ветки (волна 5).
"""

from unittest.mock import AsyncMock, MagicMock


from src.bot.payment_callbacks import PaymentCallbackHandlers
from tests.unit.test_payment_confirm_ux_140 import _make_update

PRICE = (18000, 90)  # (rub kopecks, stars) — месяц Pro со стенда


def _handlers() -> tuple[PaymentCallbackHandlers, MagicMock]:
    payment_service = MagicMock()
    payment_service.create_payment = AsyncMock(
        return_value=MagicMock(success=True, payment_url="https://t.me/pay")
    )
    sub = AsyncMock()
    sub.preview_purchase = AsyncMock(return_value=None)  # без active — сразу платёж
    handlers = PaymentCallbackHandlers(
        payment_service=payment_service, subscription_service=sub
    )
    handlers._get_db_user_id = AsyncMock(return_value=1)
    handlers._get_subscription_price = AsyncMock(return_value=PRICE)
    handlers._get_tier_name = AsyncMock(return_value="Pro")
    handlers._get_subscription_description = AsyncMock(return_value=None)
    return handlers, payment_service


async def test_stars_payment_uses_star_price():
    handlers, payment_service = _handlers()
    update = _make_update("sub_stars:1:month")
    await handlers.buy_subscription_stars_callback(update, context=AsyncMock())
    request = payment_service.create_payment.call_args.kwargs["request"]
    assert request.amount == PRICE[1]  # stars
    assert request.currency.value == "XTR"


async def test_rub_payment_uses_kopeck_price():
    handlers, payment_service = _handlers()
    update = _make_update("sub_pay:1:month")  # yookassa-путь
    from src.bot.payment_callbacks import PaymentCallbackHandlers as _P

    # прямой вызов внутреннего пути с yookassa (как делает колбэк-роутер)
    await _P._do_buy_subscription(
        handlers, update, tier_id=1, period="month", provider_name="yookassa"
    )
    request = payment_service.create_payment.call_args.kwargs["request"]
    assert request.amount == PRICE[0]  # копейки (18000 = 180₽)
    assert request.currency.value == "RUB"
