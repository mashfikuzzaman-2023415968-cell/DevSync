"""The audit log's hash chain stays one unbroken line under concurrent writers (spec §7.1, D12;
fixed in migration 0013, DECISIONS D103).

Before 0013 a row was numbered (`seq`) when its INSERT started but chained only after it took
the chain lock, so concurrent writers could chain out of numbering order and fork the chain;
`audit_verify_chain()` then reported tampering that never happened (found by the Phase 6 gate).
The race needs a writer to be descheduled between drawing its number and asking for the lock,
which happened under heavy load but can't be timed in a test. So the first test checks the
mechanism deterministically: while another connection holds the chain lock, a waiting insert
must not have drawn its number yet. The second is a stress check of the chain invariant.
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from app.core.audit import write_audit
from app.db.context import DbContext
from app.db.session import open_session
from tests.helpers import stack_available

pytestmark = pytest.mark.integration

WRITERS = 30


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available() or not os.environ.get("MIGRATION_DATABASE_URL"):
        pytest.skip("needs the test compose stack")


def _migrator() -> Any:
    # The audit log is readable only by admins and the migrator (RLS); read it as the migrator.
    return create_engine(os.environ["MIGRATION_DATABASE_URL"])


def _last_seq() -> int:
    engine = _migrator()
    try:
        with engine.connect() as c:
            return int(c.execute(text("SELECT coalesce(max(seq), 0) FROM audit_log")).scalar_one())
    finally:
        engine.dispose()


async def _writer(i: int, rnd: random.Random) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await write_audit(db, action="test.chain", entity_type="test", entity_id=str(i),
                          actor_role="SYSTEM")  # fmt: skip
        # Hold the chain lock a moment so the other writers queue with their numbers drawn.
        await asyncio.sleep(rnd.uniform(0, 0.02))
        await db.commit()


def _chain_breaks(after_seq: int) -> list[str]:
    """Every row after `after_seq`, in seq order, must link to the row before it."""
    engine = _migrator()
    try:
        with engine.connect() as c:
            prev = c.execute(
                text("SELECT hash FROM audit_log WHERE seq <= :s ORDER BY seq DESC LIMIT 1"),
                {"s": after_seq},
            ).scalar()
            rows = c.execute(
                text(
                    "SELECT seq, prev_hash, hash, audit_row_hash(prev_hash, a) AS recomputed "
                    "FROM audit_log a WHERE seq > :s ORDER BY seq"
                ),
                {"s": after_seq},
            ).all()
    finally:
        engine.dispose()
    breaks = []
    for row in rows:
        if row.prev_hash != prev:
            breaks.append(f"seq {row.seq} does not link to the row before it")
        if row.hash != row.recomputed:
            breaks.append(f"seq {row.seq} hash does not match its content")
        prev = row.hash
    return breaks


CHAIN_LOCK = "SELECT pg_advisory_xact_lock(hashtext('devsync.audit_log.chain'))"
NEXTVAL = "SELECT nextval(pg_get_serial_sequence('public.audit_log', 'seq'))"


async def test_a_row_is_numbered_only_after_it_holds_the_chain_lock() -> None:
    """Hold the chain lock elsewhere, start an insert (it waits), then draw a number directly.
    The waiting row must end up *after* that number: it was numbered under the lock. Before
    migration 0013 it was numbered on arrival, so it ended up before it (D103)."""
    engine = _migrator()
    try:
        holder = engine.connect()
        holder.begin()
        holder.execute(text(CHAIN_LOCK))
        entity = f"lock-order-{random.Random().getrandbits(32)}"
        waiting = asyncio.create_task(_writer_with_entity(entity))
        await asyncio.sleep(0.5)  # the insert is now queued on the lock
        assert not waiting.done()
        with engine.connect() as other:
            drawn = int(other.execute(text(NEXTVAL)).scalar_one())
            other.commit()
        holder.commit()  # release the lock
        holder.close()
        await asyncio.wait_for(waiting, timeout=10)
        with engine.connect() as c:
            seq = int(
                c.execute(
                    text("SELECT seq FROM audit_log WHERE entity_id = :e"), {"e": entity}
                ).scalar_one()
            )
    finally:
        engine.dispose()
    assert seq > drawn


async def _writer_with_entity(entity: str) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await write_audit(db, action="test.chain", entity_type="test", entity_id=entity,
                          actor_role="SYSTEM")  # fmt: skip
        await db.commit()


async def test_concurrent_writers_keep_one_unbroken_chain() -> None:
    start = _last_seq()
    rnd = random.Random(7)  # timing jitter for a test, not security
    await asyncio.gather(*(_writer(i, rnd) for i in range(WRITERS)))
    assert _last_seq() > start
    assert _chain_breaks(start) == []
