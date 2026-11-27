"""Scheduler entrypoint: `python -m app.jobs.scheduler`.

APScheduler only *enqueues* RQ jobs; the work itself runs in workers, so a
scheduler restart never loses or duplicates work in progress. Later phases add
the §11 schedules here.
"""

from __future__ import annotations

import signal
from types import FrameType

from apscheduler.schedulers.blocking import BlockingScheduler
from rq import Retry

from app.core.config import get_settings, validate_production
from app.core.logging import configure_logging, get_logger
from app.jobs import (
    bid_notice_jobs,
    bidding_jobs,
    email_jobs,
    profile_jobs,
    tasks,
    workspace_jobs,
)
from app.jobs.queues import get_queue

log = get_logger(__name__)
PING_INTERVAL_MINUTES = 5
EMAIL_INTERVAL_SECONDS = 30
EXPIRE_INTERVAL_MINUTES = 5
UPLOADS_CLEANUP_HOURS = 1
ATTEMPTS_EXPIRE_MINUTES = 1
BIDDING_DEADLINE_MINUTES = 5
NEW_BID_NOTICE_HOURS = 1
BID_DIGEST_HOUR = 8  # Asia/Dhaka, the morning after
CHECKIN_REMINDER_HOUR = 10  # Mondays, Asia/Dhaka (§11)
MONITORING_SWEEP_MINUTES = 15  # §11
MONITORING_FLUSH_SECONDS = 30  # D165: changed projects, debounced 30 s


def enqueue_checkin_reminders() -> None:
    """Weekly check-in reminders and missed weeks (§11: 5 min, 1 retry; D145)."""
    get_queue("default").enqueue(
        workspace_jobs.checkin_reminders, job_timeout=300, result_ttl=86400, retry=Retry(max=1)
    )


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


def enqueue_new_bid_notices() -> None:
    """Hourly in-app "new bids on your project" notices (§12, batched hourly)."""
    get_queue("default").enqueue(bid_notice_jobs.new_bid_notices, job_timeout=120, result_ttl=3600)


def enqueue_bid_digests() -> None:
    """Daily email digest of yesterday's new bids (§12)."""
    get_queue("low").enqueue(bid_notice_jobs.bid_digests, job_timeout=300, result_ttl=86400)


def enqueue_monitoring_sweep() -> None:
    """Evaluate every IN_PROGRESS project (§11, every 15 min)."""
    get_queue("default").enqueue(workspace_jobs.monitoring_sweep, job_timeout=60, result_ttl=3600)


def enqueue_monitoring_flush() -> None:
    """Evaluate projects changed at least 30 s ago (D165)."""
    get_queue("default").enqueue(workspace_jobs.monitoring_flush, job_timeout=30, result_ttl=600)


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
    scheduler.add_job(
        enqueue_new_bid_notices,
        "interval",
        hours=NEW_BID_NOTICE_HOURS,
        id="bids.new_notices",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_bid_digests,
        "cron",
        hour=BID_DIGEST_HOUR,
        minute=0,
        id="bids.daily_digest",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_checkin_reminders,
        "cron",
        day_of_week="mon",
        hour=CHECKIN_REMINDER_HOUR,
        minute=0,
        id="checkin.reminders",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_monitoring_sweep,
        "interval",
        minutes=MONITORING_SWEEP_MINUTES,
        id="monitoring.sweep",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        enqueue_monitoring_flush,
        "interval",
        seconds=MONITORING_FLUSH_SECONDS,
        id="monitoring.flush",
        coalesce=True,
        max_instances=1,
    )
    return scheduler


def main() -> None:
    """Run until SIGTERM/SIGINT, then shut down cleanly."""
    validate_production(get_settings())  # same fail-closed checks as the API (§14.18)
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
