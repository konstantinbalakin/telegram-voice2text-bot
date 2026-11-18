"""Tests for UsageRepository period statistics and language persistence.

In-memory SQLite via conftest fixtures (async_engine / async_session).
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.storage.models import Usage
from src.storage.repositories import UsageRepository, UserRepository


@pytest.mark.asyncio
async def test_get_period_stats_filters_old_records(async_session):
    """Записи старше окна (31 день) не попадают в статистику периода."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    user = await user_repo.create(telegram_id=111111001)
    await async_session.commit()

    now = datetime.now(timezone.utc)

    fresh_ru = Usage(
        user_id=user.id,
        voice_file_id="fresh_ru",
        voice_duration_seconds=60,
        transcription_length=100,
        language="ru",
        created_at=now - timedelta(days=1),
    )
    fresh_en = Usage(
        user_id=user.id,
        voice_file_id="fresh_en",
        voice_duration_seconds=30,
        transcription_length=50,
        language="en",
        created_at=now - timedelta(days=2),
    )
    old_ru = Usage(
        user_id=user.id,
        voice_file_id="old_ru",
        voice_duration_seconds=600,
        transcription_length=999,
        language="ru",
        created_at=now - timedelta(days=31),
    )
    async_session.add_all([fresh_ru, fresh_en, old_ru])
    await async_session.commit()

    stats = await usage_repo.get_period_stats(user.id, now - timedelta(days=30))

    assert stats.total_count == 2
    assert stats.total_duration_seconds == 90.0
    # Order: count desc, ties broken by language code asc (deterministic)
    assert stats.languages == [("en", 1), ("ru", 1)]


@pytest.mark.asyncio
async def test_get_period_stats_excludes_child_records(async_session):
    """Дочерние записи (parent_usage_id) исключаются из статистики."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    user = await user_repo.create(telegram_id=111111002)
    await async_session.commit()

    parent = await usage_repo.create(
        user_id=user.id,
        voice_file_id="parent",
        voice_duration_seconds=120,
        transcription_length=200,
        language="ru",
    )
    child = await usage_repo.create(
        user_id=user.id,
        voice_file_id="child",
        voice_duration_seconds=120,
        transcription_length=150,
        language="en",
        parent_usage_id=parent.id,
    )
    assert child.parent_usage_id == parent.id
    await async_session.commit()

    stats = await usage_repo.get_period_stats(
        user.id, datetime.now(timezone.utc) - timedelta(days=30)
    )

    assert stats.total_count == 1
    assert stats.languages == [("ru", 1)]


@pytest.mark.asyncio
async def test_get_period_stats_excludes_incomplete_records(async_session):
    """Записи без transcription_length (незавершённые) исключаются."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    user = await user_repo.create(telegram_id=111111003)
    await async_session.commit()

    complete = await usage_repo.create(
        user_id=user.id,
        voice_file_id="complete",
        voice_duration_seconds=45,
        transcription_length=80,
        language="ru",
    )
    incomplete = await usage_repo.create(
        user_id=user.id,
        voice_file_id="incomplete",
        voice_duration_seconds=45,
        language="ru",
    )
    assert incomplete.transcription_length is None
    await async_session.commit()

    stats = await usage_repo.get_period_stats(
        user.id, datetime.now(timezone.utc) - timedelta(days=30)
    )

    assert stats.total_count == 1
    assert stats.total_duration_seconds == 45.0
    assert stats.languages == [(complete.language, 1)]


@pytest.mark.asyncio
async def test_get_period_stats_empty_window(async_session):
    """Нет записей в окне — нулевые счётчики и пустой список языков."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    user = await user_repo.create(telegram_id=111111004)
    await async_session.commit()

    stats = await usage_repo.get_period_stats(
        user.id, datetime.now(timezone.utc) - timedelta(days=30)
    )

    assert stats.total_count == 0
    assert stats.total_duration_seconds == 0.0
    assert stats.languages == []


@pytest.mark.asyncio
async def test_create_and_update_persist_language(async_session):
    """create() и update() пишут language; update без language не затирает значение."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    user = await user_repo.create(telegram_id=111111005)
    await async_session.commit()

    created = await usage_repo.create(
        user_id=user.id,
        voice_file_id="with_language",
        voice_duration_seconds=10,
        language="kk",
    )
    assert created.language == "kk"
    await async_session.commit()

    updated = await usage_repo.update(created.id, language="en")
    assert updated.language == "en"
    await async_session.commit()

    updated_again = await usage_repo.update(created.id, transcription_length=77)
    assert updated_again.language == "en"
    assert updated_again.transcription_length == 77
    await async_session.commit()


@pytest.mark.asyncio
async def test_get_period_stats_sorts_languages_by_count(async_session):
    """Языки сортируются по убыванию количества."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    user = await user_repo.create(telegram_id=111111006)
    await async_session.commit()

    records = [
        Usage(
            user_id=user.id,
            voice_file_id=f"rec_{language}",
            voice_duration_seconds=10,
            transcription_length=10,
            language=language,
            created_at=datetime.now(timezone.utc),
        )
        for language in ["en", "ru", "ru", "kk", "ru"]
    ]
    async_session.add_all(records)
    await async_session.commit()

    stats = await usage_repo.get_period_stats(
        user.id, datetime.now(timezone.utc) - timedelta(days=30)
    )

    assert stats.total_count == 5
    assert stats.languages == [("ru", 3), ("en", 1), ("kk", 1)]
