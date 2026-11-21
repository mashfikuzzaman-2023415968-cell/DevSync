"""`reputation.recalculate_all` (spec §11: 30 min timeout, no retries): it runs through RQ, records
its run, is idempotent, and a failure is recorded with the error's class name only."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.context import DbContext
from app.db.session import open_session
from app.jobs import reputation_jobs
from app.jobs.queues import get_sync_redis
from app.models.foundation import Job, JobStatus
from app.services import reputation_engine
from tests.helpers import stack_available
from tests.integration.test_reputation_engine import _with_history

pytestmark = pytest.mark.jobs


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")


async def _clear() -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(delete(Job).where(Job.type == reputation_jobs.JOB_TYPE))
        await db.commit()


async def _statuses() -> list[tuple[JobStatus, str | None]]:
    async with open_session(DbContext.system(), job=True) as db:
        rows = await db.execute(
            select(Job.status, Job.error_code)
            .where(Job.type == reputation_jobs.JOB_TYPE)
            .order_by(Job.created_at)
        )
        return [(s, e) for s, e in rows.all()]


def test_limits_follow_section_11() -> None:
    assert reputation_jobs.TIMEOUT_SECONDS == 30 * 60
    assert reputation_jobs.RETRIES == 0


def test_runs_through_rq_and_records_the_run() -> None:
    """Synchronous on purpose: RQ's worker installs signal handlers, which needs the main
    thread (the test DB engine doesn't pool, so each asyncio.run gets fresh connections)."""
    from rq import Queue, SimpleWorker  # noqa: PLC0415

    asyncio.run(_clear())
    asyncio.run(_with_history(3))
    # A queue of its own, so a running stack worker can't take the job first (see test_ping).
    queue = Queue(f"test-reputation-{uuid.uuid4().hex}", connection=get_sync_redis())
    job = reputation_jobs.enqueue_recalculate_all(queue)
    assert job.timeout == 30 * 60
    assert job.retries_left in (None, 0)
    SimpleWorker([queue], connection=get_sync_redis()).work(burst=True)
    job.refresh()
    assert job.is_finished
    result = job.return_value()
    assert result is not None
    assert result["developers"] >= 1
    assert asyncio.run(_statuses()) == [(JobStatus.SUCCEEDED, None)]


async def test_second_run_adds_no_log_rows() -> None:
    await _with_history(4)
    await asyncio.to_thread(reputation_jobs.recalculate_all)
    again = await asyncio.to_thread(reputation_jobs.recalculate_all)
    assert again["log_rows_added"] == 0


async def test_failure_is_recorded_without_the_message(monkeypatch: pytest.MonkeyPatch) -> None:
    await _clear()

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret detail that must not be stored")

    monkeypatch.setattr(reputation_engine, "recalculate_all", boom)
    with pytest.raises(RuntimeError):
        await asyncio.to_thread(reputation_jobs.recalculate_all)
    assert await _statuses() == [(JobStatus.FAILED, "RuntimeError")]
