"""Evidence events (spec §9.1.6; DECISIONS D149, D167).

A web request records its event through the `record_activity()` definer, in the same transaction
as the change it describes: the database sets the actor to the caller and refuses
non-participants and unknown types. SYSTEM paths (team services, jobs, admin decisions) insert
the row directly in their own transaction. Payloads are validated against one schema per type
(`app/schemas/activity.py`) before they are written, and never carry money or another member's
private data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import ActivityEvent
from app.schemas.activity import validate_event_data


async def record(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    subject_id: uuid.UUID | None,
    data: dict[str, Any],
    at: datetime,
) -> uuid.UUID:
    """Record an event for the caller of a web request (through the definer)."""
    payload = validate_event_data(type, data)
    event_id = await db.scalar(
        select(
            func.record_activity(
                project_id,
                type,
                entity_type,
                entity_id,
                subject_id,
                literal(payload, JSONB),
                at,
            )
        )
    )
    if event_id is None:  # the definer always returns an id or raises
        raise RuntimeError("record_activity returned nothing")
    return uuid.UUID(str(event_id))


def record_system(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    subject_id: uuid.UUID | None,
    data: dict[str, Any],
    at: datetime,
) -> ActivityEvent:
    """Add an event in a SYSTEM session (team services, jobs, admin decisions)."""
    event = ActivityEvent(
        project_id=project_id,
        actor_id=actor_id,
        subject_id=subject_id,
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        data=validate_event_data(type, data),
        at=at,
    )
    db.add(event)
    return event
