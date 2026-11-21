"""`reputation.recalculate_all` (spec §11: admin-triggered, 30 min timeout, no retries).

Recalculates every developer with a completed-project history in one SYSTEM transaction, so a
failure leaves the previous reputations untouched. Re-running with the same histories and settings
changes nothing (the engine's log is idempotent). In Phase 6 it is started by the stage-2 seed and
`make reputation-recalculate`; the admin endpoint and button come with the Phase 12 console
(DECISIONS D92). The run is recorded in `jobs`.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from app.db.context import DbContext
from app.db.session import open_session
from app.jobs.runs import run_recorded
from app.services import platform_settings, reputation_engine

JOB_TYPE = "reputation.recalculate_all"
TIMEOUT_SECONDS = 30 * 60
RETRIES = 0


async def recalculate_everyone() -> dict[str, Any]:
    """One SYSTEM transaction over every developer with history."""
    async with open_session(DbContext.system(), job=True) as db:
        version, settings = await platform_settings.get_active(db)
        summary = await reputation_engine.recalculate_all(db, settings, version)
        await db.commit()
    out = asdict(summary)
    out["newcomer_review"] = str(summary.newcomer_review)
    return out


def recalculate_all() -> dict[str, Any]:
    """RQ entry point (sync wrapper); the run is recorded in `jobs` (§11)."""
    return asyncio.run(run_recorded(JOB_TYPE, recalculate_everyone))
