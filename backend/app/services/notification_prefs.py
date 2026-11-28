"""One user's notification switches for a §12 category (D162, D163, D153).

Shared by `notifications` (in-app rows) and `outbox` (emails), so both writers honour the same
switch. Missing rows mean the §12 defaults; an email switch only counts where §12 has an email.
Read as SYSTEM: the writer usually acts for someone else, and RLS keeps preference rows to
their owner.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.core.notification_types import CATEGORIES, NotificationType, category
from app.db.context import DbContext
from app.db.session import open_session
from app.models.workspace import NotificationPreference


@dataclass(frozen=True)
class Switches:
    in_app: bool
    email: bool


async def switches(user_id: uuid.UUID, kind: NotificationType | str) -> Switches:
    """The recipient's switches for the type's category, defaults filled in."""
    cat = category(kind)
    info = CATEGORIES[cat]
    async with open_session(DbContext.system(), job=True) as db:
        row = await db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.type == cat.value,
            )
        )
        in_app = row.in_app if row is not None else info.in_app
        email = row.email if row is not None else info.email
    return Switches(in_app=in_app, email=email and info.email_available)
