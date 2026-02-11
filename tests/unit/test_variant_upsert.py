"""Tests for TranscriptionVariantRepository.get_or_create_variant()."""

import pytest
from unittest.mock import patch, AsyncMock

from sqlalchemy.exc import IntegrityError

from src.storage.repositories import (
    UserRepository,
    UsageRepository,
    TranscriptionVariantRepository,
)


@pytest.mark.asyncio
async def test_get_or_create_returns_existing(async_session):
    """If variant already exists, return it with created=False."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)
    variant_repo = TranscriptionVariantRepository(async_session)

    user = await user_repo.create(telegram_id=100001)
    await async_session.flush()

    usage = await usage_repo.create(user_id=user.id, voice_file_id="file_exist")
    await async_session.flush()

    # Pre-create variant
    original = await variant_repo.create(
        usage_id=usage.id,
        mode="original",
        text_content="Hello world",
        length_level="default",
        emoji_level=0,
        timestamps_enabled=False,
        generated_by="transcription",
    )
    await async_session.flush()

    # get_or_create should return existing
    variant, created = await variant_repo.get_or_create_variant(
        usage_id=usage.id,
        mode="original",
        text_content="Different text",
        length_level="default",
        emoji_level=0,
        timestamps_enabled=False,
        generated_by="transcription",
    )

    assert created is False
    assert variant.id == original.id
    assert variant.text_content == "Hello world"


@pytest.mark.asyncio
async def test_get_or_create_creates_new(async_session):
    """If variant does not exist, create it with created=True."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)
    variant_repo = TranscriptionVariantRepository(async_session)

    user = await user_repo.create(telegram_id=100002)
    await async_session.flush()

    usage = await usage_repo.create(user_id=user.id, voice_file_id="file_new")
    await async_session.flush()

    variant, created = await variant_repo.get_or_create_variant(
        usage_id=usage.id,
        mode="structured",
        text_content="Structured text",
        length_level="default",
        emoji_level=1,
        timestamps_enabled=False,
        generated_by="llm",
        llm_model="deepseek-v3",
        processing_time_seconds=1.5,
    )

    assert created is True
    assert variant.text_content == "Structured text"
    assert variant.mode == "structured"
    assert variant.generated_by == "llm"
    assert variant.llm_model == "deepseek-v3"
    assert variant.processing_time_seconds == 1.5


@pytest.mark.asyncio
async def test_get_or_create_handles_race(async_session):
    """IntegrityError on create -> retry get returns existing variant."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)
    variant_repo = TranscriptionVariantRepository(async_session)

    user = await user_repo.create(telegram_id=100003)
    await async_session.flush()

    usage = await usage_repo.create(user_id=user.id, voice_file_id="file_race")
    await async_session.flush()

    # Pre-create the variant so the second get after rollback will find it
    existing = await variant_repo.create(
        usage_id=usage.id,
        mode="summary",
        text_content="Summary text",
        length_level="default",
        emoji_level=0,
        timestamps_enabled=False,
        generated_by="llm",
    )
    await async_session.flush()

    # Patch get_variant to return None on first call (simulating race),
    # then patch create to raise IntegrityError,
    # then get_variant returns the existing variant on retry.
    original_get = variant_repo.get_variant
    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None  # First call: not found
        return await original_get(**kwargs)  # Retry: found

    async def mock_create(*args, **kwargs):
        raise IntegrityError("UNIQUE constraint", params=None, orig=Exception())

    with patch.object(variant_repo, "get_variant", side_effect=mock_get):
        with patch.object(variant_repo, "create", side_effect=mock_create):
            # Also patch rollback since we're simulating
            with patch.object(async_session, "rollback", new_callable=AsyncMock):
                variant, created = await variant_repo.get_or_create_variant(
                    usage_id=usage.id,
                    mode="summary",
                    text_content="New summary",
                    length_level="default",
                    emoji_level=0,
                    timestamps_enabled=False,
                    generated_by="llm",
                )

    assert created is False
    assert variant.id == existing.id
    assert variant.text_content == "Summary text"
