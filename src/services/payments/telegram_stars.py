"""
Telegram Stars payment provider.
"""

import logging
from typing import Optional

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
            prices = [LabeledPrice(label=request.description, amount=int(request.amount))]

            invoice_link = await self.bot.create_invoice_link(
                title=request.description,
                description=request.description,
                payload=f"{request.payment_type.value}:{request.item_id}:{request.user_id}",
                currency=STARS_CURRENCY,
                prices=prices,
            )

            return PaymentResult(
                success=True,
                payment_url=invoice_link,
            )
        except Exception as e:
            logger.error(f"Failed to create Telegram Stars invoice: {e}")
            return PaymentResult(
                success=False,
                error_message=str(e),
            )

    async def handle_callback(self, data: dict) -> PaymentResult:
        """Handle Telegram Stars payment callback (pre_checkout_query or successful_payment)."""
        return PaymentResult(success=True)

    async def verify_payment(self, transaction_id: str) -> PaymentResult:
        """Verify Telegram Stars payment. Stars payments are verified by Telegram."""
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
                logger.warning(f"Malformed Stars payload (expected 3 parts): {payload!r}")
                return None
            return {
                "payment_type": parts[0],
                "item_id": int(parts[1]),
                "user_id": int(parts[2]),
            }
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse Stars payload {payload!r}: {e}")
            return None
