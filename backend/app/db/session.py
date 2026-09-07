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
engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG and settings.ENVIRONMENT == "development",
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
)

# Async Session Factory
async_session_factory = async_sessionmaker(
    bind=engine,
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
