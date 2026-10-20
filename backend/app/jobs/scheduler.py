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
from app.jobs import bidding_jobs, email_jobs, profile_jobs, tasks
from app.jobs.queues import get_queue

log = get_logger(__name__)
PING_INTERVAL_MINUTES = 5
EMAIL_INTERVAL_SECONDS = 30
EXPIRE_INTERVAL_MINUTES = 5
UPLOADS_CLEANUP_HOURS = 1
ATTEMPTS_EXPIRE_MINUTES = 1
BIDDING_DEADLINE_MINUTES = 5


def enqueue_ping() -> None:
    """Enqueue the heartbeat job on the low-priority queue."""
    get_queue("low").enqueue(tasks.ping, job_timeout=30, result_ttl=86400)


def enqueue_email_send() -> None:
    """Outbox delivery on the high queue (auth emails are urgent, §15.2)."""
    get_queue("high").enqueue(email_jobs.email_send, job_timeout=30, result_ttl=3600)


def enqueue_lifecycle_expire() -> None:
    """Cleanup of expired sessions, tokens, OTPs and idempotency keys."""
    get_queue("low").enqueue(email_jobs.lifecycle_expire, job_timeout=60, result_ttl=3600)


def enqueue_uploads_cleanup() -> None:
    """Orphan and deleted uploads (§14.9)."""
    get_queue("low").enqueue(profile_jobs.uploads_cleanup, job_timeout=300, result_ttl=3600)


def enqueue_attempts_expire() -> None:
    """Score skill-test attempts whose deadline passed without a submit."""
    get_queue("default").enqueue(profile_jobs.attempts_expire, job_timeout=60, result_ttl=3600)


def enqueue_bidding_deadline() -> None:
    """Close projects whose bidding deadline passed (→ FORMING, or notify too-few-bids)."""
    get_queue("default").enqueue(bidding_jobs.bidding_deadline, job_timeout=120, result_ttl=3600)


def build_scheduler() -> BlockingScheduler:
    """Create the scheduler with every periodic job registered (timezone Asia/Dhaka)."""
    scheduler = BlockingScheduler(timezone="Asia/Dhaka")
    scheduler.add_job(
        enqueue_ping, "interval", minutes=PING_INTERVAL_MINUTES, id="ping", coalesce=True
    )
    scheduler.add_job(
        enqueue_email_send,
        "interval",
        seconds=EMAIL_INTERVAL_SECONDS,
        id="email.send",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_lifecycle_expire,
        "interval",
        minutes=EXPIRE_INTERVAL_MINUTES,
        id="lifecycle.expire",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_uploads_cleanup,
        "interval",
        hours=UPLOADS_CLEANUP_HOURS,
        id="uploads.cleanup",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_attempts_expire,
        "interval",
        minutes=ATTEMPTS_EXPIRE_MINUTES,
        id="attempts.expire",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_bidding_deadline,
        "interval",
        minutes=BIDDING_DEADLINE_MINUTES,
        id="bidding.deadline",
        coalesce=True,
        max_instances=1,
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
