"""Run records for background jobs in the `jobs` table (spec §7.8, §11 "each job records
progress in `jobs`").

`run_recorded(type, work)` inserts a RUNNING row (started_at, progress 0) and commits it before
the work starts, then marks it SUCCEEDED (progress 100) or FAILED with an error code — the
exception's class name only, never its message (which might carry data). Each write is its own
short SYSTEM transaction on the worker engine, so no transaction stays open while the job runs
and a crash mid-job leaves a RUNNING row that `abandon_stale_runs` later closes as FAILED.

Scheduled jobs have no requester (`requested_by` NULL): RLS lets only admins and SYSTEM read
them (migration 0002) and only SYSTEM write or delete them (0009). Old system runs are pruned by
`lifecycle.expire` after `RUN_RETENTION`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import TypeVar

from sqlalchemy import delete, insert, update

from app.core.clock import get_clock
from app.core.logging import get_logger
from app.db.context import DbContext
from app.db.session import open_session
from app.models.foundation import Job, JobStatus

log = get_logger(__name__)
T = TypeVar("T")

RUN_RETENTION = timedelta(days=7)
# Longer than any scheduled job's RQ timeout (§11, the longest is 10 min): a row still RUNNING
# after this belongs to a worker that died.
STALE_AFTER = timedelta(hours=1)
ABANDONED = "ABANDONED"
MAX_ERROR_CODE = 64


async def _start(job_type: str, now: datetime) -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        job_id = await db.scalar(
            insert(Job)
            .values(type=job_type, status=JobStatus.RUNNING, progress=0, started_at=now)
            .returning(Job.id)
        )
        await db.commit()
    if job_id is None:  # pragma: no cover - INSERT … RETURNING always yields the id
        raise LookupError("job run")
    return uuid.UUID(str(job_id))


async def _finish(job_id: uuid.UUID, status: JobStatus, error_code: str | None) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status=status,
                progress=100 if status is JobStatus.SUCCEEDED else Job.progress,
                error_code=error_code,
                finished_at=get_clock().now(),
            )
        )
        await db.commit()


async def run_recorded(  # noqa: UP047 - TypeVar, not PEP 695, so Semgrep can parse the module
    job_type: str, work: Callable[[], Awaitable[T]]
) -> T:
    """Run `work` with a `jobs` row recording its start, finish and outcome."""
    job_id = await _start(job_type, get_clock().now())
    try:
        result = await work()
    except Exception as exc:
        try:
            await _finish(job_id, JobStatus.FAILED, type(exc).__name__[:MAX_ERROR_CODE])
        except Exception:  # the job's own error matters more; the row is closed later
            log.exception("job_run_record_failed", job_type=job_type)
        raise
    try:
        await _finish(job_id, JobStatus.SUCCEEDED, None)
    except Exception:  # the work is done; don't fail (and retry) it over the record
        log.exception("job_run_record_failed", job_type=job_type)
    return result


async def prune_runs(now: datetime) -> dict[str, int]:
    """Close runs abandoned by a dead worker and delete old system runs (requester NULL)."""
    async with open_session(DbContext.system(), job=True) as db:
        abandoned = await db.execute(
            update(Job)
            .where(Job.status == JobStatus.RUNNING, Job.started_at < now - STALE_AFTER)
            .values(status=JobStatus.FAILED, error_code=ABANDONED, finished_at=now)
        )
        pruned = await db.execute(
            delete(Job).where(
                Job.requested_by.is_(None),
                Job.status.in_([JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]),
                Job.created_at < now - RUN_RETENTION,
            )
        )
        await db.commit()
    return {
        "jobs_abandoned": int(abandoned.rowcount or 0),  # type: ignore[attr-defined]
        "jobs_pruned": int(pruned.rowcount or 0),  # type: ignore[attr-defined]
    }
