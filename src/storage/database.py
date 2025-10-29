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
    """
    Initialize database - verify migration status.

    This function checks that database schema is up-to-date with migrations.
    It does NOT create tables directly (use alembic for that).
    """
    import logging
    from pathlib import Path

    logger = logging.getLogger(__name__)

    # Ensure database directory exists
    import re

    # Extract path from database URL
    # Examples: sqlite+aiosqlite:////app/data/bot.db or
    # sqlite+aiosqlite:///./data/bot.db
    db_url = settings.database_url
    match = re.search(r"sqlite\+aiosqlite:///(.*)", db_url)
    if match:
        db_path = match.group(1).lstrip("/")  # Remove leading / for absolute paths
        if db_path.startswith("/"):
            db_file = Path(db_path)
        else:
            db_file = Path(db_path).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)

    # Check database migration status
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine

        # Get alembic config
        project_root = Path(__file__).parent.parent.parent
        alembic_ini = project_root / "alembic.ini"

        if not alembic_ini.exists():
            logger.warning(
                f"⚠️  Alembic config not found at {alembic_ini}. "
                "Cannot verify migration status."
            )
            return

        config = Config(str(alembic_ini))
        script = ScriptDirectory.from_config(config)
        head_revision = script.get_current_head()

        # Get current database revision (using sync engine for alembic)
        db_url_sync = db_url.replace("+aiosqlite", "")
        engine = create_engine(db_url_sync)

        try:
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                current_revision = context.get_current_revision()
        finally:
            engine.dispose()

        # Log migration status
        if current_revision is None:
            logger.error(
                "❌ Database not initialized! No migration applied.\n"
                "   Run: alembic upgrade head"
            )
            raise RuntimeError(
                "Database not initialized. Run 'alembic upgrade head' first."
            )
        elif current_revision != head_revision:
            logger.error(
                f"❌ Database schema is out of date!\n"
                f"   Current: {current_revision}\n"
                f"   HEAD:    {head_revision}\n"
                f"   Run: alembic upgrade head"
            )
            raise RuntimeError(
                f"Database schema mismatch. Current: {current_revision}, "
                f"HEAD: {head_revision}. Run 'alembic upgrade head'."
            )
        else:
            logger.info(f"✅ Database schema is up to date (revision: {current_revision})")

    except Exception as e:
        logger.error(f"Failed to verify database migration status: {e}")
        raise


async def close_db() -> None:
    """Close database connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
