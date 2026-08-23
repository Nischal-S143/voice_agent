from __future__ import annotations

from uuid import uuid4

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


def _pooler_safe_url(asyncpg_url: str) -> str:
    """Disable SQLAlchemy's own prepared-statement cache via the URL.

    The asyncpg dialect only reads ``prepared_statement_cache_size`` as a
    query parameter, not as a create_engine() keyword.
    """
    if "prepared_statement_cache_size=" in asyncpg_url:
        return asyncpg_url
    separator = "&" if "?" in asyncpg_url else "?"
    return f"{asyncpg_url}{separator}prepared_statement_cache_size=0"


def create_engine_and_session_factory(settings: Settings) -> DatabaseResources:
    """Create database resources only when a database URL has been configured."""
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        return None, None

    engine = create_async_engine(
        _pooler_safe_url(_asyncpg_url(database_url)),
        pool_pre_ping=True,
        connect_args={
            # Supabase's transaction-mode pooler hands out a different backend
            # per transaction, so a cached prepared statement is not there next
            # time and asyncpg raises DuplicatePreparedStatementError. Disable
            # asyncpg's cache and give every statement a unique name.
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)
