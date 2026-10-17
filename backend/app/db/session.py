"""Async engine and per-request session dependency (spec §5.2, §15.3).

The app connects as `devsync_app` (DML only); jobs use `devsync_worker` with a
longer statement timeout. Every connection sets `statement_timeout`,
`lock_timeout` and `idle_in_transaction_session_timeout` so a slow query can
never hold resources indefinitely.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

LOCK_TIMEOUT_MS = 3000
IDLE_IN_TX_TIMEOUT_MS = 10000


def make_engine(
    url: str, statement_timeout_ms: int, pool_size: int, max_overflow: int
) -> AsyncEngine:
    """Create an asyncpg engine whose connections carry the §15.3 server-side timeouts."""
    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_timeout=3,
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
    """Session factory bound to the web engine."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, rolled back if not committed."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        finally:
            await session.rollback()
