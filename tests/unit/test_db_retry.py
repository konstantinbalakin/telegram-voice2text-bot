"""Tests for src/utils/db_retry.py — retry decorator for transient DB errors."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from src.utils.db_retry import db_retry


def _make_locked_error(msg: str = "database is locked") -> OperationalError:
    """Create an OperationalError with the given message."""
    return OperationalError("statement", {}, Exception(msg))


class TestDbRetrySuccess:
    """Decorator does not interfere with successful calls."""

    async def test_returns_result(self):
        @db_retry(max_attempts=3)
        async def ok():
            return "result"

        assert await ok() == "result"

    async def test_called_once_on_success(self):
        call_count = 0

        @db_retry(max_attempts=3)
        async def ok():
            nonlocal call_count
            call_count += 1
            return 42

        await ok()
        assert call_count == 1

    async def test_preserves_args(self):
        @db_retry(max_attempts=3)
        async def add(a, b):
            return a + b

        assert await add(2, 3) == 5

    async def test_preserves_kwargs(self):
        @db_retry(max_attempts=3)
        async def greet(name="world"):
            return f"hello {name}"

        assert await greet(name="test") == "hello test"


class TestDbRetryOnDatabaseLocked:
    """Retries on 'database is locked' OperationalError."""

    async def test_retries_and_succeeds(self):
        call_count = 0

        @db_retry(max_attempts=3)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _make_locked_error()
            return "success"

        with patch("src.utils.db_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await flaky()

        assert result == "success"
        assert call_count == 3

    async def test_max_attempts_exceeded_raises(self):
        @db_retry(max_attempts=3)
        async def always_fail():
            raise _make_locked_error()

        with patch("src.utils.db_retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OperationalError):
                await always_fail()

    async def test_call_count_matches_max_attempts(self):
        call_count = 0

        @db_retry(max_attempts=4)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise _make_locked_error()

        with patch("src.utils.db_retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OperationalError):
                await always_fail()
        assert call_count == 4

    async def test_succeeds_on_last_attempt(self):
        call_count = 0

        @db_retry(max_attempts=3)
        async def last_chance():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _make_locked_error()
            return "ok"

        with patch("src.utils.db_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await last_chance()

        assert result == "ok"
        assert call_count == 3


class TestDbRetryNonRetriableErrors:
    """Errors that should NOT trigger retries."""

    async def test_non_locked_operational_error_not_retried(self):
        call_count = 0

        @db_retry(max_attempts=3)
        async def other_db_error():
            nonlocal call_count
            call_count += 1
            raise _make_locked_error("connection refused")

        with pytest.raises(OperationalError):
            await other_db_error()
        assert call_count == 1

    async def test_value_error_not_retried(self):
        call_count = 0

        @db_retry(max_attempts=3)
        async def bad():
            nonlocal call_count
            call_count += 1
            raise ValueError("something else")

        with pytest.raises(ValueError):
            await bad()
        assert call_count == 1

    async def test_runtime_error_not_retried(self):
        call_count = 0

        @db_retry(max_attempts=3)
        async def bad():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await bad()
        assert call_count == 1

    async def test_type_error_not_retried(self):
        call_count = 0

        @db_retry(max_attempts=3)
        async def bad():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            await bad()
        assert call_count == 1


class TestDbRetryBackoff:
    """Exponential backoff between retries."""

    async def test_backoff_delays(self):
        sleep_times: list[float] = []

        @db_retry(max_attempts=4, initial_delay=0.1, backoff_factor=2.0)
        async def always_fail():
            raise _make_locked_error()

        async def mock_sleep(delay: float) -> None:
            sleep_times.append(delay)

        with patch("src.utils.db_retry.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(OperationalError):
                await always_fail()

        # 4 attempts -> 3 sleeps: 0.1, 0.2, 0.4
        assert len(sleep_times) == 3
        assert sleep_times[0] == pytest.approx(0.1)
        assert sleep_times[1] == pytest.approx(0.2)
        assert sleep_times[2] == pytest.approx(0.4)

    async def test_custom_initial_delay(self):
        sleep_times: list[float] = []

        @db_retry(max_attempts=2, initial_delay=0.5, backoff_factor=1.0)
        async def always_fail():
            raise _make_locked_error()

        async def mock_sleep(delay: float) -> None:
            sleep_times.append(delay)

        with patch("src.utils.db_retry.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(OperationalError):
                await always_fail()

        assert len(sleep_times) == 1
        assert sleep_times[0] == pytest.approx(0.5)

    async def test_custom_backoff_factor(self):
        sleep_times: list[float] = []

        @db_retry(max_attempts=4, initial_delay=1.0, backoff_factor=3.0)
        async def always_fail():
            raise _make_locked_error()

        async def mock_sleep(delay: float) -> None:
            sleep_times.append(delay)

        with patch("src.utils.db_retry.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(OperationalError):
                await always_fail()

        assert sleep_times == [pytest.approx(1.0), pytest.approx(3.0), pytest.approx(9.0)]

    async def test_no_sleep_on_success(self):
        sleep_called = False

        @db_retry(max_attempts=3)
        async def ok():
            return "ok"

        async def mock_sleep(delay: float) -> None:
            nonlocal sleep_called
            sleep_called = True

        with patch("src.utils.db_retry.asyncio.sleep", side_effect=mock_sleep):
            await ok()

        assert not sleep_called


class TestDbRetryCustomMaxAttempts:
    """max_attempts parameter is respected."""

    async def test_max_attempts_1(self):
        call_count = 0

        @db_retry(max_attempts=1)
        async def fail():
            nonlocal call_count
            call_count += 1
            raise _make_locked_error()

        with patch("src.utils.db_retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OperationalError):
                await fail()
        assert call_count == 1

    async def test_max_attempts_5(self):
        call_count = 0

        @db_retry(max_attempts=5)
        async def fail():
            nonlocal call_count
            call_count += 1
            raise _make_locked_error()

        with patch("src.utils.db_retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OperationalError):
                await fail()
        assert call_count == 5


class TestDbRetryDefaults:
    """Default parameter values."""

    async def test_default_max_attempts_is_3(self):
        call_count = 0

        @db_retry()
        async def fail():
            nonlocal call_count
            call_count += 1
            raise _make_locked_error()

        with patch("src.utils.db_retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OperationalError):
                await fail()
        assert call_count == 3

    async def test_default_initial_delay(self):
        sleep_times: list[float] = []

        @db_retry()
        async def fail():
            raise _make_locked_error()

        async def mock_sleep(delay: float) -> None:
            sleep_times.append(delay)

        with patch("src.utils.db_retry.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(OperationalError):
                await fail()

        # default: initial_delay=0.1, backoff_factor=2.0, max_attempts=3
        # sleeps: 0.1, 0.2
        assert sleep_times[0] == pytest.approx(0.1)
        assert sleep_times[1] == pytest.approx(0.2)
