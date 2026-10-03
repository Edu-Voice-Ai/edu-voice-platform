"""
Edu-Voice-Ai — Database Connection Layer & Async Session Management
Provides connection pooling, lifecycle management, and get_db FastAPI dependency.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from app.core.config import settings
from app.core.logging import logger

# Initialize Async Engine with connection pooling
# pool_pre_ping is disabled: asyncpg detects broken connections at the transport layer.
# pool_recycle=1800 recycles idle connections every 30 min to avoid server-side timeouts.
engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG and settings.ENVIRONMENT == "development",
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=False,
    pool_recycle=1800,
)

# Standard Session Factory (read-write endpoints)
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# AUTOCOMMIT engine for read-only endpoints — prevents BEGIN/ROLLBACK roundtrips.
# Each statement runs directly without a transaction wrapper: 1 SQL = 1 WAN RTT.
_engine_autocommit: AsyncEngine = engine.execution_options(isolation_level="AUTOCOMMIT")

# Read-only Session Factory (uses AUTOCOMMIT isolation — no transaction overhead)
_async_session_factory_readonly = async_sessionmaker(
    bind=_engine_autocommit,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async database session per request.
    Automatically commits on success or rolls back on exception.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_readonly() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for read-only database sessions.
    Uses isolation_level=AUTOCOMMIT to eliminate both the implicit BEGIN and
    the ROLLBACK on session close — each query runs in a single WAN roundtrip.
    Use ONLY for pure-SELECT endpoints (e.g. DID resolution) that never write.
    Saves ~290ms per request vs get_db() (Stockholm -> Mumbai cross-region).
    """
    async with _async_session_factory_readonly() as session:
        try:
            yield session
            # No commit — AUTOCOMMIT means each statement auto-completes
        except Exception:
            raise  # No rollback needed — AUTOCOMMIT, nothing to undo
        finally:
            await session.close()


async def check_database_health() -> bool:
    """
    Executes a lightweight query (SELECT 1) to verify database connectivity.
    Returns True if healthy, False otherwise.
    """
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as exc:
        logger.warning(f"Database health check failed: {str(exc)}")
        return False


async def init_db() -> None:
    """Initialize database connection lifecycle."""
    pass


async def close_db() -> None:
    """Dispose of the database engine connection pool upon application shutdown."""
    await engine.dispose()


