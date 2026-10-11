"""Database connection management and async engine lifecycle for PostgreSQL."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.config import get_settings
from app.infrastructure.persistence.postgres.models import Base

logger = logging.getLogger("ledger_core.database")


def create_async_db_engine(
    database_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
) -> AsyncEngine:
    """Creates a high-performance SQLAlchemy AsyncEngine backed by asyncpg."""
    settings = get_settings()
    url = database_url or settings.database_url
    p_size = pool_size if pool_size is not None else settings.db_pool_size
    m_overflow = max_overflow if max_overflow is not None else settings.db_max_overflow
    p_timeout = pool_timeout if pool_timeout is not None else settings.db_pool_timeout

    engine = create_async_engine(
        url,
        echo=False,
        future=True,
        pool_size=p_size,
        max_overflow=m_overflow,
        pool_timeout=p_timeout,
        pool_pre_ping=True,
    )
    return engine


def get_async_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Builds an async session maker bound to the given engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def init_db(engine: AsyncEngine) -> None:
    """Initializes schema and tables in the PostgreSQL database."""
    logger.info("Initializing relational database schema for LedgerCore...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Relational database schema successfully initialized.")


async def drop_db(engine: AsyncEngine) -> None:
    """Drops all tables for testing isolation and migrations."""
    logger.warning("Dropping all relational database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("Relational database tables dropped.")


async def check_db_health(engine: AsyncEngine) -> bool:
    """Pings the PostgreSQL database to verify connectivity."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as err:
        logger.error("PostgreSQL database health check failed: %s", err)
        return False


@asynccontextmanager
async def get_session_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager yielding an AsyncSession with auto-rollback on failure."""
    session = session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
