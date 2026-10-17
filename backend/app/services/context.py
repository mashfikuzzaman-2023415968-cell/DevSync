"""The acting context passed to Phase 3+ services: who acts, through which DB session, when."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Principal
from app.core.config import Settings


@dataclass(frozen=True)
class Ctx:
    """Who is acting, with what, at what time."""

    db: AsyncSession
    settings: Settings
    principal: Principal
    now: datetime

    @property
    def uid(self) -> uuid.UUID:
        return self.principal.user_id
