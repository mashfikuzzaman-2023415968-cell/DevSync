"""Row-level-security request context (spec §14.15).

Every database transaction starts with
`set_config('app.user_id', …, true), set_config('app.role', …, true)` — the `true`
makes them transaction-local, so they are safe with PgBouncer transaction pooling
and can never leak into another request. The values come from the server-side
session, never from the request body. Without a context the role is GUEST and
user-scoped policies match nothing (fail closed).

SYSTEM is only meaningful on the worker's database role (`is_system()` checks
`current_user`), so web code setting it would gain nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

CONTEXT_KEY = "db_context"


@dataclass(frozen=True)
class DbContext:
    """Who the current transaction acts for."""

    user_id: uuid.UUID | None
    role: str  # GUEST | CLIENT | DEVELOPER | ADMIN | SYSTEM

    @classmethod
    def guest(cls) -> DbContext:
        """Anonymous request."""
        return cls(user_id=None, role="GUEST")

    @classmethod
    def system(cls, acting_for: uuid.UUID | None = None) -> DbContext:
        """Background job (only effective on the `devsync_worker` connection)."""
        return cls(user_id=acting_for, role="SYSTEM")


def _context_statement(ctx: DbContext) -> Any:
    return select(
        func.set_config("app.user_id", str(ctx.user_id) if ctx.user_id else "", True),
        func.set_config("app.role", ctx.role, True),
    )


class RlsSession(Session):
    """ORM session class that applies the request context at the start of every transaction."""


@event.listens_for(RlsSession, "after_begin")
def _apply_context(session: Session, _tx: SessionTransaction, connection: Connection) -> None:
    ctx = session.info.get(CONTEXT_KEY) or DbContext.guest()
    connection.execute(_context_statement(ctx))


async def set_context(session: AsyncSession, ctx: DbContext) -> None:
    """Switch the context (e.g. right after login) for the rest of this and later transactions."""
    session.info[CONTEXT_KEY] = ctx
    if session.in_transaction():
        await session.execute(_context_statement(ctx))


def get_context(session: AsyncSession) -> DbContext:
    """The context the session currently applies."""
    ctx = session.info.get(CONTEXT_KEY)
    return ctx if isinstance(ctx, DbContext) else DbContext.guest()
