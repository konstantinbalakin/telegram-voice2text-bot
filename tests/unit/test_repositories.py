"""
Tests for database repositories
"""

import pytest

from src.storage.repositories import UserRepository, UsageRepository


@pytest.mark.asyncio
async def test_user_repository_create(async_session):
    """Test creating a user via repository."""
    repo = UserRepository(async_session)

    user = await repo.create(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
    )

    assert user.id is not None
    assert user.telegram_id == 123456789
    assert user.username == "testuser"


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
