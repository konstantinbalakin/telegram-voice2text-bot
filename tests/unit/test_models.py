"""
Tests for database models
"""

import pytest
from datetime import date, datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.storage.models import User, Usage, Transaction


@pytest.mark.asyncio
async def test_user_model_creation(async_session):
    """Test creating a user model."""
    user = User(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        daily_quota_seconds=60,
        is_unlimited=False,
        today_usage_seconds=0,
        last_reset_date=date.today(),
        total_usage_seconds=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    async_session.add(user)
    await async_session.commit()

    assert user.id is not None
    assert user.telegram_id == 123456789
    assert user.username == "testuser"
    assert user.daily_quota_seconds == 60
    assert user.is_unlimited is False


@pytest.mark.asyncio
async def test_usage_model_creation(async_session):
    """Test creating a usage model."""
    # Create user first
    user = User(
        telegram_id=123456789,
        username="testuser",
        daily_quota_seconds=60,
        is_unlimited=False,
        today_usage_seconds=0,
        last_reset_date=date.today(),
        total_usage_seconds=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    async_session.add(user)
    await async_session.flush()

    # Create usage
    usage = Usage(
        user_id=user.id,
        voice_duration_seconds=30,
        voice_file_id="file_123",
        transcription_text="Test transcription",
        processing_time_seconds=5.5,
        model_size="base",
        language="ru",
        created_at=datetime.utcnow(),
    )

    async_session.add(usage)
    await async_session.commit()

    assert usage.id is not None
    assert usage.user_id == user.id
    assert usage.voice_duration_seconds == 30
    assert usage.transcription_text == "Test transcription"
    assert usage.model_size == "base"


@pytest.mark.asyncio
async def test_transaction_model_creation(async_session):
    """Test creating a transaction model."""
    # Create user first
    user = User(
        telegram_id=123456789,
        username="testuser",
        daily_quota_seconds=60,
        is_unlimited=False,
        today_usage_seconds=0,
        last_reset_date=date.today(),
        total_usage_seconds=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    async_session.add(user)
    await async_session.flush()

    # Create transaction
    transaction = Transaction(
        user_id=user.id,
        amount=500,
        currency="USD",
        quota_seconds_added=3600,
        status="pending",
        provider="telegram_payments",
        provider_transaction_id="tx_123",
        created_at=datetime.utcnow(),
    )

    async_session.add(transaction)
    await async_session.commit()

    assert transaction.id is not None
    assert transaction.user_id == user.id
    assert transaction.amount == 500
    assert transaction.quota_seconds_added == 3600
    assert transaction.status == "pending"


@pytest.mark.asyncio
async def test_user_usage_relationship(async_session):
    """Test relationship between User and Usage models."""
    # Create user
    user = User(
        telegram_id=123456789,
        username="testuser",
        daily_quota_seconds=60,
        is_unlimited=False,
        today_usage_seconds=0,
        last_reset_date=date.today(),
        total_usage_seconds=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    async_session.add(user)
    await async_session.flush()

    # Create multiple usage records
    for i in range(3):
        usage = Usage(
            user_id=user.id,
            voice_duration_seconds=10 * (i + 1),
            voice_file_id=f"file_{i}",
            transcription_text=f"Test {i}",
            model_size="base",
            created_at=datetime.utcnow(),
        )
        async_session.add(usage)

    await async_session.commit()

    # Reload user with relationships eagerly loaded
    result = await async_session.execute(
        select(User).where(User.id == user.id).options(selectinload(User.usage_records))
    )
    user = result.scalar_one()

    # Check relationship
    assert len(user.usage_records) == 3
    assert user.usage_records[0].voice_duration_seconds in [10, 20, 30]
