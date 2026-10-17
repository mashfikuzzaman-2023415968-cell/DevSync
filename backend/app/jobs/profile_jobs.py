"""Phase 3 maintenance jobs (spec §11, §14.9): orphan uploads and expired skill-test attempts."""

from __future__ import annotations

import asyncio

from app.core.clock import get_clock
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.context import DbContext
from app.db.session import open_session
from app.services import files, skill_tests

log = get_logger(__name__)


async def purge_uploads() -> dict[str, int]:
    """Delete removed and never-attached files (rows and bytes)."""
    async with open_session(DbContext.system(), job=True) as db:
        counts = await files.purge_orphans(db, files.storage_for(get_settings()), get_clock().now())
    log.info("uploads_purged", **counts)
    return counts


async def score_expired() -> int:
    """Score attempts whose time ran out without a submit."""
    async with open_session(DbContext.system(), job=True) as db:
        done = await skill_tests.score_expired_attempts(db, get_clock().now())
    log.info("attempts_expired", scored=done)
    return done


def uploads_cleanup() -> dict[str, int]:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(purge_uploads())


def attempts_expire() -> int:
    """RQ entry point (sync wrapper)."""
    return asyncio.run(score_expired())
