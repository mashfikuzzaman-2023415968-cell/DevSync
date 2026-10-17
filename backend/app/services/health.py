"""Dependency probes for the readiness endpoint.

Each probe has a short timeout and never raises: a failure is reported as
"unavailable" so readiness fails closed without leaking error details.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from sqlalchemy import literal, select

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.session import get_engine

log = get_logger(__name__)

Status = Literal["ok", "unavailable"]
PROBE_TIMEOUT_SECONDS = 2.0
QUEUE_KEY_PREFIX = "rq:queues"


async def _probe_database() -> Status:
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            async with get_engine().connect() as conn:
                await conn.execute(select(literal(1)))
    except Exception as exc:  # any failure means "not ready"
        log.warning("readiness_probe_failed", dependency="database", error=type(exc).__name__)
        return "unavailable"
    return "ok"


async def _probe_redis() -> Status:
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            await get_redis().ping()
    except Exception as exc:
        log.warning("readiness_probe_failed", dependency="redis", error=type(exc).__name__)
        return "unavailable"
    return "ok"


async def _probe_queue() -> Status:
    """The RQ queues live in Redis; the queue is usable when Redis accepts reads of its keys."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            await get_redis().exists(QUEUE_KEY_PREFIX)
    except Exception as exc:
        log.warning("readiness_probe_failed", dependency="queue", error=type(exc).__name__)
        return "unavailable"
    return "ok"


async def check_dependencies() -> dict[str, Status]:
    """Run all probes concurrently."""
    db, redis, queue = await asyncio.gather(_probe_database(), _probe_redis(), _probe_queue())
    return {"database": db, "redis": redis, "queue": queue}
