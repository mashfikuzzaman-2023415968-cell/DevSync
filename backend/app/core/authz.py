"""Central authorization policy: `authorize(principal, action, resource)` (spec §2.2, §14.5).

Deny by default: an action without a registered policy is refused. Outcomes map
to the spec's status semantics:
- no session → 401 (`AuthError`);
- signed in but the wrong role → 403 (`ForbiddenError`);
- the right role but not this object → 404 (`NotFoundError`, existence not revealed);
- admin-only areas answer 404 to everyone else so they are not confirmed to exist (§14.17).

Policies are small functions registered per action; later phases add actions
and ownership checks (client owns project, member of team, bidder owns bid).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.errors import AuthError, ErrorCode, ForbiddenError, NotFoundError

ROLES = ("CLIENT", "DEVELOPER", "ADMIN")
# Admin-only actions answer 404 to everyone else, anonymous callers included (§14.17).
HIDDEN_ACTIONS = frozenset({"totp.manage"})


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, built only from the server-side session."""

    user_id: uuid.UUID
    role: str
    status: str
    session_id: uuid.UUID
    totp_verified: bool
    step_up_until: datetime | None

    @property
    def is_admin(self) -> bool:
        """Admin with a TOTP-verified session (admins without TOTP get no admin powers)."""
        return self.role == "ADMIN" and self.totp_verified

    @property
    def is_active(self) -> bool:
        """Verified, not suspended."""
        return self.status == "ACTIVE"

    def has_step_up(self, now: datetime) -> bool:
        """TOTP re-confirmed within the step-up window (§14.4)."""
        return self.step_up_until is not None and now < self.step_up_until


Policy = Callable[[Principal, Any], None]
_POLICIES: dict[str, Policy] = {}


def policy(action: str) -> Callable[[Policy], Policy]:
    """Register the policy for `action` (each action exactly once)."""

    def register(fn: Policy) -> Policy:
        if action in _POLICIES:
            raise ValueError(f"duplicate policy for {action}")
        _POLICIES[action] = fn
        return fn

    return register


def registered_actions() -> frozenset[str]:
    """All actions with a policy (used by tests)."""
    return frozenset(_POLICIES)


def authorize(principal: Principal | None, action: str, resource: Any = None) -> None:
    """Raise unless `principal` may perform `action` on `resource`."""
    fn = _POLICIES.get(action)
    if fn is None:
        raise ForbiddenError("This action is not allowed.")  # deny by default
    if principal is None:
        if action.startswith("admin.") or action in HIDDEN_ACTIONS:
            raise NotFoundError
        raise AuthError
    fn(principal, resource)


# --------------------------------------------------------------------------- helpers


def _require_active(p: Principal) -> None:
    if p.status == "PENDING":
        raise ForbiddenError(code=ErrorCode.VERIFICATION_REQUIRED)
    if not p.is_active:
        raise AuthError


def _require_admin(p: Principal) -> None:
    if not p.is_admin or not p.is_active:
        raise NotFoundError  # hide the admin area (§14.17)


# --------------------------------------------------------------------------- Phase 1 policies


@policy("account.read")
def _account_read(p: Principal, _r: Any) -> None:
    """Any signed-in user (PENDING included) may read their own account."""
    if p.status not in ("PENDING", "ACTIVE"):
        raise AuthError


@policy("account.verify")
def _account_verify(p: Principal, _r: Any) -> None:
    """Verification endpoints are for PENDING (and ACTIVE re-checks) accounts."""
    if p.status not in ("PENDING", "ACTIVE"):
        raise AuthError


@policy("account.update")
def _account_update(p: Principal, _r: Any) -> None:
    _require_active(p)


@policy("session.manage")
def _session_manage(p: Principal, resource: Any) -> None:
    """Own sessions only; another user's session id is 'not found'."""
    if p.status not in ("PENDING", "ACTIVE"):
        raise AuthError
    owner = getattr(resource, "user_id", None)
    if resource is not None and owner != p.user_id:
        raise NotFoundError


