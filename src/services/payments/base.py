"""
Payment provider protocol and data models.

Billing enums are centralised here to avoid circular imports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol


# ── Enums ────────────────────────────────────────────────────────────


class PaymentType(str, Enum):
    PACKAGE = "package"
    SUBSCRIPTION = "subscription"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SubscriptionPeriod(str, Enum):
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"

    @property
    def days(self) -> int:
        return _PERIOD_DAYS[self]


_PERIOD_DAYS = {
    SubscriptionPeriod.WEEK: 7,
    SubscriptionPeriod.MONTH: 30,
    SubscriptionPeriod.YEAR: 365,
}


class BalanceType(str, Enum):
    BONUS = "bonus"
    PACKAGE = "package"


class DeductionSource(str, Enum):
    DAILY = "daily"
    BONUS = "bonus"
    PACKAGE = "package"


class PurchaseStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class Currency(str, Enum):
    USD = "USD"
    RUB = "RUB"
    XTR = "XTR"


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class UserBalance:
    """User's minute balance breakdown."""

    daily_limit: float
    daily_used: float
    daily_remaining: float
    bonus_minutes: float
    package_minutes: float
    total_available: float
    bonus_expires_at: Optional[datetime] = field(default=None)
    package_expires_at: Optional[datetime] = field(default=None)


@dataclass
class PaymentRequest:
    """Request to create a payment."""

    user_id: int
    payment_type: PaymentType
    item_id: int
    amount: float
    currency: str
    description: str
    title: Optional[str] = None
    price_label: Optional[str] = None
    customer_email: Optional[str] = None


@dataclass
class PaymentResult:
    """Result of a payment operation."""

    success: bool
    provider_transaction_id: Optional[str] = None
    payment_url: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.success and self.error_message:
            raise ValueError("success=True is incompatible with error_message")


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
