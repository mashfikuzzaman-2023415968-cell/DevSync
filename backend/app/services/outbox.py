"""Enqueue transactional emails in the caller's transaction (transactional outbox, §15.6).

Phase 9 (D163): the six account and security templates (`ACCOUNT_TEMPLATES`) are always sent
and name no one. Every other template belongs to a notification type (`TEMPLATE_TYPE`) and names
its recipient, whose email switch for that §12 category decides whether it is queued at all.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notification_types import ACCOUNT_TEMPLATES, TEMPLATE_TYPE
from app.integrations.email import TEMPLATES, validate_address
from app.models.identity import EmailOutbox
from app.services.notification_prefs import switches


async def enqueue(
    db: AsyncSession,
    *,
    to: str,
    template: str,
    payload: dict[str, Any],
    user_id: uuid.UUID | None = None,
) -> bool:
    """Write one email to the outbox; it is sent only if the transaction commits. Returns False
    when the recipient switched this kind of email off."""
    if template not in TEMPLATES:
        raise KeyError(template)
    if template not in ACCOUNT_TEMPLATES:
        kind = TEMPLATE_TYPE.get(template)
        if kind is None:
            raise KeyError(f"{template} has no notification type (D163)")
        if user_id is None:
            raise ValueError(f"{template} must name its recipient (D163)")
        if not (await switches(user_id, kind)).email:
            return False
    # Core insert: the web role may add outbox rows but cannot read them back (RLS).
    await db.execute(
        insert(EmailOutbox).values(
            to_email=validate_address(to), template=template, payload=payload
        )
    )
    return True
