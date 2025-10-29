"""
Database models for Telegram Voice2Text Bot
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Date, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
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
    3. Updated after transcription: model_size, processing_time_seconds, transcription_length, updated_at
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

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # Stage 1
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )  # Stage 2, 3

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_records")

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
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    quota_seconds_added: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, completed, failed, refunded

    # Payment provider data
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, status={self.status})>"
