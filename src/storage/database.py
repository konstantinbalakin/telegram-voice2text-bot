"""
Database connection and session management
"""

from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
)

from src.config import settings
from src.storage.models import Base


# Global engine instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,  # Set to True for SQL query logging
            future=True,
            pool_pre_ping=True,  # Verify connections before using
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Usage:
        async with get_session() as session:
            result = await session.execute(query)
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database - create all tables."""
    # Ensure database directory exists
    from pathlib import Path
    import re

    # Extract path from database URL
    # Examples: sqlite+aiosqlite:////app/data/bot.db or sqlite+aiosqlite:///./data/bot.db
    db_url = settings.database_url
    match = re.search(r'sqlite\+aiosqlite:///(.*)', db_url)
    if match:
        db_path = match.group(1).lstrip('/')  # Remove leading / for absolute paths
        db_file = Path(db_path) if db_path.startswith('/') else Path(db_path).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
