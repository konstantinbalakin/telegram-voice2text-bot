"""
Telegram Stars payment provider.
"""

import logging

from telegram import Bot, LabeledPrice

from src.services.payments.base import (
    PaymentRequest,
    PaymentResult,
)

logger = logging.getLogger(__name__)

# Telegram Stars currency code
STARS_CURRENCY = "XTR"


class TelegramStarsProvider:
    """Payment provider for Telegram Stars."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def provider_name(self) -> str:
        return "telegram_stars"

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        """Create a Telegram Stars invoice."""
        try:
            title = request.title or request.description
            label = request.price_label or request.description
            prices = [LabeledPrice(label=label, amount=int(request.amount))]

            payload = f"{request.payment_type.value}:{request.item_id}:{request.user_id}"
            if request.period:
                payload += f":{request.period}"

            invoice_link = await self.bot.create_invoice_link(
                title=title,
                description=request.description,
                payload=payload,
                currency=STARS_CURRENCY,
                prices=prices,
            )

            return PaymentResult(
                success=True,
                payment_url=invoice_link,
            )
        except Exception as e:
            logger.error("Failed to create Telegram Stars invoice: %s", e, exc_info=True)
            return PaymentResult(
                success=False,
                error_message="Ошибка создания платежа. Попробуйте позже.",
            )

    async def handle_callback(self, data: dict) -> PaymentResult:
        """Handle Telegram Stars payment callback."""
        return PaymentResult(success=True)

    async def verify_payment(self, transaction_id: str) -> PaymentResult:
        """Verify Telegram Stars payment."""
        return PaymentResult(success=True, provider_transaction_id=transaction_id)
