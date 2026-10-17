"""RQ worker entrypoint: `python -m app.jobs.worker`.

Listens on high → default → low, restarts after 500 jobs, and finishes the
current job on SIGTERM (RQ's warm shutdown) before exiting.
"""

from __future__ import annotations

from rq import Worker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.jobs.queues import MAX_JOBS_PER_WORKER, QUEUE_NAMES, get_queue, get_sync_redis


def main() -> None:
    """Start a worker on all queues in priority order."""
    configure_logging(get_settings().LOG_LEVEL)
    get_logger(__name__).info("worker_starting", queues=list(QUEUE_NAMES))
    worker = Worker([get_queue(n) for n in QUEUE_NAMES], connection=get_sync_redis())
    worker.work(max_jobs=MAX_JOBS_PER_WORKER, with_scheduler=False)


if __name__ == "__main__":
    main()
