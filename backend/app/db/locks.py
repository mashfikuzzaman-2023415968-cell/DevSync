"""Transaction-scoped advisory locks keyed by an entity id.

Used where a check and a write must not interleave across requests or job runs (count-then-insert
caps such as 30 open bids per developer, and the notice jobs). The lock ends with the transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def lock_key(entity_id: uuid.UUID) -> int:
    """A signed 64-bit key from the id (a collision only makes two callers wait for each other)."""
    return int.from_bytes(entity_id.bytes[:8], "big", signed=True)


async def advisory_xact_lock(db: AsyncSession, entity_id: uuid.UUID) -> None:
    """Wait for, then hold until commit/rollback, the lock for `entity_id`."""
    await db.execute(select(func.pg_advisory_xact_lock(lock_key(entity_id))))
