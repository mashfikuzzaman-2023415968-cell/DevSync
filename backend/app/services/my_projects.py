"""A developer's own projects (spec §13.5 #13 "My projects", #9 developer dashboard).

`active` lists the teams the caller is an ACTIVE member of (project pending start or in
progress); `completed` the ones they finished (COMPLETED). Only the caller's own membership
rows are read, as SYSTEM with an explicit `developer_id = caller` filter (the slot label lives
on rows other roles write). For a project in progress, progress, the next deadline, health and
the overall risk come from the member-shaped dashboard (cached, D151), which never carries money.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, or_, select

from app.core.errors import DomainError, ErrorCode
from app.db.context import DbContext
from app.db.session import open_session
from app.models.formation import MemberStatus, Team, TeamMember
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.schemas.common import Page
from app.schemas.monitoring import DashboardForMember, MyProject
from app.services import monitoring
from app.services.context import Ctx

State = Literal["active", "completed"]
_STATUS = {"active": MemberStatus.ACTIVE, "completed": MemberStatus.COMPLETED}


def _cursor(at: datetime, member_id: uuid.UUID) -> str:
    raw = json.dumps([at.isoformat(), str(member_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, mid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(at), uuid.UUID(str(mid))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DomainError(
            "That page link is invalid.", code=ErrorCode.BAD_REQUEST, fields={"cursor": "Invalid"}
        ) from exc


async def my_projects(ctx: Ctx, *, state: State, cursor: str | None, limit: int) -> Page[MyProject]:
    """Newest membership first."""
    async with open_session(DbContext.system(), job=True) as db:
        q = (
            select(TeamMember, Project, ProjectSlot.label)
            .join(Team, Team.id == TeamMember.team_id)
            .join(Project, Project.id == Team.project_id)
            .join(ProjectSlot, ProjectSlot.id == TeamMember.slot_id)
            .where(TeamMember.developer_id == ctx.uid, TeamMember.status == _STATUS[state])
        )
        if cursor is not None:
            at, mid = _decode(cursor)
            q = q.where(
                or_(
                    TeamMember.created_at < at,
                    and_(TeamMember.created_at == at, TeamMember.id < mid),
                )
            )
        order = (TeamMember.created_at.desc(), TeamMember.id.desc())
        rows = list((await db.execute(q.order_by(*order).limit(limit + 1))).tuples().all())
        more = len(rows) > limit
        rows = rows[:limit]
        found = [
            (m.id, m.created_at, m.is_lead, p.id, p.title, p.status, label) for m, p, label in rows
        ]
    items: list[MyProject] = []
    for _mid, _at, is_lead, pid, title, status, label in found:
        item = MyProject(
            project_id=pid,
            title=title,
            status=status.value,
            role=label,
            is_lead=is_lead,
            progress_pct=100 if state == "completed" else None,
            next_deadline=None,
            next_milestone=None,
            overall_risk=None,
            health=None,
        )
        if status == ProjectStatus.IN_PROGRESS:
            board = await monitoring.dashboard(ctx, pid)
            if isinstance(board, DashboardForMember):
                nxt = board.next_milestone
                item.progress_pct = board.progress_pct
                item.health = board.health
                item.overall_risk = board.overall_risk
                if nxt is not None:
                    item.next_milestone = nxt.name
                    item.next_deadline = nxt.forecast_finish_date or nxt.planned_finish_date
        items.append(item)
    last = found[-1] if found else None
    return Page[MyProject](
        items=items, next_cursor=_cursor(last[1], last[0]) if more and last else None
    )
