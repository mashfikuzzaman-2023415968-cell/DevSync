"""RQ queue names and a synchronous Redis connection for enqueueing (spec §15.2).

Priorities: `high` (formation, auth emails), `default`, `low` (sync, analytics).
"""

from __future__ import annotations

from functools import lru_cache

from redis import Redis
from rq import Queue

from app.core.config import get_settings

QUEUE_NAMES: tuple[str, ...] = ("high", "default", "low")
MAX_JOBS_PER_WORKER = 500  # restart workers after 500 jobs (memory hygiene, §11)


@lru_cache(maxsize=1)
def get_sync_redis() -> Redis:
    """Synchronous Redis client for RQ (RQ does not use asyncio)."""
    return Redis.from_url(get_settings().REDIS_URL, socket_connect_timeout=1, socket_timeout=5)


def get_queue(name: str = "default") -> Queue:
    """Return one of the named queues; unknown names are rejected."""
    if name not in QUEUE_NAMES:
        raise ValueError(f"Unknown queue: {name}")
    return Queue(name, connection=get_sync_redis())
