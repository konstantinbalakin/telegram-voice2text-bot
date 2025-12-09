"""Database retry utilities for handling transient errors."""

import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Any

from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def db_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.1,
    backoff_factor: float = 2.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator for database operations that may encounter transient errors.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 0.1)
        backoff_factor: Multiplier for delay between retries (default: 2.0)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except OperationalError as e:
                    last_exception = e
                    # Only retry on "database is locked" errors
                    if "database is locked" in str(e):
                        if attempt < max_attempts - 1:
                            logger.warning(
                                f"Database locked, retrying in {delay:.2f}s "
                                f"(attempt {attempt + 1}/{max_attempts})"
                            )
                            await asyncio.sleep(delay)
                            delay *= backoff_factor
                            continue
                    # For other errors, raise immediately
                    raise

            # All attempts failed
            logger.error(
                f"Database operation failed after {max_attempts} attempts: {last_exception}"
            )
            raise last_exception  # type: ignore

        return wrapper  # type: ignore

    return decorator
