"""Shared async Redis clients with the §15.3 timeouts (connect 1 s, socket 1 s, retry once).

One client per event loop: an asyncio connection belongs to the loop that opened
it. Production workers run a single loop, so this is one client per process;
tests that run several apps side by side get one per loop.
"""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import get_settings

SOCKET_TIMEOUT_SECONDS = 1.0
_clients: dict[int, Redis] = {}


def _loop_key() -> int:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0


def get_redis() -> Redis:
    """The Redis client for the current event loop."""
    key = _loop_key()
    client = _clients.get(key)
    if client is None:
        client = Redis.from_url(
            get_settings().REDIS_URL,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            retry=Retry(NoBackoff(), retries=1),
            decode_responses=False,
        )
        _clients[key] = client
    return client


def forget_clients() -> None:
    """Drop all cached clients without closing them (tests, after loops ended)."""
    _clients.clear()


async def close_redis() -> None:
    """Close this loop's client (app shutdown)."""
    client = _clients.pop(_loop_key(), None)
    if client is not None:
        await client.aclose()
