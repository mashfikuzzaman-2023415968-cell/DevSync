"""Queue a background task by name from the service layer (spec §15.2).

Services may not import `app.jobs` (layering), so they queue a task by its dotted path; RQ
imports it in the worker. Only the names listed here can be queued, each with its §11 limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from redis import Redis
from rq import Queue, Retry

from app.core.config import get_settings


@dataclass(frozen=True)
class TaskSpec:
    path: str
    queue: str
    timeout: int
    retries: int


TASKS: dict[str, TaskSpec] = {
    "formation.run": TaskSpec("app.jobs.formation_jobs.formation_run", "high", 60, 0),
    "formation.explanations": TaskSpec(
        "app.jobs.formation_jobs.formation_explanations", "default", 120, 1
    ),
    "formation.verify": TaskSpec("app.jobs.formation_jobs.formation_verify", "default", 120, 0),
}


@lru_cache(maxsize=1)
def _redis() -> Redis:
    return Redis.from_url(get_settings().REDIS_URL, socket_connect_timeout=1, socket_timeout=5)


def enqueue(name: str, *args: str) -> str:
    """Queue task `name` with string arguments; returns the RQ job id."""
    spec = TASKS[name]
    job = Queue(spec.queue, connection=_redis()).enqueue(
        spec.path,
        *args,
        job_timeout=spec.timeout,
        result_ttl=3600,
        retry=Retry(max=spec.retries) if spec.retries else None,
    )
    return str(job.id)
