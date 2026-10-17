"""Homepage statistics (spec §13.11 #3): aggregate counts only, cached for 5 minutes.

Counting needs every user row, which row-level security hides from web requests, so the
numbers come from the SECURITY DEFINER function `public_stats()` that returns aggregates and
nothing else (migration 0003). The cache fails open: without Redis the numbers are recomputed.
"""

from __future__ import annotations

import json

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import Integer, Select, column, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.schemas.public import PublicStats

log = get_logger(__name__)

CACHE_KEY = "public:stats:v1"
CACHE_SECONDS = 300


async def compute_stats(db: AsyncSession) -> PublicStats:
    query: Select[int] = select(column("developers", Integer)).select_from(func.public_stats())
    developers = int((await db.execute(query)).scalar_one())
    return PublicStats(developers=developers or None)


async def get_public_stats(db: AsyncSession, redis: Redis) -> PublicStats:
    try:
        cached = await redis.get(CACHE_KEY)
    except RedisError as exc:
        log.warning("public_stats_cache_unavailable", error=type(exc).__name__)
        cached = None
    if cached:
        return PublicStats.model_validate(json.loads(cached))
    stats = await compute_stats(db)
    try:
        await redis.set(CACHE_KEY, stats.model_dump_json(), ex=CACHE_SECONDS)
    except RedisError as exc:
        log.warning("public_stats_cache_unavailable", error=type(exc).__name__)
    return stats
