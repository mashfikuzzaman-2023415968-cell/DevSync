"""Shared async Redis client with the §15.3 timeouts (connect 1 s, socket 1 s, retry once)."""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import get_settings

SOCKET_TIMEOUT_SECONDS = 1.0


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    """Process-wide async Redis client."""
    return Redis.from_url(
        get_settings().REDIS_URL,
        socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        retry=Retry(NoBackoff(), retries=1),
        decode_responses=False,
    )
