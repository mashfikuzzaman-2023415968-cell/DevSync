"""Scheduler entrypoint: `python -m app.jobs.scheduler`.

APScheduler only *enqueues* RQ jobs; the work itself runs in workers, so a
scheduler restart never loses or duplicates work in progress. Later phases add
the §11 schedules here.
"""

from __future__ import annotations

import signal
from types import FrameType

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.jobs import tasks
from app.jobs.queues import get_queue

log = get_logger(__name__)
PING_INTERVAL_MINUTES = 5


def enqueue_ping() -> None:
    """Enqueue the heartbeat job on the low-priority queue."""
    get_queue("low").enqueue(tasks.ping, job_timeout=30, result_ttl=86400)


def build_scheduler() -> BlockingScheduler:
    """Create the scheduler with every periodic job registered (timezone Asia/Dhaka)."""
    scheduler = BlockingScheduler(timezone="Asia/Dhaka")
    scheduler.add_job(
        enqueue_ping, "interval", minutes=PING_INTERVAL_MINUTES, id="ping", coalesce=True
    )
    return scheduler


def main() -> None:
    """Run until SIGTERM/SIGINT, then shut down cleanly."""
    configure_logging(get_settings().LOG_LEVEL)
    scheduler = build_scheduler()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        log.info("scheduler_stopping", signal=signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("scheduler_starting")
    enqueue_ping()
    scheduler.start()


if __name__ == "__main__":
    main()
