"""Team formation jobs (spec §11): RQ entry points; the work is in
`app/services/formation_runner.py`.

- `formation.run` (high queue, 60 s, no retry);
- `formation.explanations` (default queue, 120 s, one retry; recorded in `jobs`);
- `formation.verify` (default queue, 120 s, no retry);
- `formation.repair` (default queue, 60 s, one retry; team repair, §9.9).

Services queue them by name through `app/core/task_queue.py`.
"""

from __future__ import annotations

import asyncio
import uuid

from app.jobs.runs import run_recorded
from app.services.formation_runner import (
    build_result,
    execute_repair,
    execute_run,
    execute_verify,
    explanations_for,
    problem_from,
    write_explanations,
)

__all__ = [
    "build_result",
    "execute_repair",
    "execute_run",
    "execute_verify",
    "explanations_for",
    "formation_explanations",
    "formation_repair",
    "formation_run",
    "formation_verify",
    "problem_from",
    "write_explanations",
]


def formation_run(run_id: str) -> str:
    """RQ entry point for `formation.run`."""
    return asyncio.run(execute_run(uuid.UUID(run_id))).value


def formation_explanations(run_id: str) -> dict[str, int]:
    """RQ entry point for `formation.explanations` (recorded in `jobs`)."""
    return asyncio.run(
        run_recorded("formation.explanations", lambda: write_explanations(uuid.UUID(run_id)))
    )


def formation_verify(run_id: str, job_id: str) -> bool:
    """RQ entry point for `formation.verify`."""
    return asyncio.run(execute_verify(uuid.UUID(run_id), uuid.UUID(job_id)))


def formation_repair(proposal_id: str) -> str:
    """RQ entry point for `formation.repair`."""
    return asyncio.run(execute_repair(uuid.UUID(proposal_id)))
