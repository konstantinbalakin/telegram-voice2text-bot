"""
Tests for database repositories
"""

import pytest
from datetime import date, datetime

from src.storage.repositories import UserRepository, UsageRepository, TransactionRepository


@pytest.mark.asyncio
async def test_user_repository_create(async_session):
    """Test creating a user via repository."""
    repo = UserRepository(async_session)

    user = await repo.create(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        daily_quota_seconds=60,
    )

    assert user.id is not None
    assert user.telegram_id == 123456789
    assert user.username == "testuser"
    assert user.daily_quota_seconds == 60


@pytest.mark.asyncio
async def test_user_repository_get_by_telegram_id(async_session):
    """Test getting user by Telegram ID."""
    repo = UserRepository(async_session)

    # Create user
    created_user = await repo.create(
        telegram_id=987654321,
        username="findme",
    )
    await async_session.commit()

    # Find user
    found_user = await repo.get_by_telegram_id(987654321)

    assert found_user is not None
    assert found_user.id == created_user.id
    assert found_user.telegram_id == 987654321
    assert found_user.username == "findme"


@pytest.mark.asyncio
async def test_user_repository_update_usage(async_session):
    """Test updating user usage."""
    repo = UserRepository(async_session)

    user = await repo.create(telegram_id=111222333)
    await async_session.commit()

    # Update usage
    updated_user = await repo.update_usage(user, duration_seconds=30)
    await async_session.commit()

    assert updated_user.today_usage_seconds == 30
    assert updated_user.total_usage_seconds == 30

    # Update again
    await repo.update_usage(updated_user, duration_seconds=20)
    await async_session.commit()

    assert updated_user.today_usage_seconds == 50
    assert updated_user.total_usage_seconds == 50


@pytest.mark.asyncio
async def test_user_repository_reset_daily_quota(async_session):
    """Test resetting user's daily quota."""
    repo = UserRepository(async_session)

    user = await repo.create(telegram_id=444555666)
    await repo.update_usage(user, duration_seconds=50)
    await async_session.commit()

    # Reset quota
    reset_user = await repo.reset_daily_quota(user)
    await async_session.commit()

    assert reset_user.today_usage_seconds == 0
    assert reset_user.last_reset_date == date.today()
    assert reset_user.total_usage_seconds == 50  # Total should remain


@pytest.mark.asyncio
async def test_usage_repository_create(async_session):
    """Test creating usage record via repository."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    # Create user first
    user = await user_repo.create(telegram_id=777888999)
    await async_session.commit()

    # Create usage
    usage = await usage_repo.create(
        user_id=user.id,
        voice_duration_seconds=45,
        voice_file_id="test_file_123",
        transcription_length=29,  # Length of "This is a test transcription"
        model_size="base",
        processing_time_seconds=8.5,
        language="ru",
    )
    await async_session.commit()

    assert usage.id is not None
    assert usage.user_id == user.id
    assert usage.voice_duration_seconds == 45
    assert usage.transcription_length == 29


@pytest.mark.asyncio
async def test_usage_repository_get_by_user_id(async_session):
    """Test getting usage records by user ID."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    # Create user
    user = await user_repo.create(telegram_id=111000111)
    await async_session.commit()

    # Create multiple usage records
    for i in range(5):
        await usage_repo.create(
            user_id=user.id,
            voice_duration_seconds=10 * (i + 1),
            voice_file_id=f"file_{i}",
            transcription_length=6 + i,  # Length varies
            model_size="base",
        )
    await async_session.commit()

    # Get usage records
    usages = await usage_repo.get_by_user_id(user.id, limit=3)

    assert len(usages) == 3
    # Should be ordered by created_at desc (most recent first)
    assert usages[0].voice_file_id == "file_4"


@pytest.mark.asyncio
async def test_transaction_repository_create(async_session):
    """Test creating transaction via repository."""
    user_repo = UserRepository(async_session)
    tx_repo = TransactionRepository(async_session)

    # Create user first
    user = await user_repo.create(telegram_id=222333444)
    await async_session.commit()

    # Create transaction
    transaction = await tx_repo.create(
        user_id=user.id,
        amount=1000,
        currency="USD",
        quota_seconds_added=7200,
        provider="stripe",
        provider_transaction_id="ch_123456",
    )
    await async_session.commit()

    assert transaction.id is not None
    assert transaction.user_id == user.id
    assert transaction.amount == 1000
    assert transaction.status == "pending"


@pytest.mark.asyncio
async def test_transaction_repository_mark_completed(async_session):
    """Test marking transaction as completed."""
    user_repo = UserRepository(async_session)
    tx_repo = TransactionRepository(async_session)

    # Create user and transaction
    user = await user_repo.create(telegram_id=555666777)
    transaction = await tx_repo.create(
        user_id=user.id,
        amount=500,
        currency="USD",
        quota_seconds_added=3600,
    )
    await async_session.commit()

    # Mark as completed
    completed_tx = await tx_repo.mark_completed(transaction)
    await async_session.commit()

    assert completed_tx.status == "completed"
    assert completed_tx.completed_at is not None


@pytest.mark.asyncio
async def test_transaction_repository_mark_failed(async_session):
    """Test marking transaction as failed."""
    user_repo = UserRepository(async_session)
    tx_repo = TransactionRepository(async_session)

    # Create user and transaction
    user = await user_repo.create(telegram_id=888999000)
    transaction = await tx_repo.create(
        user_id=user.id,
        amount=300,
        currency="USD",
        quota_seconds_added=1800,
    )
    await async_session.commit()

    # Mark as failed
    failed_tx = await tx_repo.mark_failed(transaction)
    await async_session.commit()

    assert failed_tx.status == "failed"
    assert failed_tx.completed_at is not None
