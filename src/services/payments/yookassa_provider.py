"""
YooKassa payment provider (Native Telegram Payments).

Uses Telegram Payments API with provider_token from BotFather.
Works identically to TelegramStarsProvider but with currency=RUB.
"""

import logging
from typing import Optional

from telegram import Bot, LabeledPrice

from src.services.payments.base import (
    PaymentRequest,
    PaymentResult,
)

logger = logging.getLogger(__name__)


class YooKassaProvider:
    """Payment provider for YooKassa via native Telegram Payments.

    Uses sendInvoice with provider_token and currency=RUB.
    """

    def __init__(self, bot: Bot, provider_token: str):
        self.bot = bot
        self.provider_token = provider_token

    @property
    def provider_name(self) -> str:
        return "yookassa"

    # Минимальная сумма для RUB в Telegram Payments API (в копейках)
    # https://core.telegram.org/bots/payments/currencies.json → RUB.min_amount
    MIN_RUB_AMOUNT = 8773

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        """Create a YooKassa invoice via Telegram Payments API."""
        try:
            amount = int(request.amount)

            if amount < self.MIN_RUB_AMOUNT:
                min_rub = self.MIN_RUB_AMOUNT / 100
                actual_rub = amount / 100
                logger.error(
                    "Amount %d (%s RUB) is below Telegram minimum %d (%s RUB) for currency RUB",
                    amount,
                    actual_rub,
                    self.MIN_RUB_AMOUNT,
                    min_rub,
                )
                return PaymentResult(
                    success=False,
                    error_message=(
                        f"Сумма {actual_rub} ₽ ниже минимальной для Telegram Payments ({min_rub} ₽)"
                    ),
                )

            title = request.title or request.description
            label = request.price_label or request.description
            prices = [LabeledPrice(label=label, amount=amount)]

            logger.info(
                "Creating YooKassa invoice: amount=%d currency=RUB user_id=%s item_id=%s",
                amount,
                request.user_id,
                request.item_id,
            )

            invoice_link = await self.bot.create_invoice_link(
                title=title,
                description=request.description,
                payload=f"{request.payment_type.value}:{request.item_id}:{request.user_id}",
                provider_token=self.provider_token,
                currency="RUB",
                prices=prices,
            )

            return PaymentResult(
                success=True,
                payment_url=invoice_link,
            )
        except Exception as e:
            logger.error(f"Failed to create YooKassa invoice: {e}")
            return PaymentResult(
                success=False,
                error_message=str(e),
            )

    async def handle_callback(self, data: dict) -> PaymentResult:
        """Handle YooKassa payment callback.

        Native Telegram Payments are fully managed by Telegram.
        The bot receives pre_checkout_query and successful_payment updates directly.
        """
        return PaymentResult(success=True)

    async def verify_payment(self, transaction_id: str) -> PaymentResult:
        """Verify YooKassa payment. Native Telegram Payments are verified by Telegram."""
        return PaymentResult(success=True, provider_transaction_id=transaction_id)

    @staticmethod
    def parse_payload(payload: str) -> Optional[dict]:
        """Parse payment payload string into components.

        Payload format: {payment_type}:{item_id}:{user_id}

        Returns:
            Parsed dict or None on malformed payload.
        """
        try:
            parts = payload.split(":")
            if len(parts) != 3:
                logger.warning(f"Malformed YooKassa payload (expected 3 parts): {payload!r}")
                return None
            return {
                "payment_type": parts[0],
                "item_id": int(parts[1]),
                "user_id": int(parts[2]),
            }
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse YooKassa payload {payload!r}: {e}")
            return None
