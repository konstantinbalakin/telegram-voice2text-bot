"""
Payment provider protocol and data models.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class PaymentType(str, Enum):
    """Payment type."""

    PACKAGE = "package"
    SUBSCRIPTION = "subscription"


class PaymentStatus(str, Enum):
    """Payment status."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PaymentRequest:
    """Request to create a payment."""

    user_id: int
    payment_type: PaymentType
    item_id: int
    amount: float
    currency: str
    description: str
    customer_email: Optional[str] = None


@dataclass
class PaymentResult:
    """Result of a payment operation."""

    success: bool
    provider_transaction_id: Optional[str] = None
    payment_url: Optional[str] = None
    error_message: Optional[str] = None


class PaymentProvider(Protocol):
    """Protocol for payment providers (Telegram Stars, YooKassa, etc.)."""

    @property
    def provider_name(self) -> str:
        """Unique name of the payment provider."""
        ...

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        """Create a payment with the provider."""
        ...

    async def handle_callback(self, data: dict) -> PaymentResult:
        """Handle callback/webhook from the provider."""
        ...

    async def verify_payment(self, transaction_id: str) -> PaymentResult:
        """Verify a payment status with the provider."""
        ...
