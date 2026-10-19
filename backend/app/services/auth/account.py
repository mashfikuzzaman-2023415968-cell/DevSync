"""The caller's own account and sessions (spec §10.2 Me, Auth sessions)."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.core.audit import write_audit
from app.core.authz import Principal, authorize
from app.core.errors import AuthError, NotFoundError
from app.core.sessions import SessionData, SessionPolicy, SessionStore
from app.models.identity import Session, User
from app.repositories import users as repo
from app.schemas.auth import MeResponse
from app.services.auth.common import AuthDeps


async def get_me(deps: AuthDeps, principal: Principal) -> MeResponse:
    """The caller's account view (no hashes or secrets)."""
    user = await repo.get_user(deps.db, principal.user_id)
    if user is None:
        raise AuthError
    credential = await repo.totp_credential(deps.db, user.id) if user.role == "ADMIN" else None
    return _me_view(user, bool(credential and credential.confirmed_at), principal)


def _me_view(user: User, totp_enabled: bool, principal: Principal) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=str(user.email),
        phone_e164=user.phone_e164,
        display_name=user.display_name,
        role=user.role.value,
        status="PENDING" if user.status.value == "PENDING" else "ACTIVE",
        email_verified=user.email_verified_at is not None,
        phone_verified=user.phone_verified_at is not None,
        totp_enabled=totp_enabled,
        totp_verified=principal.totp_verified,
        payment_verified=user.payment_verified_at is not None,
        created_at=user.created_at,
    )


async def update_me(deps: AuthDeps, principal: Principal, display_name: str) -> User:
    """Change editable profile basics. Commits."""
    user = await repo.get_user(deps.db, principal.user_id)
    if user is None:
        raise AuthError
    before = {"display_name": user.display_name}
    user.display_name = display_name
    await write_audit(
        deps.db,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        actor_role=principal.role,
        before=before,
        after={"display_name": display_name},
    )
    await deps.db.commit()
    return user


async def list_sessions(deps: AuthDeps, principal: Principal, now: datetime) -> list[Session]:
    """Live sessions (devices) of the caller."""
    return await repo.list_sessions(deps.db, principal.user_id, now)


async def revoke_session(
    deps: AuthDeps, principal: Principal, session_id: uuid.UUID, now: datetime
) -> None:
    """Sign out one device. Another user's session id is 'not found'. Commits."""
    row = await repo.get_session(deps.db, session_id)
    authorize(principal, "session.manage", row)
    if row is None or row.revoked_at is not None:
        raise NotFoundError
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    await store.revoke_by_id(deps.db, principal.user_id, session_id, now)
    await write_audit(
        deps.db,
        action="auth.session_revoked",
        entity_type="session",
        entity_id=session_id,
        actor_id=principal.user_id,
        actor_role=principal.role,
    )
    await deps.db.commit()


async def logout(
    deps: AuthDeps, principal: Principal, session: tuple[str, SessionData], now: datetime
) -> None:
    """End the current session. Commits."""
    token, data = session
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    await store.revoke(deps.db, token, data, now)
    await write_audit(
        deps.db,
        action="auth.logout",
        entity_type="session",
        entity_id=data.session_id,
        actor_id=principal.user_id,
        actor_role=principal.role,
    )
    await deps.db.commit()


async def logout_all(deps: AuthDeps, principal: Principal, now: datetime) -> int:
    """End every session of the caller (including this one). Commits."""
    store = SessionStore(deps.redis, SessionPolicy(deps.settings))
    count = await store.revoke_all(deps.db, principal.user_id, now)
    await write_audit(
        deps.db,
        action="auth.logout_all",
        entity_type="user",
        entity_id=principal.user_id,
        actor_id=principal.user_id,
        actor_role=principal.role,
        after={"revoked": count},
    )
    await deps.db.commit()
    return count
