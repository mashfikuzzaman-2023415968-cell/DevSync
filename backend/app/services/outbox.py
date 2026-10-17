"""Enqueue transactional emails in the caller's transaction (transactional outbox, §15.6)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.email import TEMPLATES, validate_address
from app.models.identity import EmailOutbox


async def enqueue(db: AsyncSession, *, to: str, template: str, payload: dict[str, Any]) -> None:
    """Write one email to the outbox; it is sent only if the transaction commits."""
    if template not in TEMPLATES:
        raise KeyError(template)
    # Core insert: the web role may add outbox rows but cannot read them back (RLS).
    await db.execute(
        insert(EmailOutbox).values(
            to_email=validate_address(to), template=template, payload=payload
        )
    )
