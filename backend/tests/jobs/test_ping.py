"""The ping job runs through RQ (spec §11) and the scheduler registers it."""

from __future__ import annotations

import os

import pytest
from app.jobs import tasks
from app.jobs.scheduler import PING_INTERVAL_MINUTES, build_scheduler

pytestmark = pytest.mark.jobs


def test_ping_returns_pong() -> None:
    assert tasks.ping().startswith("pong ")


def test_scheduler_registers_ping() -> None:
    job = build_scheduler().get_job("ping")
    assert job is not None
    assert job.trigger.interval.total_seconds() == PING_INTERVAL_MINUTES * 60


def test_unknown_queue_is_rejected() -> None:
    from app.jobs.queues import get_queue  # noqa: PLC0415

    with pytest.raises(ValueError, match="Unknown queue"):
        get_queue("urgent")


@pytest.mark.skipif(not os.environ.get("REDIS_URL"), reason="needs Redis from the test stack")
def test_ping_through_rq_simple_worker() -> None:
    from app.jobs.queues import get_queue, get_sync_redis  # noqa: PLC0415
    from rq import SimpleWorker  # noqa: PLC0415

    queue = get_queue("low")
    job = queue.enqueue(tasks.ping, job_timeout=30)
    SimpleWorker([queue], connection=get_sync_redis()).work(burst=True)
    job.refresh()
    assert job.is_finished
    assert str(job.return_value()).startswith("pong ")
