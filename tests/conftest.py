"""
Pytest configuration and fixtures
"""

import pytest
import pytest_asyncio
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.storage.models import Base


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for the test session."""
    return asyncio.get_event_loop_policy()


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    from src.config import Settings

    return Settings(
        telegram_bot_token="test_token",
        bot_mode="polling",
        whisper_model_size="tiny",
        database_url="sqlite+aiosqlite:///:memory:",
        max_queue_size=10,
        max_concurrent_workers=2,
    )


@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite async engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """Create an async session for testing."""
    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()
