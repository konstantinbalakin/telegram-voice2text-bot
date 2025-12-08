"""
Database models for Telegram Voice2Text Bot
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Date, ForeignKey
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
        DateTime, default=datetime.utcnow, nullable=False
    )  # Stage 1
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    usage: Mapped["Usage"] = relationship("Usage", back_populates="transcription_segments")

    def __repr__(self) -> str:
        return (
            f"<TranscriptionSegment(id={self.id}, usage_id={self.usage_id}, "
            f"index={self.segment_index}, start={self.start_time:.2f})>"
        )
