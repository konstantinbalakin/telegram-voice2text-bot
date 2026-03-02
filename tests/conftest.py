"""
Pytest configuration and fixtures
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.services.billing_service import BillingService
from src.storage.models import Base
from src.transcription.audio_handler import AudioHandler


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


@pytest.fixture
def audio_handler(tmp_path):
    """Create AudioHandler instance with temp directory."""
    return AudioHandler(temp_dir=tmp_path)


def make_billing_service(
    billing_enabled: bool = True,
    warning_threshold: float = 0.8,
) -> tuple[BillingService, dict[str, AsyncMock]]:
    """Create BillingService with mocked repositories.

    Shared helper used across billing test modules.
    Returns (service, mocks_dict) where mocks_dict keys are:
    condition_repo, subscription_repo, balance_repo, daily_usage_repo, deduction_log_repo.
    """
    mocks = {
        "condition_repo": AsyncMock(),
        "subscription_repo": AsyncMock(),
        "balance_repo": AsyncMock(),
        "daily_usage_repo": AsyncMock(),
        "deduction_log_repo": AsyncMock(),
    }

    service = BillingService(
        condition_repo=mocks["condition_repo"],
        subscription_repo=mocks["subscription_repo"],
        balance_repo=mocks["balance_repo"],
        daily_usage_repo=mocks["daily_usage_repo"],
        deduction_log_repo=mocks["deduction_log_repo"],
        billing_enabled=billing_enabled,
        warning_threshold=warning_threshold,
    )

    return service, mocks
