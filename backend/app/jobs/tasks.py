"""Job functions executed by RQ workers.

Rule (§11): a job never trusts its queue payload; it reloads and re-authorizes
entities from the database. The Phase 0 `ping` job has no payload.
"""

from __future__ import annotations

from app.core.clock import get_clock
from app.core.logging import get_logger

log = get_logger(__name__)


def ping() -> str:
    """Prove the worker and scheduler pipeline works end to end."""
    at = get_clock().now().isoformat()
    log.info("job_ping", at=at)
    return f"pong {at}"
