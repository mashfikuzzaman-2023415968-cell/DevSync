"""Append-only audit writer (spec §7.1, §14.11).

The application only INSERTs. The hash chain (`prev_hash`, `hash`) is computed
by the `audit_log_chain` trigger in the database, and UPDATE/DELETE are blocked
by trigger and by grants, so even a compromised app process cannot rewrite history.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import redact, request_id_var
from app.models.foundation import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Insert one audit row in the caller's transaction (before/after are redacted)."""
    await session.execute(
        insert(AuditLog).values(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=redact(before) if before is not None else None,
            after=redact(after) if after is not None else None,
            ip=ip,
            request_id=request_id_var.get(),
        )
    )


async def verify_chain(session: AsyncSession) -> int | None:
    """Return the `seq` of the first broken audit row, or None if the chain is intact."""
    result = await session.execute(select(func.audit_verify_chain()))
    value: int | None = result.scalar_one()
    return int(value) if value is not None else None
