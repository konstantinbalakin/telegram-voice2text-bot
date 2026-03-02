"""
YooKassa payment provider.

Integrates with YooKassa (Russian payment gateway) for processing payments
via bank cards, SBP, and other methods. Requires the `yookassa` package.
Sync SDK calls are wrapped in asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
import logging
import uuid
from typing import Optional

from src.services.payments.base import (
    PaymentRequest,
    PaymentResult,
)

logger = logging.getLogger(__name__)


class YooKassaProvider:
    """Payment provider for YooKassa (Russian payment gateway).

    Supports: bank cards, SBP, recurring payments, 54-FZ receipts.
    Sync SDK calls are wrapped in asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(
        self,
        shop_id: str,
        secret_key: str,
        return_url: str = "",
    ):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.return_url = return_url
        self._configured = False

        try:
            from yookassa import Configuration  # type: ignore[import-not-found]

            Configuration.account_id = shop_id
            Configuration.secret_key = secret_key
            self._configured = True
            logger.info("YooKassa SDK configured successfully")
        except ImportError:
            logger.warning("yookassa package not installed, YooKassa payments unavailable")

    @property
    def provider_name(self) -> str:
        return "yookassa"

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        """Create a YooKassa payment."""
        if not self._configured:
            return PaymentResult(
                success=False,
                error_message="YooKassa not configured (missing yookassa package)",
            )

        try:
            from yookassa import Payment  # type: ignore[import-not-found]

            idempotency_key = str(uuid.uuid4())

            receipt = {
                "customer": {"email": request.customer_email} if request.customer_email else {},
                "items": [
                    {
                        "description": request.description,
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{request.amount:.2f}",
                            "currency": "RUB",
                        },
                        "vat_code": 1,
                        "payment_subject": "service",
                        "payment_mode": "full_payment",
                    }
                ],
            }

            payment_data: dict = {
                "amount": {
                    "value": f"{request.amount:.2f}",
                    "currency": "RUB",
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": self.return_url,
                },
                "capture": True,
                "description": request.description,
                "metadata": {
                    "payment_type": request.payment_type.value,
                    "item_id": str(request.item_id),
                    "user_id": str(request.user_id),
                },
            }

            # Only include receipt if customer email is provided (54-FZ requirement)
            if request.customer_email:
                payment_data["receipt"] = receipt

            # Wrap sync SDK call in asyncio.to_thread to avoid blocking event loop
            payment = await asyncio.to_thread(Payment.create, payment_data, idempotency_key)

            confirmation_url = None
            if payment.confirmation:
                confirmation_url = payment.confirmation.confirmation_url

            return PaymentResult(
                success=True,
                provider_transaction_id=payment.id,
                payment_url=confirmation_url,
            )
        except Exception as e:
            logger.error(f"Failed to create YooKassa payment: {e}")
            return PaymentResult(
                success=False,
                error_message=str(e),
            )

    async def handle_callback(self, data: dict) -> PaymentResult:
        """Handle YooKassa webhook notification.

        Verifies the payment via Payment.find_one() to prevent spoofed callbacks.
        """
        try:
            event = data.get("event", "")
            payment_obj = data.get("object", {})
            payment_id = payment_obj.get("id", "")

            if event == "payment.succeeded":
                # Verify payment status with YooKassa API to prevent spoofed webhooks
                if self._configured and payment_id:
                    verification = await self.verify_payment(payment_id)
                    if not verification.success:
                        logger.warning(
                            f"Webhook verification failed for payment {payment_id}: "
                            f"{verification.error_message}"
                        )
                        return verification

                return PaymentResult(
                    success=True,
                    provider_transaction_id=payment_id,
                )
            elif event == "payment.canceled":
                return PaymentResult(
                    success=False,
                    provider_transaction_id=payment_id,
                    error_message="Payment cancelled",
                )
            else:
                return PaymentResult(
                    success=False,
                    error_message=f"Unknown event: {event}",
                )
        except Exception as e:
            logger.error(f"Failed to handle YooKassa callback: {e}")
            return PaymentResult(success=False, error_message=str(e))

    async def verify_payment(self, transaction_id: str) -> PaymentResult:
        """Verify payment status with YooKassa."""
        if not self._configured:
            return PaymentResult(
                success=False,
                error_message="YooKassa not configured",
            )

        try:
            from yookassa import Payment  # type: ignore[import-not-found]

            # Wrap sync SDK call in asyncio.to_thread to avoid blocking event loop
            payment = await asyncio.to_thread(Payment.find_one, transaction_id)

            if payment.status == "succeeded":
                return PaymentResult(
                    success=True,
                    provider_transaction_id=transaction_id,
                )
            else:
                return PaymentResult(
                    success=False,
                    provider_transaction_id=transaction_id,
                    error_message=f"Payment status: {payment.status}",
                )
        except Exception as e:
            logger.error(f"Failed to verify YooKassa payment: {e}")
            return PaymentResult(success=False, error_message=str(e))

    @staticmethod
    def parse_metadata(metadata: dict) -> Optional[dict]:
        """Parse payment metadata from YooKassa payment object.

        Returns:
            Parsed dict or None on malformed metadata.
        """
        try:
            payment_type = metadata.get("payment_type")
            item_id_raw = metadata.get("item_id")
            user_id_raw = metadata.get("user_id")

            if not payment_type or item_id_raw is None or user_id_raw is None:
                logger.warning(f"Incomplete YooKassa metadata: {metadata}")
                return None

            return {
                "payment_type": payment_type,
                "item_id": int(item_id_raw),
                "user_id": int(user_id_raw),
            }
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse YooKassa metadata {metadata}: {e}")
            return None
