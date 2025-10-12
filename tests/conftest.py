"""
Pytest configuration and fixtures
"""
import pytest
import asyncio
from typing import Generator


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


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
