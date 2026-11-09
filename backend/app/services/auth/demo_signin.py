"""Quick sign-in for the seeded demo accounts (demo and development only).

Presenting a demo means switching between a dozen people. This starts a normal session for one
of the seeded `@devsync.local` clients or developers without typing a password. Narrow on purpose:

- only the routes mounted by `create_app` where `Settings.sms_sandbox_enabled` call it (the
  development and test environments and the offline demo stack), so it does not exist in a real
  deployment, and `assert_no_sandbox_routes` refuses to start if it does;
- only addresses ending `@devsync.local` (the seed's domain; no registration can create one,
  and real addresses are never accepted), never an administrator (they need their TOTP code), and
  never a suspended or deleted account;
- every use is written to the audit log (`auth.demo_signin`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.errors import AuthError, ErrorCode
from app.core.redirects import safe_redirect
from app.db.context import DbContext
from app.db.session import open_session
from app.models.identity import User, UserRole, UserStatus
from app.repositories import users as repo
from app.services.auth import login as login_service
from app.services.auth.common import AuthDeps, act_as

DEMO_DOMAIN = "@devsync.local"


@dataclass(frozen=True)
class DemoAccount:
    """One seeded demo person."""

    email: str
    name: str
    role: str


async def list_accounts() -> list[DemoAccount]:
    """The seeded clients and developers, clients first, then by name."""
    async with open_session(DbContext.system(), job=True) as db:
        stmt = (
            select(User.email, User.display_name, User.role)
            .where(func.lower(User.email).like(f"%{DEMO_DOMAIN}"))
            .where(User.role != UserRole.ADMIN)
            .where(User.status == UserStatus.ACTIVE)
        )
        rows = (await db.execute(stmt)).all()
    accounts = [
        DemoAccount(email=str(e).lower(), name=n, role=r.value if hasattr(r, "value") else str(r))
        for e, n, r in rows
    ]
    return sorted(accounts, key=lambda a: (a.role != "CLIENT", a.name))


async def sign_in(
    deps: AuthDeps, now: datetime, client: login_service.ClientInfo, *, email: str
) -> login_service.SignedIn:
    """Start a session for a seeded demo account. Commits. Anything else is a plain 401."""
    wanted = email.strip().lower()
    if not wanted.endswith(DEMO_DOMAIN):
        raise AuthError(code=ErrorCode.INVALID_CREDENTIALS)
    record = await repo.login_lookup(deps.db, wanted)
    if (
        record is None
        or record.role == "ADMIN"
        or record.status in (UserStatus.SUSPENDED.value, UserStatus.DELETED.value)
    ):
        raise AuthError(code=ErrorCode.INVALID_CREDENTIALS)
    await act_as(deps.db, record.id, record.role)
    user = await repo.get_user(deps.db, record.id)
    if user is None:
        raise AuthError(code=ErrorCode.INVALID_CREDENTIALS)
    await write_audit(
        deps.db,
        action="auth.demo_signin",
        entity_type="user",
        entity_id=record.id,
        actor_id=record.id,
        actor_role=record.role,
        ip=client.ip,
    )
    return await login_service.start_session(
        deps,
        now,
        client,
        user_id=user.id,
        role=record.role,
        status=str(user.status),
        email=str(user.email),
        display_name=user.display_name,
        redirect_to=safe_redirect(None, record.role, str(user.status)),
        totp_verified=False,
    )
