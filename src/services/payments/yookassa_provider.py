"""
YooKassa payment provider.

Note: Requires `yookassa` package to be installed for production use.
This module can work in mock mode without the package for testing.
"""

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
                "customer": {"email": "customer@example.com"},
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

            payment_data = {
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
                "receipt": receipt,
            }

            payment = Payment.create(payment_data, idempotency_key)

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
        """Handle YooKassa webhook notification."""
        try:
            event = data.get("event", "")
            payment_obj = data.get("object", {})
            payment_id = payment_obj.get("id", "")

            if event == "payment.succeeded":
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

            payment = Payment.find_one(transaction_id)

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
        """Parse payment metadata from YooKassa payment object."""
        try:
            return {
                "payment_type": metadata.get("payment_type", ""),
                "item_id": int(metadata.get("item_id", 0)),
                "user_id": int(metadata.get("user_id", 0)),
            }
        except (ValueError, TypeError):
            return None
