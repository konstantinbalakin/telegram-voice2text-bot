"""
Database models for Telegram Voice2Text Bot
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Date, Float, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.services.payments.base import (
    Currency,
    PaymentStatus,
    PurchaseStatus,
    SubscriptionStatus,
)


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class User(Base):
    """User model - represents a Telegram user."""

    __tablename__ = "users"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Telegram data
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Quota settings
    daily_quota_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_unlimited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Usage tracking
    today_usage_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reset_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_usage_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    usage_records: Mapped[list["Usage"]] = relationship(
        "Usage", back_populates="user", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Usage(Base):
    """Usage model - represents a single transcription request.

    Lifecycle stages:
    1. Created on file download: user_id, voice_file_id, created_at
    2. Updated after download: voice_duration_seconds, updated_at
    3. Updated after transcription: model_size, processing_time_seconds, transcription_length, llm_model, updated_at
    4. Updated after LLM refinement (hybrid mode only): llm_processing_time_seconds, updated_at
    """

    __tablename__ = "usage"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    # Voice message data
    voice_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Stage 2
    voice_file_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Stage 1

    # Transcription data (privacy: only store length, not text)
    transcription_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Stage 3
    processing_time_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)  # Stage 3

    # Whisper settings used
    model_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Stage 3
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # LLM refinement tracking (hybrid mode)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Stage 3
    llm_processing_time_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)  # Stage 4

    # Retranscription support (Phase 8)
    original_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    parent_usage_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usage.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )  # Stage 1
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )  # Stage 2, 3

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_records")
    transcription_state: Mapped[Optional["TranscriptionState"]] = relationship(
        "TranscriptionState", back_populates="usage", uselist=False, cascade="all, delete-orphan"
    )
    transcription_variants: Mapped[list["TranscriptionVariant"]] = relationship(
        "TranscriptionVariant", back_populates="usage", cascade="all, delete-orphan"
    )
    transcription_segments: Mapped[list["TranscriptionSegment"]] = relationship(
        "TranscriptionSegment", back_populates="usage", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Usage(id={self.id}, user_id={self.user_id}, duration={self.voice_duration_seconds}s)>"


class Transaction(Base):
    """Transaction model - represents a payment transaction (future billing)."""

    __tablename__ = "transactions"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    # Transaction data
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Amount in cents
    currency: Mapped[str] = mapped_column(String(3), default=Currency.USD, nullable=False)
    quota_seconds_added: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(String(50), default=PaymentStatus.PENDING, nullable=False)

    # Payment provider data
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, status={self.status})>"


class TranscriptionState(Base):
    """TranscriptionState model - current UI state for each transcription message."""

    __tablename__ = "transcription_states"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    usage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usage.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Current UI state
    active_mode: Mapped[str] = mapped_column(String(20), default="original", nullable=False)
    length_level: Mapped[str] = mapped_column(String(10), default="default", nullable=False)
    emoji_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timestamps_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # File message metadata
    is_file_message: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    usage: Mapped["Usage"] = relationship("Usage", back_populates="transcription_state")

    def __repr__(self) -> str:
        return (
            f"<TranscriptionState(id={self.id}, usage_id={self.usage_id}, "
            f"mode={self.active_mode}, message_id={self.message_id})>"
        )


class TranscriptionVariant(Base):
    """TranscriptionVariant model - cache of generated text variants."""

    __tablename__ = "transcription_variants"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    usage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usage.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Variant parameters (composite key)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    length_level: Mapped[str] = mapped_column(String(10), nullable=False)
    emoji_level: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamps_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Content
    text_content: Mapped[str] = mapped_column(String, nullable=False)

    # Generation metadata
    generated_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    processing_time_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    usage: Mapped["Usage"] = relationship("Usage", back_populates="transcription_variants")

    def __repr__(self) -> str:
        return (
            f"<TranscriptionVariant(id={self.id}, usage_id={self.usage_id}, "
            f"mode={self.mode}, length={self.length_level})>"
        )


class TranscriptionSegment(Base):
    """TranscriptionSegment model - segments with timestamps from faster-whisper."""

    __tablename__ = "transcription_segments"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    usage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usage.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Segment data
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[float] = mapped_column(nullable=False)
    end_time: Mapped[float] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    usage: Mapped["Usage"] = relationship("Usage", back_populates="transcription_segments")

    def __repr__(self) -> str:
        return (
            f"<TranscriptionSegment(id={self.id}, usage_id={self.usage_id}, "
            f"index={self.segment_index}, start={self.start_time:.2f})>"
        )


# =============================================================================
# Billing System Models
# =============================================================================


class BillingCondition(Base):
    """General and individual billing conditions (key-value with optional user override)."""

    __tablename__ = "billing_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<BillingCondition(id={self.id}, key={self.key}, user_id={self.user_id})>"


class SubscriptionTier(Base):
    """Subscription levels (e.g. Pro)."""

    __tablename__ = "subscription_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    daily_limit_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    prices: Mapped[list["SubscriptionPrice"]] = relationship(
        "SubscriptionPrice", back_populates="tier", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SubscriptionTier(id={self.id}, name={self.name})>"


class SubscriptionPrice(Base):
    """Prices for subscription tiers by period."""

    __tablename__ = "subscription_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_tiers.id"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_rub: Mapped[float] = mapped_column(Float, nullable=False)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    tier: Mapped["SubscriptionTier"] = relationship("SubscriptionTier", back_populates="prices")

    def __repr__(self) -> str:
        return f"<SubscriptionPrice(id={self.id}, tier_id={self.tier_id}, period={self.period})>"


class UserSubscription(Base):
    """Active user subscriptions."""

    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    tier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_tiers.id"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    payment_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    next_subscription_tier_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subscription_tiers.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=SubscriptionStatus.ACTIVE, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    tier: Mapped["SubscriptionTier"] = relationship("SubscriptionTier", foreign_keys=[tier_id])
    next_tier: Mapped[Optional["SubscriptionTier"]] = relationship(
        "SubscriptionTier", foreign_keys=[next_subscription_tier_id]
    )

    def __repr__(self) -> str:
        return (
            f"<UserSubscription(id={self.id}, user_id={self.user_id}, "
            f"tier_id={self.tier_id}, status={self.status})>"
        )


class MinutePackage(Base):
    """Minute packages catalog."""

    __tablename__ = "minute_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    minutes: Mapped[float] = mapped_column(Float, nullable=False)
    price_rub: Mapped[float] = mapped_column(Float, nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MinutePackage(id={self.id}, name={self.name}, minutes={self.minutes})>"


class UserMinuteBalance(Base):
    """User minute balances (bonus and package)."""

    __tablename__ = "user_minute_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    balance_type: Mapped[str] = mapped_column(String(20), nullable=False)
    minutes_remaining: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source_description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<UserMinuteBalance(id={self.id}, user_id={self.user_id}, "
            f"type={self.balance_type}, remaining={self.minutes_remaining})>"
        )


class DailyUsage(Base):
    """Daily usage tracking per user."""

    __tablename__ = "daily_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    minutes_used: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    minutes_from_daily: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    minutes_from_bonus: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    minutes_from_package: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<DailyUsage(id={self.id}, user_id={self.user_id}, "
            f"date={self.date}, minutes={self.minutes_used})>"
        )


class Purchase(Base):
    """Purchase history (packages and subscriptions)."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    purchase_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    payment_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=PurchaseStatus.PENDING, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Purchase(id={self.id}, user_id={self.user_id}, "
            f"type={self.purchase_type}, status={self.status})>"
        )


class DeductionLog(Base):
    """Detailed log of minute deductions by source."""

    __tablename__ = "deduction_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    usage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usage.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    minutes_deducted: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
