"""Phase 9 workspace jobs (spec §11; D145, D151, D165): weekly check-in reminders and
monitoring (evaluate one project; the 15-minute sweep; the 30-second flush of changed projects)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from app.core import task_queue
from app.core.clock import get_clock
from app.core.logging import get_logger
from app.jobs.runs import run_recorded
from app.services import checkins, monitoring

log = get_logger(__name__)


async def remind_checkins(as_of: datetime | None = None) -> dict[str, int]:
    """Remind members who haven't checked in this week; record finished weeks that were missed
    (D145). `as_of` lets the test-only route run it "on" another day (D155)."""
    return await checkins.send_reminders(as_of or get_clock().now())


def checkin_reminders() -> dict[str, int]:
    """RQ entry point (Mondays 10:00 Asia/Dhaka; 5 min; 1 retry, §11); the run is recorded."""
    return asyncio.run(run_recorded("checkin.reminders", remind_checkins))


async def evaluate(project_id: str, as_of: datetime | None = None) -> dict[str, Any]:
    return await monitoring.evaluate_project(uuid.UUID(project_id), as_of or get_clock().now())


def monitoring_evaluate(project_id: str) -> dict[str, Any]:
    """RQ entry point (§11: 60 s, 1 retry). Re-reads everything from the database."""
    return asyncio.run(run_recorded("monitoring.evaluate", lambda: evaluate(project_id)))


async def sweep() -> int:
    """Every 15 minutes: queue an evaluation for every IN_PROGRESS project."""
    projects = await monitoring.in_progress_projects()
    for pid in projects:
        task_queue.enqueue("monitoring.evaluate", str(pid))
    return len(projects)


def monitoring_sweep() -> int:
    return asyncio.run(sweep())


async def flush(now: datetime | None = None) -> int:
    """Every 30 seconds: for each project changed ≥ 30 s ago, clear its mark, then queue an
    evaluation (D165). In this order a change committed before the clear is seen by the queued
    evaluation, and a change after it marks the project again for the next flush — so the last
    event of a burst is never lost."""
    at = now or get_clock().now()
    queued = 0
    for pid, score in await monitoring.due_projects(at):
        await monitoring.clear_if_unchanged(pid, score)
        task_queue.enqueue("monitoring.evaluate", pid)
        queued += 1
    return queued


def monitoring_flush() -> int:
    return asyncio.run(flush())
