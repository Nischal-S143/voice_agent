from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

AsyncSessionFactory = async_sessionmaker[AsyncSession]
DatabaseResources = tuple[AsyncEngine | None, AsyncSessionFactory | None]


def _asyncpg_url(database_url: str) -> str:
    """Convert PostgreSQL and Supabase pooler URLs to SQLAlchemy's asyncpg dialect."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+asyncpg://" + database_url.removeprefix("postgres://")
    return database_url


def create_engine_and_session_factory(settings: Settings) -> DatabaseResources:
    """Create database resources only when a database URL has been configured."""
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        return None, None

    engine = create_async_engine(_asyncpg_url(database_url), pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
