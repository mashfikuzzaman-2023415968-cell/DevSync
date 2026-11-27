"""Weekly check-ins (spec §7.5, §10.2 Check-ins, §11 `checkin.reminders`, §12; D145, D149).

- An ACTIVE member posts one check-in per Dhaka week (409 `CHECKIN_EXISTS` for a second one, also
  when two arrive at once: the UNIQUE index decides). It is immutable once posted: it's reputation
  evidence; corrections go in a comment. The client reads the feed and may reply (comments).
- `on_time` and `week_start` are the server's (`app/algorithms/weeks.py`), never the client's.
- Posting records `checkin.posted`; non-empty blockers also record `blocker.reported` and tell the
  lead (§12 "blocker reported").
- `send_reminders` (the Monday 10:00 job) reminds every expected member who hasn't posted this week
  and records `checkin.missed` once for every finished expected week with neither a check-in nor a
  missed event, so a run skipped while the scheduler was down is caught up next time.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import date, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.algorithms import weeks
from app.core.errors import DomainError, ErrorCode
from app.core.logging import get_logger
from app.db.context import DbContext
from app.db.session import open_session
from app.models.formation import MemberStatus, Team, TeamMember
from app.models.projects import Project, ProjectStatus
from app.models.workspace import ActivityEvent, Checkin, Comment, CommentTarget
from app.schemas.checkins import CheckinCreate, CheckinFeed, CheckinOut, ThisWeek
from app.schemas.tasks import PersonRef
from app.services import activity, monitoring
from app.services import workspace as wsp
from app.services.context import Ctx
from app.services.notifications import notify_once, notify_users

log = get_logger(__name__)


def _cursor(c: Checkin) -> str:
    raw = json.dumps([c.week_start.isoformat(), c.created_at.isoformat(), str(c.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[date, datetime, uuid.UUID]:
    try:
        week, at, cid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return date.fromisoformat(week), datetime.fromisoformat(at), uuid.UUID(str(cid))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DomainError(
            "That page link is invalid.", code=ErrorCode.BAD_REQUEST, fields={"cursor": "Invalid"}
        ) from exc


async def post_checkin(ctx: Ctx, project_id: uuid.UUID, body: CheckinCreate) -> CheckinOut:
    ws = await wsp.load(ctx, project_id, write=True)
    wsp.require_member(ws, "post check-ins")
    me = ws.me
    if me is None:  # require_member guarantees a member row; this narrows the type
        raise DomainError(code=ErrorCode.ROLE_NOT_ALLOWED)
    db = ctx.db
    monday = weeks.week_of(ctx.now)
    checkin = Checkin(
        project_id=ws.project.id,
        team_member_id=me.id,
        week_start=monday,
        done=body.done,
        next=body.next,
        blockers=body.blockers,
        confidence=body.confidence,
        on_time=weeks.is_on_time(ctx.now, monday),
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    db.add(checkin)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DomainError(code=ErrorCode.CHECKIN_EXISTS) from exc

    async def emit(event_type: str, data: dict[str, object]) -> None:
        await activity.record(
            db,
            project_id=ws.project.id,
            type=event_type,
            entity_type="CHECKIN",
            entity_id=checkin.id,
            subject_id=ctx.uid,
            data=data,
            at=ctx.now,
        )

    await emit(
        "checkin.posted",
        {
            "checkin_id": checkin.id,
            "week_start": monday,
            "on_time": checkin.on_time,
            "has_blockers": checkin.blockers is not None,
        },
    )
    if checkin.blockers is not None:
        await emit("blocker.reported", {"checkin_id": checkin.id})
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    names = await wsp.people(ws)
    if checkin.blockers is not None and not ws.is_lead:
        lead = await _lead_of(ws)
        if lead is not None:
            await notify_users(
                [lead],
                "BLOCKER_REPORTED",
                title=f"{names.get(ctx.uid, 'A member')} reported a blocker",
                body=f"In {ws.project.title}. Read their check-in and help them unblock.",
                link=f"/w/{ws.project.id}/check-ins?checkin={checkin.id}",
                once=False,
            )
    return _out(checkin, ctx.uid, names, 0)


async def _lead_of(ws: wsp.Workspace) -> uuid.UUID | None:
    async with open_session(DbContext.system(), job=True) as db:
        return await db.scalar(
            select(TeamMember.developer_id).where(
                TeamMember.team_id == ws.team.id,
                TeamMember.is_lead.is_(True),
                TeamMember.status == MemberStatus.ACTIVE,
            )
        )


def _out(c: Checkin, user_id: uuid.UUID, names: dict[uuid.UUID, str], replies: int) -> CheckinOut:
    return CheckinOut(
        id=c.id,
        member_id=c.team_member_id,
        member=PersonRef(id=user_id, name=names.get(user_id, "Former member")),
        week_start=c.week_start,
        done=c.done,
        next=c.next,
        blockers=c.blockers,
        confidence=c.confidence,
        on_time=c.on_time,
        created_at=c.created_at,
        reply_count=replies,
    )


async def feed(
    ctx: Ctx,
    project_id: uuid.UUID,
    *,
    member_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> CheckinFeed:
    """The project's check-ins, newest week first (then by posting time), and this week's state:
    who still owes one. Read by participants and admins."""
    ws = await wsp.load(ctx, project_id)
    db = ctx.db
    q = (
        select(Checkin, TeamMember.developer_id)
        .join(TeamMember, TeamMember.id == Checkin.team_member_id)
        .where(Checkin.project_id == ws.project.id)
    )
    if member_id is not None:
        q = q.where(Checkin.team_member_id == member_id)
    if cursor is not None:
        week, at, cid = _decode(cursor)
        q = q.where(
            or_(
                Checkin.week_start < week,
                and_(Checkin.week_start == week, Checkin.created_at > at),
                and_(Checkin.week_start == week, Checkin.created_at == at, Checkin.id > cid),
            )
        )
    rows = list(
        await db.execute(
            q.order_by(Checkin.week_start.desc(), Checkin.created_at, Checkin.id).limit(limit + 1)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    ids = [c.id for c, _ in rows]
    replies: dict[uuid.UUID, int] = {}
    if ids:
        counted = await db.execute(
            select(Comment.target_id, func.count())
            .where(
                Comment.target_type == CommentTarget.CHECKIN,
                Comment.target_id.in_(ids),
                Comment.deleted_at.is_(None),
            )
            .group_by(Comment.target_id)
        )
        replies = {tid: int(n) for tid, n in counted}
    names = await wsp.people(ws)
    return CheckinFeed(
        items=[_out(c, uid, names, replies.get(c.id, 0)) for c, uid in rows],
        next_cursor=_cursor(rows[-1][0]) if more and rows else None,
        this_week=await _this_week(ctx, ws, names),
    )


async def _this_week(ctx: Ctx, ws: wsp.Workspace, names: dict[uuid.UUID, str]) -> ThisWeek:
    monday = weeks.week_of(ctx.now)
    db = ctx.db
    members = list(
        await db.scalars(
            select(TeamMember)
            .where(TeamMember.team_id == ws.team.id, TeamMember.status == MemberStatus.ACTIVE)
            .order_by(TeamMember.id)
        )
    )
    posted = set(
        await db.scalars(
            select(Checkin.team_member_id).where(
                Checkin.project_id == ws.project.id, Checkin.week_start == monday
            )
        )
    )
    expected = [
        m
        for m in members
        if m.joined_at is not None and weeks.first_expected_week(m.joined_at) <= monday
    ]
    missing = sorted(
        (m for m in expected if m.id not in posted),
        key=lambda m: (names.get(m.developer_id, ""), m.developer_id),
    )
    return ThisWeek(
        week_start=monday,
        due_at=weeks.due_at(monday),
        posted=ws.me is not None and ws.me.id in posted,
        missing=[PersonRef(id=m.developer_id, name=names.get(m.developer_id, "")) for m in missing],
    )


# --------------------------------------------------------------------------- the weekly job


async def send_reminders(now: datetime) -> dict[str, int]:
    """Monday 10:00 Asia/Dhaka (§11): remind members who haven't posted this week; record each
    finished expected week without a check-in as `checkin.missed`, once (D145). Idempotent per
    member-week; safe to re-run."""
    monday = weeks.week_of(now)
    reminded = missed = 0
    async with open_session(DbContext.system(), job=True) as db:
        rows = list(
            await db.execute(
                select(Project, TeamMember)
                .join(Team, Team.project_id == Project.id)
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(
                    Project.status == ProjectStatus.IN_PROGRESS,
                    TeamMember.status == MemberStatus.ACTIVE,
                    TeamMember.joined_at.is_not(None),
                )
                .order_by(Project.id, TeamMember.id)
            )
        )
        to_remind: list[tuple[Project, TeamMember]] = []
        for project, member in rows:
            joined = member.joined_at
            if joined is None:
                continue
            posted = set(
                await db.scalars(
                    select(Checkin.week_start).where(Checkin.team_member_id == member.id)
                )
            )
            stored: list[str] = list(
                await db.scalars(
                    select(ActivityEvent.data["week_start"].astext).where(
                        ActivityEvent.project_id == project.id,
                        ActivityEvent.type == "checkin.missed",
                        ActivityEvent.subject_id == member.developer_id,
                    )
                )
            )
            recorded = {date.fromisoformat(w) for w in stored}
            for week in weeks.finished_weeks(joined, now, now):
                if week not in posted and week not in recorded:
                    activity.record_system(
                        db,
                        project_id=project.id,
                        type="checkin.missed",
                        entity_type="TEAM_MEMBER",
                        entity_id=member.id,
                        actor_id=None,
                        subject_id=member.developer_id,
                        data={"week_start": week},
                        at=now,
                    )
                    missed += 1
            if weeks.first_expected_week(joined) <= monday and monday not in posted:
                to_remind.append((project, member))
        await db.commit()
        for project, member in to_remind:
            since = datetime.combine(monday, datetime.min.time(), tzinfo=weeks.DHAKA)
            if await notify_once(
                db,
                member.developer_id,
                "CHECKIN_REMINDER",
                title="Time for your weekly check-in",
                body=f"Tell {project.title}'s team what you did and what's next, by Tuesday night.",
                link=f"/w/{project.id}/check-ins",
                since=since,
            ):
                reminded += 1
        await db.commit()
    log.info("checkin_reminders_sent", reminded=reminded, missed=missed)
    return {"reminded": reminded, "missed": missed}
