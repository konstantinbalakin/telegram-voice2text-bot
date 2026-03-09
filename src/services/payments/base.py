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

_PERIOD_LABELS = {
    SubscriptionPeriod.WEEK: "Неделя",
    SubscriptionPeriod.MONTH: "Месяц",
    SubscriptionPeriod.YEAR: "Год",
}


def period_label(period: str) -> str:
    """Convert period code to human-readable Russian label."""
    try:
        return _PERIOD_LABELS[SubscriptionPeriod(period)]
    except (ValueError, KeyError):
        return period


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


@dataclass(frozen=True)
class UserBalance:
    """User's minute balance breakdown.

    daily_remaining and total_available are computed properties.
    """

    daily_limit: float
    daily_used: float
    bonus_minutes: float
    package_minutes: float
    bonus_expires_at: Optional[datetime] = field(default=None)
    package_expires_at: Optional[datetime] = field(default=None)

    def __post_init__(self) -> None:
        if self.daily_limit < 0:
            raise ValueError(f"daily_limit must be >= 0, got {self.daily_limit}")
        if self.daily_used < 0:
            raise ValueError(f"daily_used must be >= 0, got {self.daily_used}")
        if self.bonus_minutes < 0:
            raise ValueError(f"bonus_minutes must be >= 0, got {self.bonus_minutes}")
        if self.package_minutes < 0:
            raise ValueError(f"package_minutes must be >= 0, got {self.package_minutes}")

    @property
    def daily_remaining(self) -> float:
        return max(0.0, self.daily_limit - self.daily_used)

    @property
    def total_available(self) -> float:
        return self.daily_remaining + self.bonus_minutes + self.package_minutes


@dataclass
class PaymentRequest:
    """Request to create a payment."""

    user_id: int
    payment_type: PaymentType
    item_id: int
    amount: int
    currency: Currency
    description: str
    title: Optional[str] = None
    price_label: Optional[str] = None
    customer_email: Optional[str] = None
    period: Optional[str] = None


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


def parse_payment_payload(payload: str) -> Optional[dict]:
    """Parse payment payload string into components.

    Payload format:
        {payment_type}:{item_id}:{user_id}              — for packages
        {payment_type}:{item_id}:{user_id}:{period}     — for subscriptions

    Returns:
        Parsed dict with keys: payment_type, item_id, user_id, period (optional).
        None on malformed payload.
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        parts = payload.split(":")
        if len(parts) < 3 or len(parts) > 4:
            logger.warning("Malformed payment payload (expected 3-4 parts): %r", payload)
            return None
        result: dict = {
            "payment_type": parts[0],
            "item_id": int(parts[1]),
            "user_id": int(parts[2]),
        }
        if len(parts) == 4:
            result["period"] = parts[3]
        return result
    except (ValueError, IndexError) as e:
        logger.warning("Failed to parse payment payload %r: %s", payload, e)
        return None
