"""Async engine and per-request session dependency (spec §5.2, §15.3).

The app connects as `devsync_app` (DML only); jobs use `devsync_worker` with a
longer statement timeout. Every connection sets `statement_timeout`,
`lock_timeout` and `idle_in_transaction_session_timeout` so a slow query can
never hold resources indefinitely.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Environment, get_settings
from app.db.context import CONTEXT_KEY, DbContext, RlsSession

LOCK_TIMEOUT_MS = 3000
IDLE_IN_TX_TIMEOUT_MS = 10000


def make_engine(
    url: str, statement_timeout_ms: int, pool_size: int, max_overflow: int
) -> AsyncEngine:
    """Create an asyncpg engine whose connections carry the §15.3 server-side timeouts.

    In the test environment connections are not pooled: tests run many short-lived
    event loops, and an asyncpg connection cannot move between loops.
    """
    pooling: dict[str, Any] = (
        {"poolclass": NullPool}
        if get_settings().DEVSYNC_ENV is Environment.TEST
        else {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_pre_ping": True,
            "pool_timeout": 3,
        }
    )
    return create_async_engine(
        url,
        **pooling,
        connect_args={
            "timeout": 3,
            "command_timeout": max(1, statement_timeout_ms // 1000 + 1),
            "server_settings": {
                "statement_timeout": str(statement_timeout_ms),
                "lock_timeout": str(LOCK_TIMEOUT_MS),
                "idle_in_transaction_session_timeout": str(IDLE_IN_TX_TIMEOUT_MS),
                "application_name": "devsync",
            },
        },
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Engine for web requests (`devsync_app`)."""
    s = get_settings()
    return make_engine(s.DATABASE_URL, s.DB_STATEMENT_TIMEOUT_MS, s.DB_POOL_SIZE, s.DB_MAX_OVERFLOW)


@lru_cache(maxsize=1)
def get_job_engine() -> AsyncEngine:
    """Engine for background jobs (`devsync_worker`, 30 s statement timeout)."""
    s = get_settings()
    url = s.WORKER_DATABASE_URL or s.DATABASE_URL
    return make_engine(url, s.DB_JOB_STATEMENT_TIMEOUT_MS, 5, 2)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the web engine; sessions apply the RLS context per transaction."""
    return async_sessionmaker(get_engine(), expire_on_commit=False, sync_session_class=RlsSession)


@lru_cache(maxsize=1)
def get_job_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Session factory for background jobs (`devsync_worker`)."""
    return async_sessionmaker(
        get_job_engine(), expire_on_commit=False, sync_session_class=RlsSession
    )


@asynccontextmanager
async def open_session(ctx: DbContext, *, job: bool = False) -> AsyncIterator[AsyncSession]:
    """A session acting for `ctx`; rolled back unless the caller committed."""
    maker = get_job_sessionmaker() if job else get_sessionmaker()
    async with maker() as session:
        session.info[CONTEXT_KEY] = ctx
        try:
            yield session
        finally:
            await session.rollback()


async def dispose_engines() -> None:
    """Close pooled connections (app shutdown) and forget cached engines."""
    for factory in (get_engine, get_job_engine):
        if factory.cache_info().currsize:
            await factory().dispose()
        factory.cache_clear()
    get_sessionmaker.cache_clear()
    get_job_sessionmaker.cache_clear()
