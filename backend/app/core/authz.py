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


@policy("assessment.take")
def _assessment_take(p: Principal, resource: Any) -> None:
    """Role assessments (role assessment spec §6.2, §9): developers only — clients and admins get
    ROLE_NOT_ALLOWED. A developer who hasn't finished verifying is let through so the status
    can say what to do next (the service answers ACCOUNT_NOT_VERIFIED); an attempt belongs to
    its developer (others: not found)."""
    if p.status not in ("PENDING", "ACTIVE"):
        raise AuthError
    if p.role != "DEVELOPER":
        raise ForbiddenError(code=ErrorCode.ROLE_NOT_ALLOWED)
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


@policy("project.terms")
def _project_terms(p: Principal, _r: Any) -> None:
    """The owning client changes a BIDDING project's terms through the too-few-bids actions
    (§9.19); ownership and the BIDDING state are checked in the service (→ 404 / 409)."""
    _require_role(p, "CLIENT")


@policy("reputation.read")
def _reputation_read(p: Principal, _r: Any) -> None:
    """Reputation snapshots are a public value for any active account (spec §14.15)."""
    _require_active(p)


@policy("reputation.history")
def _reputation_history(p: Principal, _r: Any) -> None:
    """A developer reads how their own reputation changed (`/me/reputation/history`); the
    service and row-level security scope it to the caller."""
    _require_role(p, "DEVELOPER")


@policy("job.read")
def _job_read(p: Principal, _r: Any) -> None:
    """A job's status and live events: its requester, or an admin; the service and row-level
    security answer 404 for anyone else's job (D107)."""
    _require_active(p)


@policy("formation.run")
def _formation_run(p: Principal, _r: Any) -> None:
    """The owning client starts team formation; ownership is checked in the service (→ 404)."""
    _require_role(p, "CLIENT")


@policy("formation.confirm")
def _formation_confirm(p: Principal, _r: Any) -> None:
    """Only the owning client confirms a team (admins can read and verify, not confirm)."""
    _require_role(p, "CLIENT")


@policy("formation.read")
def _formation_read(p: Principal, _r: Any) -> None:
    """A project's own client, or an admin; others' runs are 404 in the service and RLS."""
    _require_active(p)
    if p.role != "CLIENT" and not p.is_admin:
        raise ForbiddenError


@policy("bid.explanation")
def _bid_explanation(p: Principal, _r: Any) -> None:
    """A bidder reads why their own bid was not selected (admins too); sealed by RLS."""
    _require_active(p)
    if p.role != "DEVELOPER" and not p.is_admin:
        raise ForbiddenError


# --------------------------------------------------------------------------- Phase 8 policies
# Object checks (whose invitation, which project, the lead of *this* project) live in
# `services/team.py` and `services/repair.py` and answer 404; RLS is the second gate (§14.13 row 8).


@policy("invitation.respond")
def _invitation_respond(p: Principal, _r: Any) -> None:
    """Developers answer their own invitations and see their own dashboard invitations."""
    _require_role(p, "DEVELOPER")


@policy("team.read")
def _team_read(p: Principal, _r: Any) -> None:
    """The project's client, its current members, or an admin (decided per project → 404)."""
    _require_active(p)


@policy("team.list")
def _team_list(p: Principal, _r: Any) -> None:
    """A client's own teams (`/client/teams`)."""
    _require_role(p, "CLIENT")


@policy("team.lead.choose")
def _team_lead_choose(p: Principal, _r: Any) -> None:
    """Only the project's client chooses the lead (§1.6 rule 2)."""
    _require_role(p, "CLIENT")


@policy("team.lead.decide")
def _team_lead_decide(p: Principal, _r: Any) -> None:
    """The client approves or rejects a lead-change request (§1.6 rule 4)."""
    _require_role(p, "CLIENT")


@policy("team.lead.decline")
def _team_lead_decline(p: Principal, _r: Any) -> None:
    """The lead of this project declines the role (§1.6 rule 3)."""
    _require_role(p, "DEVELOPER")


@policy("team.lead.request")
def _team_lead_request(p: Principal, _r: Any) -> None:
    """An active member asks for (or withdraws) a lead change (§1.6 rule 4)."""
    _require_role(p, "DEVELOPER")


@policy("team.leave")
def _team_leave(p: Principal, _r: Any) -> None:
    _require_role(p, "DEVELOPER")


@policy("team.removal.request")
def _team_removal_request(p: Principal, _r: Any) -> None:
    _require_role(p, "CLIENT")


@policy("team.repair")
def _team_repair(p: Principal, _r: Any) -> None:
    """Repair proposals: the client and admins only — developers never see candidates."""
    _require_active(p)
    if p.role != "CLIENT" and not p.is_admin:
        raise ForbiddenError


@policy("team.repair.choose")
def _team_repair_choose(p: Principal, _r: Any) -> None:
    """Invite a replacement, reopen a place, raise the budget: the client."""
    _require_role(p, "CLIENT")


@policy("project.start")
def _project_start(p: Principal, _r: Any) -> None:
    """The client starts their project once the team and lead are confirmed (D119)."""
    _require_role(p, "CLIENT")


@policy("notifications.read")
def _notifications_read(p: Principal, _r: Any) -> None:
    """Any signed-in account (PENDING included) reads and marks its own notifications."""
    if p.status not in ("PENDING", "ACTIVE"):
        raise AuthError


# --------------------------------------------------------------------------- Phase 9 workspace
# The project decides the rest (services/workspace.py, D142): participants read, 404 for anyone
# else; lead powers only in the lead's own project; the client reads tasks and comments, posts
# and uploads; admins read monitoring and never write. These policies only fix the account side.


@policy("workspace.read")
def _workspace_read(p: Principal, _r: Any) -> None:
    """A participant of the project, or an admin where the endpoint allows it."""
    _require_active(p)


@policy("workspace.task.lead")
def _workspace_task_lead(p: Principal, _r: Any) -> None:
    """Create, edit, delete tasks and dependencies: the project's lead (decided per project)."""
    _require_active(p)
    if p.role != "DEVELOPER":
        raise ForbiddenError("Only the team lead can do this.")


@policy("workspace.task.work")
def _workspace_task_work(p: Principal, _r: Any) -> None:
    """Move tasks and add evidence: the assignee or the lead; never the client (§1.6)."""
    _require_active(p)
    if p.role != "DEVELOPER":
        raise ForbiddenError("Clients watch progress; the team moves the tasks.")


@policy("workspace.checkin.post")
def _workspace_checkin_post(p: Principal, _r: Any) -> None:
    """Weekly check-ins: ACTIVE members (decided per project); the client reads and replies."""
    _require_active(p)
    if p.role != "DEVELOPER":
        raise ForbiddenError("Team members post check-ins; clients read and reply to them.")


@policy("workspace.my_projects")
def _workspace_my_projects(p: Principal, _r: Any) -> None:
    """A developer's own projects (§13.5 #13); clients have their own project list."""
    _require_active(p)
    if p.role != "DEVELOPER":
        raise ForbiddenError("My projects lists the teams you work in.")


@policy("workspace.write")
def _workspace_write(p: Principal, _r: Any) -> None:
    """Comments, discussion and files: participants (client included); admins later (D142)."""
    _require_active(p)
    if p.role not in ("CLIENT", "DEVELOPER"):
        raise ForbiddenError("Admins see workspace conversations with disputes (Phase 12).")
