"""Who the caller is in a project's workspace (spec §1.6, §2.2; DECISIONS D142).

Every workspace service starts here. Participants are the project's client and its ACTIVE
members (COMPLETED members may read, so Phase 11 can show finished projects). Anyone else —
INVITED, DECLINED, EXPIRED, LEFT or REMOVED members, other clients, outsiders — gets 404, as for
the team (D130). Admins may read where the caller allows it and never write (Phase 12 adds the
dispute context). Writes need the project IN_PROGRESS (409 INVALID_STATE otherwise). RLS repeats
the participant rule underneath (migration 0016).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, InvalidStateTransition, NotFoundError
from app.db.context import DbContext
from app.db.session import open_session
from app.models.formation import MemberStatus, Team, TeamMember, TeamStatus
from app.models.identity import User
from app.models.projects import Project, ProjectStatus
from app.services.context import Ctx


class WorkspaceRole(StrEnum):
    CLIENT = "CLIENT"
    LEAD = "LEAD"
    MEMBER = "MEMBER"
    ADMIN = "ADMIN"


@dataclass(frozen=True)
class Workspace:
    project: Project
    team: Team
    role: WorkspaceRole
    me: TeamMember | None  # the caller's member row (members and the lead)

    @property
    def is_lead(self) -> bool:
        return self.role == WorkspaceRole.LEAD

    @property
    def is_member(self) -> bool:
        """An ACTIVE or COMPLETED member, the lead included."""
        return self.role in (WorkspaceRole.LEAD, WorkspaceRole.MEMBER)

    @property
    def is_client(self) -> bool:
        return self.role == WorkspaceRole.CLIENT


async def team_of(db: AsyncSession, project_id: uuid.UUID) -> Team | None:
    """The project's current team (a cancelled one only if nothing newer exists)."""
    return await db.scalar(
        select(Team)
        .where(Team.project_id == project_id)
        .order_by((Team.status == TeamStatus.CANCELLED).asc(), Team.created_at.desc(), Team.id)
        .limit(1)
    )


async def load(
    ctx: Ctx, project_id: uuid.UUID, *, write: bool = False, admin_read: bool = True
) -> Workspace:
    """The caller's place in the workspace, or 404 / 403 / 409 as described above."""
    db = ctx.db
    project = await db.get(Project, project_id)
    team = await team_of(db, project_id) if project is not None else None
    if project is None or team is None:
        raise NotFoundError
    if project.client_id == ctx.uid:
        ws = Workspace(project, team, WorkspaceRole.CLIENT, None)
    elif ctx.principal.is_admin:
        if write or not admin_read:
            raise ForbiddenError("Admins see workspace conversations with disputes (Phase 12).")
        ws = Workspace(project, team, WorkspaceRole.ADMIN, None)
    else:
        allowed = (MemberStatus.ACTIVE,) if write else (MemberStatus.ACTIVE, MemberStatus.COMPLETED)
        me = await db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.developer_id == ctx.uid,
                TeamMember.status.in_(allowed),
            )
        )
        if me is None:
            raise NotFoundError
        lead = me.is_lead and me.status == MemberStatus.ACTIVE
        ws = Workspace(project, team, WorkspaceRole.LEAD if lead else WorkspaceRole.MEMBER, me)
    if write and project.status != ProjectStatus.IN_PROGRESS:
        raise InvalidStateTransition(
            project.status.value,
            [],
            "The workspace opens for changes when the project starts.",
        )
    return ws


async def people(ws: Workspace) -> dict[uuid.UUID, str]:
    """Display names of everyone who is or was in the project (its client and every member row,
    departed ones included, so old tasks and comments still show a name). Read as SYSTEM after
    the caller was admitted by `load`: the users table is own-row-only under RLS."""
    async with open_session(DbContext.system(), job=True) as db:
        devs = select(TeamMember.developer_id).where(TeamMember.team_id == ws.team.id)
        rows = await db.execute(
            select(User.id, User.display_name).where(
                (User.id == ws.project.client_id) | User.id.in_(devs)
            )
        )
        return dict(rows.tuples().all())


def require_lead(ws: Workspace, what: str) -> None:
    """Lead powers exist only inside the lead's own project (§1.6 rule 6)."""
    if not ws.is_lead:
        raise ForbiddenError(f"Only the team lead can {what}.")


def require_member(ws: Workspace, what: str) -> None:
    """Members' work (moves, evidence, check-ins): never the client (§1.6, D142)."""
    if not ws.is_member:
        raise ForbiddenError(f"Only team members can {what}.")
