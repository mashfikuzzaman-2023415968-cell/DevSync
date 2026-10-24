"""Scheduled jobs record their runs in the `jobs` table (spec §7.8, §11)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, insert, select, text, update

from app.core.clock import get_clock
from app.db.context import DbContext
from app.db.session import open_session
from app.jobs import email_jobs, profile_jobs
from app.jobs.runs import ABANDONED, RUN_RETENTION, STALE_AFTER, prune_runs, run_recorded
from app.models.foundation import Job, JobStatus
from tests.helpers import stack_available

pytestmark = pytest.mark.jobs


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")


@dataclass(frozen=True)
class Run:
    """A `jobs` row read outside its session (so attributes stay readable)."""

    id: uuid.UUID
    status: JobStatus
    progress: int
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    requested_by: uuid.UUID | None


async def _runs(job_type: str) -> list[Run]:
    async with open_session(DbContext.system(), job=True) as db:
        rows = await db.execute(
            select(
                Job.id,
                Job.status,
                Job.progress,
                Job.started_at,
                Job.finished_at,
                Job.error_code,
                Job.requested_by,
            )
            .where(Job.type == job_type)
            .order_by(Job.created_at, Job.id)
        )
        return [Run(*row) for row in rows.all()]


async def _clear(job_type: str) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(delete(Job).where(Job.type == job_type))
        await db.commit()


async def test_a_successful_run_is_recorded() -> None:
    await _clear("t.ok")
    assert await run_recorded("t.ok", _value) == 42
    (row,) = await _runs("t.ok")
    assert row.status is JobStatus.SUCCEEDED
    assert row.progress == 100
    assert row.started_at is not None
    assert row.finished_at is not None
    assert row.finished_at >= row.started_at
    assert row.error_code is None
    assert row.requested_by is None  # a scheduled job has no requester


async def _value() -> int:
    return 42


async def _boom() -> int:
    raise ZeroDivisionError("secret value 1234 should never be stored")


async def test_a_failed_run_keeps_the_error_class_only() -> None:
    await _clear("t.fail")
    with pytest.raises(ZeroDivisionError):
        await run_recorded("t.fail", _boom)
    (row,) = await _runs("t.fail")
    assert row.status is JobStatus.FAILED
    assert row.error_code == "ZeroDivisionError"
    assert row.progress == 0  # it never finished
    assert row.finished_at is not None


async def test_the_row_exists_while_the_job_runs() -> None:
    await _clear("t.during")
    seen: list[tuple[JobStatus, int]] = []

    async def work() -> None:
        # The RUNNING row was committed before the work started (own transaction, §11).
        seen.extend((r.status, r.progress) for r in await _runs("t.during"))

    await run_recorded("t.during", work)
    assert seen == [(JobStatus.RUNNING, 0)]


async def test_each_run_is_its_own_row() -> None:
    await _clear("t.many")
    for _ in range(3):
        await run_recorded("t.many", _value)
    rows = await _runs("t.many")
    assert len(rows) == 3
    assert {r.status for r in rows} == {JobStatus.SUCCEEDED}


async def test_scheduled_jobs_record_a_run() -> None:
    for job_type, call in (
        ("email.send", email_jobs.email_send),
        ("lifecycle.expire", email_jobs.lifecycle_expire),
        ("uploads.cleanup", profile_jobs.uploads_cleanup),
        ("attempts.expire", profile_jobs.attempts_expire),
    ):
        await _clear(job_type)
        # The RQ entry points are synchronous (they call asyncio.run themselves).
        await asyncio.to_thread(call)
        rows = await _runs(job_type)
        assert [r.status for r in rows] == [JobStatus.SUCCEEDED], job_type
        assert rows[0].finished_at is not None


async def _insert(job_type: str, **values: object) -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        job_id = await db.scalar(insert(Job).values(type=job_type, **values).returning(Job.id))
        await db.commit()
    assert job_id is not None
    return uuid.UUID(str(job_id))


async def _age(job_id: uuid.UUID, created_at: object) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(Job).where(Job.id == job_id).values(created_at=created_at))
        await db.commit()


async def test_prune_closes_abandoned_runs_and_deletes_old_ones() -> None:
    await _clear("t.prune")
    now = get_clock().now()
    stale = await _insert(
        "t.prune", status=JobStatus.RUNNING, started_at=now - STALE_AFTER - timedelta(minutes=1)
    )
    fresh = await _insert("t.prune", status=JobStatus.RUNNING, started_at=now)
    old_done = await _insert("t.prune", status=JobStatus.SUCCEEDED, finished_at=now)
    await _age(old_done, now - RUN_RETENTION - timedelta(days=1))
    recent_done = await _insert("t.prune", status=JobStatus.SUCCEEDED, finished_at=now)

    counts = await prune_runs(now)
    assert counts["jobs_abandoned"] >= 1
    assert counts["jobs_pruned"] >= 1
    by_id = {r.id: r for r in await _runs("t.prune")}
    assert old_done not in by_id  # deleted
    assert by_id[stale].status is JobStatus.FAILED
    assert by_id[stale].error_code == ABANDONED
    assert by_id[fresh].status is JobStatus.RUNNING  # still running, left alone
    assert by_id[recent_done].status is JobStatus.SUCCEEDED


async def test_a_users_own_job_is_never_pruned() -> None:
    await _clear("t.user")
    async with open_session(DbContext.system(), job=True) as db:
        user_id = await db.scalar(text("SELECT id FROM users LIMIT 1"))
    if user_id is None:
        pytest.skip("no user seeded in this database")
    now = get_clock().now()
    mine = await _insert(
        "t.user", status=JobStatus.SUCCEEDED, finished_at=now, requested_by=user_id
    )
    await _age(mine, now - RUN_RETENTION - timedelta(days=30))
    await prune_runs(now)
    assert [r.id for r in await _runs("t.user")] == [mine]
