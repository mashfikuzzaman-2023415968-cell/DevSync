"""Read-through cache in Redis (spec §15.1; D151).

- Cache-aside: `cached()` returns the stored JSON text or loads, stores and returns it.
- Versioned keys: every key embeds its scope's generation (`cache:gen:{scope}`); invalidating a
  scope bumps the generation, so stale entries are never read again and simply expire. Callers
  invalidate *after* their transaction commits.
- Single flight: one caller loads a missing entry while the others wait briefly for it (a short
  Redis lock), so a burst of requests doesn't stampede the database.
- The cache is an optimisation, never a gate: if Redis is down the loader runs directly.
- What goes in a key decides who shares it: the dashboard puts the response *shape* (client,
  member) in its key, so one role's data is never served to another.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger

log = get_logger(__name__)
LOCK_MS = 5000
WAIT_SECONDS = 2.0
POLL_SECONDS = 0.05


def _gen_key(scope: str) -> str:
    return f"cache:gen:{scope}"


async def _generation(redis: Redis, scope: str) -> str:
    raw = await redis.get(_gen_key(scope))
    if raw is None:
        return "0"
    return raw.decode() if isinstance(raw, bytes) else str(raw)


def _text(raw: object) -> str:
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def cached(
    redis: Redis,
    *,
    name: str,
    scope: str,
    parts: tuple[str, ...],
    ttl_seconds: int,
    loader: Callable[[], Awaitable[str]],
) -> str:
    """The cached JSON text for (name, scope, parts), loading it on a miss."""
    try:
        gen = await _generation(redis, scope)
        key = f"cache:v1:{name}:{scope}:{gen}:{':'.join(parts)}"
        hit = await redis.get(key)
        if hit is not None:
            return _text(hit)
        if not await redis.set(f"{key}:lock", "1", nx=True, px=LOCK_MS):
            waited = 0.0
            while waited < WAIT_SECONDS:  # someone else is loading it: wait for their result
                await asyncio.sleep(POLL_SECONDS)
                waited += POLL_SECONDS
                hit = await redis.get(key)
                if hit is not None:
                    return _text(hit)
        value = await loader()
        await redis.set(key, value, ex=ttl_seconds)
        await redis.delete(f"{key}:lock")
        return value
    except RedisError as exc:
        log.warning("cache_unavailable", name=name, error=type(exc).__name__)
        return await loader()


async def invalidate(redis: Redis, scope: str) -> None:
    """Make every cached entry of `scope` stale (call after the change has committed)."""
    try:
        await redis.incr(_gen_key(scope))
    except RedisError as exc:  # the entries expire on their own (short TTLs)
        log.warning("cache_invalidate_failed", scope=scope, error=type(exc).__name__)
