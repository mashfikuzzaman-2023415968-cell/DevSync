"""Transaction-scoped advisory locks (`app/db/locks.py`).

They are what keeps a count-then-insert cap honest — 30 open bids per developer, 20 active
projects per client (D63) — so the property under test is the one those caps rely on: a second
transaction asking for the same key waits until the first commits, and a different key does not
wait at all.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.db.context import DbContext
from app.db.locks import advisory_xact_lock, lock_key
from app.db.session import open_session
from tests.helpers import stack_available

pytestmark = pytest.mark.integration

INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
HOLD_SECONDS = 0.5  # how long the first transaction keeps the lock before committing


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")


# --------------------------------------------------------------------------------- lock_key


def test_lock_key_is_stable_for_one_id() -> None:
    entity = uuid.uuid4()
    assert lock_key(entity) == lock_key(uuid.UUID(str(entity)))


def test_lock_key_fits_a_postgres_bigint() -> None:
    for entity in (uuid.UUID(int=0), uuid.UUID(int=2**128 - 1), *(uuid.uuid4() for _ in range(50))):
        assert INT64_MIN <= lock_key(entity) <= INT64_MAX


def test_lock_key_separates_ids_that_differ_in_the_first_half() -> None:
    # The key is the first 8 bytes; ids differing there must not share a lock.
    a = uuid.UUID("00000000-0000-4000-8000-000000000001")
    b = uuid.UUID("00000001-0000-4000-8000-000000000001")
    assert lock_key(a) != lock_key(b)


# ------------------------------------------------------------------------ advisory_xact_lock


async def _hold_then_commit(entity: uuid.UUID, held: asyncio.Event) -> float:
    """Take the lock, signal, keep it for HOLD_SECONDS, commit; return when the commit began.

    The commit's start is the earliest moment the lock can pass on: Postgres grants a waiter
    the instant the commit lands, which can be before this coroutine resumes to read a clock.
    """
    loop = asyncio.get_running_loop()
    async with open_session(DbContext.system(), job=True) as db:
        await advisory_xact_lock(db, entity)
        held.set()
        await asyncio.sleep(HOLD_SECONDS)
        releasing = loop.time()
        await db.commit()
        return releasing


async def _acquire(entity: uuid.UUID) -> float:
    """Take the lock in a fresh transaction; return when it was granted."""
    loop = asyncio.get_running_loop()
    async with open_session(DbContext.system(), job=True) as db:
        await advisory_xact_lock(db, entity)
        granted = loop.time()
        await db.commit()
        return granted


@pytest.mark.asyncio
async def test_a_second_transaction_waits_for_the_first_to_commit() -> None:
    entity = uuid.uuid4()
    held = asyncio.Event()
    first = asyncio.create_task(_hold_then_commit(entity, held))
    await held.wait()
    granted = await _acquire(entity)
    releasing = await first
    # Granted only once the holder began to commit: the check-then-write window is serialised.
    assert granted >= releasing


@pytest.mark.asyncio
async def test_a_different_key_does_not_wait() -> None:
    held = asyncio.Event()
    first = asyncio.create_task(_hold_then_commit(uuid.uuid4(), held))
    await held.wait()
    loop = asyncio.get_running_loop()
    asked = loop.time()
    granted = await _acquire(uuid.uuid4())
    releasing = await first
    # Another user's lock is independent: granted while the first is still held.
    assert granted < releasing
    assert granted - asked < HOLD_SECONDS


@pytest.mark.asyncio
async def test_the_lock_ends_with_a_rollback_too() -> None:
    entity = uuid.uuid4()
    async with open_session(DbContext.system(), job=True) as db:
        await advisory_xact_lock(db, entity)
        await db.rollback()
    # Transaction-scoped: nothing left behind for the next caller.
    granted = await asyncio.wait_for(_acquire(entity), timeout=HOLD_SECONDS)
    assert granted > 0