@policy("totp.manage")
def _totp_manage(p: Principal, _r: Any) -> None:
    """Only admins have TOTP; others are told the area doesn't exist."""
    if p.role != "ADMIN" or not p.is_active:
        raise NotFoundError


@policy("admin.access")
def _admin_access(p: Principal, _r: Any) -> None:
    _require_admin(p)


# --------------------------------------------------------------------------- Phase 3 policies


def _require_role(p: Principal, role: str) -> None:
    _require_active(p)
    if p.role != role:
        raise ForbiddenError(code=ErrorCode.ROLE_NOT_ALLOWED)


@policy("profile.developer")
def _profile_developer(p: Principal, _r: Any) -> None:
    """Developers manage their own profile, portfolio and evidence."""
    _require_role(p, "DEVELOPER")


@policy("profile.client")
def _profile_client(p: Principal, _r: Any) -> None:
    """Clients manage their own organisation profile."""
    _require_role(p, "CLIENT")


@policy("catalog.read")
def _catalog_read(p: Principal, _r: Any) -> None:
    """Skills, tests and other developers' profiles: any verified account."""
    _require_active(p)


@policy("test.take")
def _test_take(p: Principal, resource: Any) -> None:
    """Developers take tests; an attempt belongs to its developer (others: not found)."""
    _require_role(p, "DEVELOPER")
    owner = getattr(resource, "user_id", None)
    if resource is not None and owner != p.user_id:
        raise NotFoundError


# --------------------------------------------------------------------------- Phase 4 policies


def _require_client_or_admin(p: Principal) -> None:
    _require_active(p)
    if p.role != "CLIENT" and not p.is_admin:
        raise ForbiddenError(code=ErrorCode.ROLE_NOT_ALLOWED)


@policy("project.create")
def _project_create(p: Principal, _r: Any) -> None:
    """Clients create and own projects."""
    _require_role(p, "CLIENT")


@policy("project.write")
def _project_write(p: Principal, _r: Any) -> None:
    """Edit a draft project and its plan; object ownership is checked in the service (→ 404)."""
    _require_role(p, "CLIENT")


@policy("project.read")
def _project_read(p: Principal, _r: Any) -> None:
    """A project's own client, or an admin; the service hides other clients' projects (→ 404)."""
    _require_client_or_admin(p)


@policy("project.cancel")
def _project_cancel(p: Principal, _r: Any) -> None:
    """The owning client cancels; an admin may cancel with a reason (§2.2)."""
    _require_client_or_admin(p)


@policy("payment.verify")
def _payment_verify(p: Principal, _r: Any) -> None:
    """Clients mark their simulated payment method verified (D39)."""
    _require_role(p, "CLIENT")


# --------------------------------------------------------------------------- Phase 5 policies


@policy("marketplace.read")
def _marketplace_read(p: Principal, _r: Any) -> None:
    """Developers search and see recommended projects (§9.16)."""
    _require_role(p, "DEVELOPER")


@policy("bid.create")
def _bid_create(p: Principal, _r: Any) -> None:
    """Developers place sealed bids; the service enforces the BIDDING state and one-per-project."""
    _require_role(p, "DEVELOPER")


@policy("bid.write")
def _bid_write(p: Principal, _r: Any) -> None:
    """Edit or withdraw one's own bid; bid ownership is checked in the service (→ 404)."""
    _require_role(p, "DEVELOPER")


@policy("bid.read")
def _bid_read(p: Principal, _r: Any) -> None:
    """A developer reads their own bids (`/me/bids`); the service scopes to the caller."""
    _require_role(p, "DEVELOPER")


@policy("bid.view")
def _bid_view(p: Principal, _r: Any) -> None:
    """A client reads their own project's bids (sealed, §14.5); an admin may too.

    The service returns the bids only for the caller's own project; a developer never reaches
    this view (wrong role → 403), and a foreign project is 404.
    """
    _require_client_or_admin(p)


@policy("reputation.read")
def _reputation_read(p: Principal, _r: Any) -> None:
    """Reputation snapshots are a public value for any active account (spec §14.15)."""
    _require_active(p)
