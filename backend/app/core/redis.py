"""Shared async Redis clients with the §15.3 timeouts (connect 1 s, socket 1 s, retry once).

One client per event loop: an asyncio connection belongs to the loop that opened
it. Production web workers run a single loop, so this is one client per process;
background jobs start a fresh loop per run (`asyncio.run`) and tests start many.

The cache is keyed by the loop object itself, held weakly, so a client lives exactly as long
as its loop. Keying by `id(loop)` (as before) handed a new loop the client of a dead one
whenever Python reused the id — in practice almost always — and that client's connections
belong to a loop that no longer runs: a request could spin there indefinitely.
"""

from __future__ import annotations

import asyncio
import weakref

from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.maint_notifications import MaintNotificationsConfig
from redis.retry import Retry

from app.core.config import get_settings

SOCKET_TIMEOUT_SECONDS = 1.0
_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Redis] = weakref.WeakKeyDictionary()
_loopless: Redis | None = None  # built outside any running loop (start-up code)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _new_client() -> Redis:
    return Redis.from_url(
        get_settings().REDIS_URL,
        socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        retry=Retry(NoBackoff(), retries=1),
        decode_responses=False,
        # redis-py 8 asks every new connection to turn on "maintenance notifications" (a Redis
        # Enterprise/Cloud failover feature). Our Redis 7 refuses it, so each connection paid a
        # failed round trip and a warning; the handshake is also where a stale loop hung.
        maint_notifications_config=MaintNotificationsConfig(enabled=False),
    )


def get_redis() -> Redis:
    """The Redis client for the current event loop."""
    global _loopless  # noqa: PLW0603  (one client for code that runs before any loop)
    loop = _running_loop()
    if loop is None:
        if _loopless is None:
            _loopless = _new_client()
        return _loopless
    client = _clients.get(loop)
    if client is None:
        client = _new_client()
        _clients[loop] = client
    return client


def forget_clients() -> None:
    """Drop all cached clients without closing them (tests, after loops ended)."""
    global _loopless  # noqa: PLW0603
    _clients.clear()
    _loopless = None


async def close_redis() -> None:
    """Close this loop's client (app shutdown)."""
    loop = _running_loop()
    client = _clients.pop(loop, None) if loop is not None else None
    if client is not None:
        await client.aclose()
