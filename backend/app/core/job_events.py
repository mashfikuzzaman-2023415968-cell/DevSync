"""Live progress of a background job, for the SSE stream (spec §10.3, D107).

The worker appends small JSON events to a capped Redis list `job:{id}:events` (at most
`MAX_EVENTS`, expiring `TTL_SECONDS` after the last write); the stream reads it from an index,
so a reconnecting browser resumes with `Last-Event-ID`. Events carry only ids, a phase,
progress, iteration and best fitness — never candidate data, prices or names.

`acquire_stream`/`release_stream` count each user's open streams (`sse.concurrent`, max 3).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis

MAX_EVENTS = 500
TTL_SECONDS = 3600
MAX_STREAMS_PER_USER = 3
STREAM_SLOT_TTL_SECONDS = 31 * 60  # a crashed web worker can't hold a slot past the 30 min cap
TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "INFEASIBLE", "TIMED_OUT"})
ALLOWED_KEYS = frozenset({"type", "status", "progress", "iteration", "best_fitness", "run_id"})


def events_key(job_id: uuid.UUID) -> str:
    return f"job:{job_id}:events"


def _streams_key(user_id: uuid.UUID) -> str:
    return f"sse:concurrent:{user_id}"


async def publish(redis: Redis, job_id: uuid.UUID, event: dict[str, Any]) -> None:
    """Append one event (unknown keys are refused, so nothing sensitive slips in)."""
    unknown = set(event) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"unexpected event keys: {sorted(unknown)}")
    key = events_key(job_id)
    pipe = redis.pipeline(transaction=True)
    pipe.rpush(key, json.dumps(event, separators=(",", ":")))
    pipe.ltrim(key, -MAX_EVENTS, -1)
    pipe.expire(key, TTL_SECONDS)
    await pipe.execute()


async def read_from(redis: Redis, job_id: uuid.UUID, start: int) -> list[dict[str, Any]]:
    """Events from index `start` on (the list is capped, so very old indexes are gone)."""
    raw = await redis.lrange(events_key(job_id), max(start, 0), -1)
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            value = json.loads(item)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


async def acquire_stream(redis: Redis, user_id: uuid.UUID) -> bool:
    """Take one of the user's stream slots; False when all are in use."""
    key = _streams_key(user_id)
    count = int(await redis.incr(key))
    await redis.expire(key, STREAM_SLOT_TTL_SECONDS)
    if count > MAX_STREAMS_PER_USER:
        await redis.decr(key)
        return False
    return True


async def release_stream(redis: Redis, user_id: uuid.UUID) -> None:
    key = _streams_key(user_id)
    if int(await redis.decr(key)) <= 0:
        await redis.delete(key)
