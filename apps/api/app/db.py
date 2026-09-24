from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _behind_pgbouncer(url: str) -> bool:
    """Transaction-mode poolers (Neon "-pooler" hosts, Supabase on 6543) break asyncpg's
    statement cache unless prepared statements get unique names."""
    parsed = make_url(url)
    return "pooler" in (parsed.host or "") or parsed.port == 6543


def engine_options(url: str, *, serverless: bool, pool_size: int) -> dict[str, Any]:
    options: dict[str, Any] = {"pool_pre_ping": True}
    if serverless:
        # Function instances are many and may sit frozen between requests: keep few
        # connections, recycle them early and verify each one before use.
        options.update(pool_size=2, max_overflow=8, pool_recycle=240)
    else:
        options.update(pool_size=pool_size, max_overflow=pool_size)
    if _behind_pgbouncer(url):
        options["connect_args"] = {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__lt_{uuid.uuid4().hex}__",
        }
    return options


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            **engine_options(
                settings.database_url,
                serverless=settings.serverless,
                pool_size=settings.database_pool_size,
            ),
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    return _sessionmaker


def set_engine(engine: AsyncEngine) -> None:
    """Override the engine (used by tests)."""
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session for background work: commits on success, rolls back on error."""
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
