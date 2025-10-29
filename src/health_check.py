#!/usr/bin/env python3
"""
Health check script for Docker container.

Checks:
1. Database connectivity
2. Database schema version (must be at HEAD)

Exit codes:
- 0: Healthy (all checks passed)
- 1: Unhealthy (any check failed)
"""
import asyncio
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def get_alembic_config() -> Config:
    """Get Alembic configuration."""
    # Get project root (parent of src/)
    project_root = Path(__file__).parent.parent
    alembic_ini = project_root / "alembic.ini"

    if not alembic_ini.exists():
        print(f"❌ Alembic config not found: {alembic_ini}", file=sys.stderr)
        sys.exit(1)

    config = Config(str(alembic_ini))
    return config


def get_current_revision(config: Config) -> str | None:
    """
    Get current database revision.

    Returns:
        Current revision hash or None if not initialized
    """
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    # Get database URL from config
    db_url = config.get_main_option("sqlalchemy.url")
    if not db_url:
        print("❌ Database URL not found in alembic config", file=sys.stderr)
        sys.exit(1)

    # Convert async URL to sync for alembic operations
    db_url_sync = db_url.replace("+aiosqlite", "")

    # Create sync engine for migration context
    engine = create_engine(db_url_sync)

    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            return current_rev
    finally:
        engine.dispose()


def get_head_revision(config: Config) -> str:
    """
    Get HEAD revision from migration scripts.

    Returns:
        HEAD revision hash
    """
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()

    if not head:
        print("❌ No HEAD revision found in migration scripts", file=sys.stderr)
        sys.exit(1)

    return head


async def check_database_connectivity() -> bool:
    """
    Check database connectivity.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        # Import settings here to avoid circular imports
        from src.config import settings

        # Create async engine
        engine = create_async_engine(settings.database_url)

        # Try to connect and execute simple query
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()

        await engine.dispose()
        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}", file=sys.stderr)
        return False


def check_migration_status() -> bool:
    """
    Check if database is at HEAD revision.

    Returns:
        True if at HEAD, False otherwise
    """
    try:
        config = get_alembic_config()
        current = get_current_revision(config)
        head = get_head_revision(config)

        if current is None:
            print("❌ Database not initialized (no revision found)", file=sys.stderr)
            return False

        if current != head:
            print(f"❌ Database schema out of date:", file=sys.stderr)
            print(f"   Current: {current}", file=sys.stderr)
            print(f"   HEAD:    {head}", file=sys.stderr)
            print(f"   Run 'alembic upgrade head' to update", file=sys.stderr)
            return False

        print(f"✅ Database schema is up to date (revision: {current})")
        return True

    except Exception as e:
        print(f"❌ Migration status check failed: {e}", file=sys.stderr)
        return False


async def run_health_checks() -> bool:
    """
    Run all health checks.

    Returns:
        True if all checks pass, False otherwise
    """
    all_checks_passed = True

    # Check 1: Database connectivity
    print("Checking database connectivity...")
    if await check_database_connectivity():
        print("✅ Database connection successful")
    else:
        all_checks_passed = False

    # Check 2: Migration status
    print("Checking migration status...")
    if not check_migration_status():
        all_checks_passed = False

    return all_checks_passed


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        all_passed = asyncio.run(run_health_checks())

        if all_passed:
            print("\n✅ All health checks passed")
            return 0
        else:
            print("\n❌ Some health checks failed", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"\n❌ Health check error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
