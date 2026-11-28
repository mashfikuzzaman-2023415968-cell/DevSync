"""Monitoring (spec §9.10–9.11, §10.2 Monitoring, §11 `monitoring.evaluate`, §12; D150–D152,
D165).

- `evaluate_project(project_id, now)` loads one IN_PROGRESS project as SYSTEM, runs the pure engine
  (`app/algorithms/risks.py`) and writes the result: risks upserted by (type, entity) — a severity
  change updates the open row, a rule that stops firing resolves it — and today's forecast
  snapshot (each milestone's planned and forecast dates, the finish, the impact and which
  milestones caused the delay; Phase 11's post-mortem reads the causes). A risk that opens as, or
  is raised to, CRITICAL tells the client and the lead once. A per-project advisory lock keeps two
  evaluations from interleaving; running it twice changes nothing (idempotent).
- Triggers (D165): every 15 minutes for all IN_PROGRESS projects, and 30 s after task, check-in or
  comment changes (a Redis "dirty" set the flush job drains without losing the last event).
- Reads: the dashboard (cached 30 s per project and shape, D151), risks, activity and the
  Evidence tab's summary — role-shaped: members never see budget figures or the client-only risks.
  Reads never write: without a stored evaluation the dashboard computes one in memory.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import risks as engine
from app.algorithms import weeks
from app.algorithms.cpm import CpmError, MilestoneInput, compute_cpm
from app.core import cache
from app.core.errors import DomainError, ErrorCode
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.locks import advisory_xact_lock
from app.db.session import open_session
from app.models.bidding import AvailabilityReservation, Bid
from app.models.formation import MemberStatus, Team, TeamMember
from app.models.identity import User
from app.models.projects import (
    Milestone,
    MilestoneDependency,
    MilestoneSkill,
    Project,
    ProjectSlot,
    ProjectStatus,
)
from app.models.workspace import (
    ActivityEvent,
    Checkin,
    ForecastSnapshot,
    Risk,
    RiskSeverity,
    RiskStatus,
    RiskType,
    Task,
    TaskStatus,
)
from app.schemas.common import Page
from app.schemas.monitoring import (
    ActivityItem,
    Budget,
    DashboardForClient,
    DashboardForMember,
    EvidenceSummary,
    ForecastSummary,
    MemberEvidence,
    NextMilestone,
    ProjectRisk,
    RiskList,
    Schedule,
    TaskCounts,
)
from app.schemas.tasks import PersonRef
from app.services import team as team_svc
from app.services import workspace as wsp
from app.services.context import Ctx
from app.services.notifications import EmailSpec, notify_users

log = get_logger(__name__)
CLIENT_ONLY = frozenset({RiskType.BUDGET, RiskType.AUTO_APPROVAL_SOON})
DASHBOARD_TTL = 30
DIRTY_KEY = "mon:dirty"
DEBOUNCE_SECONDS = 30
_LOCK_NS = uuid.UUID("0b8f1c42-7d3e-4a9b-8e21-5c6d7f8a9b0c")


def project_day(start: date, now: datetime) -> int:
    """Calendar days since the start date in Asia/Dhaka (day 0 is the start, D151)."""
    return (weeks.dhaka_date(now) - start).days


def _day_date(start: date | None, day: int | None) -> date | None:
    return None if start is None or day is None else start + timedelta(days=day)


def _pct(value: Fraction) -> int:
    return max(0, min(100, int(value * 100)))


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class Loaded:
    project: Project
    team: Team
    data: engine.ProjectIn
    milestones: dict[str, Milestone]
    names: dict[str, str]  # user id → display name


async def load_input(db: AsyncSession, project: Project, team: Team, now: datetime) -> Loaded:
    """Everything the engine needs, read in a handful of queries (no N+1, §15.1)."""
    settings = await active_settings(db)
    start = project.start_date or weeks.dhaka_date(now)
    today = project_day(start, now)
    milestones = list(
        await db.scalars(
            select(Milestone)
            .where(Milestone.project_id == project.id)
            .order_by(Milestone.position, Milestone.id)
        )
    )
    deps = list(
        await db.scalars(
            select(MilestoneDependency).where(MilestoneDependency.project_id == project.id)
        )
    )
    preds: dict[uuid.UUID, list[str]] = {m.id: [] for m in milestones}
    for d in deps:
        preds.setdefault(d.successor_id, []).append(str(d.predecessor_id))
    cpm = compute_cpm(
        [
            MilestoneInput(
                id=str(m.id),
                duration_days=m.duration_days,
                predecessors=tuple(sorted(preds.get(m.id, ()))),
                name=m.name,
            )
            for m in milestones
        ]
    )
    skills: dict[uuid.UUID, list[str]] = {}
    for ms_id, skill in await db.execute(
        select(MilestoneSkill.milestone_id, MilestoneSkill.skill_id).where(
            MilestoneSkill.milestone_id.in_([m.id for m in milestones] or [uuid.uuid4()])
        )
    ):
        skills.setdefault(ms_id, []).append(str(skill))
    tasks = list(
        await db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id))
    )
    task_in = tuple(
        engine.TaskIn(
            id=str(t.id),
            title=t.title,
            milestone_id=str(t.milestone_id),
            status=t.status.value,
            assignee_id=str(t.assignee_id) if t.assignee_id else None,
            estimate_hours=t.estimate_hours,
            deadline_day=(t.deadline - start).days if t.deadline else None,
            idle_days=max(0, (now - t.last_activity_at).days),
        )
        for t in tasks
    )
    by_milestone: dict[str, list[engine.TaskIn]] = {}
    for t in task_in:
        by_milestone.setdefault(t.milestone_id, []).append(t)
    milestone_in = tuple(
        engine.MilestoneIn(
            id=str(m.id),
            name=m.name,
            status=m.status.value,
            duration_days=m.duration_days,
            share_bp=m.share_bp,
            predecessors=tuple(sorted(preds.get(m.id, ()))),
            planned_es=cpm.nodes[str(m.id)].es,
            planned_ef=cpm.nodes[str(m.id)].ef,
            slack=cpm.nodes[str(m.id)].slack,
            critical=cpm.nodes[str(m.id)].critical,
            progress=engine.milestone_progress(by_milestone.get(str(m.id), [])),
            actual_start_day=(m.actual_start - start).days if m.actual_start else None,
            actual_finish_day=(m.actual_finish - start).days if m.actual_finish else None,
            skill_ids=tuple(sorted(skills.get(m.id, []))),
        )
        for m in milestones
    )
    members = list(
        await db.execute(
            select(
                TeamMember, ProjectSlot.skill_id, User.display_name, Bid.hours_per_week_committed
            )
            .join(ProjectSlot, ProjectSlot.id == TeamMember.slot_id)
            .join(User, User.id == TeamMember.developer_id)
            .join(Bid, Bid.id == TeamMember.bid_id)
            .where(TeamMember.team_id == team.id, TeamMember.status == MemberStatus.ACTIVE)
            .order_by(TeamMember.id)
        )
    )
    reserved = dict(
        (
            await db.execute(
                select(
                    AvailabilityReservation.developer_id, AvailabilityReservation.hours_per_week
                ).where(AvailabilityReservation.project_id == project.id)
            )
        )
        .tuples()
        .all()
    )
    member_in = []
    names: dict[str, str] = {}
    for member, skill_id, name, bid_hours in members:
        names[str(member.developer_id)] = name
        member_in.append(
            engine.MemberIn(
                user_id=str(member.developer_id),
                name=name,
                slot_skill_id=str(skill_id),
                hours_per_week=int(reserved.get(member.developer_id, bid_hours)),
                inactive_days=await team_svc.member_inactive_days(db, member, now) or 0,
            )
        )
    data = engine.ProjectIn(
        today=today,
        baseline_duration=cpm.duration,
        milestones=milestone_in,
        tasks=task_in,
        members=tuple(member_in),
        money=engine.MoneyIn(budget_paisa=project.budget_paisa),
        thresholds=engine.Thresholds(
            inactive_days=settings.alerts.inactive_days,
            repair_days=settings.alerts.repair_days,
            stalled_days=settings.alerts.stalled_days,
        ),
    )
    return Loaded(project, team, data, {str(m.id): m for m in milestones}, names)


def snapshot_json(loaded: Loaded, e: engine.Evaluation, now: datetime) -> dict[str, Any]:
    """Today's snapshot: per-milestone plan and forecast, the finish, the impact and the causes."""
    start = loaded.project.start_date
    look = {o.id: o for o in e.outlook}
    crit = {m.id: m.critical for m in loaded.data.milestones}
    return {
        "evaluated_at": now.isoformat(),
        "today": loaded.data.today,
        "baseline_days": loaded.data.baseline_duration,
        "finish_day": e.finish_day,
        "finish_date": str(_day_date(start, e.finish_day)) if start else None,
        "impact_days": e.impact_days,
        "health": e.health,
        "overall": e.overall,
        "progress_pct": _pct(e.progress),
        "planned_pct": _pct(e.planned_progress),
        "milestones": [
            {
                "id": o.id,
                "name": loaded.milestones[o.id].name,
                "state": o.state,
                "status": loaded.milestones[o.id].status.value,
                "planned_es": o.planned_es,
                "planned_ef": o.planned_ef,
                "forecast_es": o.forecast_es,
                "forecast_ef": o.forecast_ef,
                "progress_pct": _pct(o.progress),
                "days_late": o.days_late,
                "critical": crit[o.id],
            }
            for o in e.outlook
        ],
        "causes": [
            {
                "milestone_id": mid,
                "name": loaded.milestones[mid].name,
                "days_late": look[mid].days_late,
                "critical": crit[mid],
            }
            for mid in e.causes
        ],
    }


# --------------------------------------------------------------------------- evaluation


async def evaluate_project(project_id: uuid.UUID, now: datetime) -> dict[str, Any]:
    """Evaluate and store one project's risks and snapshot (idempotent; SYSTEM)."""
    critical_opened: list[str] = []
    async with open_session(DbContext.system(), job=True) as db:
        await advisory_xact_lock(db, uuid.uuid5(_LOCK_NS, str(project_id)))
        project = await db.get(Project, project_id)
        if project is None or project.status != ProjectStatus.IN_PROGRESS:
            return {"skipped": True}
        team = await wsp.team_of(db, project.id)
        if team is None:
            return {"skipped": True}
        try:
            loaded = await load_input(db, project, team, now)
        except CpmError:
            log.warning("monitoring_plan_invalid", project_id=str(project_id))
            return {"skipped": True}
        e = engine.evaluate(loaded.data)
        critical_opened = await _upsert_risks(db, project.id, e.risks, now)
        day = weeks.dhaka_date(now)
        snap = await db.scalar(
            select(ForecastSnapshot).where(
                ForecastSnapshot.project_id == project.id, ForecastSnapshot.day == day
            )
        )
        payload = snapshot_json(loaded, e, now)
        if snap is None:
            db.add(
                ForecastSnapshot(
                    project_id=project.id,
                    day=day,
                    forecast=payload,
                    impact_days=e.impact_days,
                    evaluated_at=now,
                )
            )
        else:
            snap.forecast, snap.impact_days, snap.evaluated_at = payload, e.impact_days, now
        lead = await db.scalar(
            select(TeamMember.developer_id).where(
                TeamMember.team_id == team.id,
                TeamMember.is_lead.is_(True),
                TeamMember.status == MemberStatus.ACTIVE,
            )
        )
        await db.commit()
        client_id, title = project.client_id, project.title
    if critical_opened:
        recipients = [client_id, *([lead] if lead else [])]
        for risk_title in critical_opened:
            await notify_users(
                recipients,
                "RISK_CRITICAL",
                title=f"Critical risk: {risk_title}",
                body=f"In {title}. Open the Risks tab for what it means and what to do.",
                link=f"/w/{project_id}/risks",
                once=False,
                email=EmailSpec("risk_critical", {"project": title, "risk": risk_title}),
            )
    await cache.invalidate(get_redis(), f"project:{project_id}")
    return {
        "risks": len(e.risks),
        "critical_opened": len(critical_opened),
        "impact_days": e.impact_days,
    }


async def _upsert_risks(
    db: AsyncSession, project_id: uuid.UUID, found: tuple[engine.RiskOut, ...], now: datetime
) -> list[str]:
    """Open new risks, update the open ones that still fire, resolve the rest (by type and
    entity, §9.11). Returns the titles of risks that just became CRITICAL (opened or raised)."""
    open_rows = {
        (r.type.value, r.entity_type, str(r.entity_id) if r.entity_id else None): r
        for r in await db.scalars(
            select(Risk).where(Risk.project_id == project_id, Risk.status == RiskStatus.OPEN)
        )
    }
    critical: list[str] = []
    for out in found:
        detail = {"why": out.why, "actions": list(out.actions), **out.detail}
        row = open_rows.pop(out.key, None)
        raised = out.severity == engine.CRITICAL and (
            row is None or row.severity != RiskSeverity.CRITICAL
        )
        if raised:
            critical.append(out.title)
        if row is None:
            db.add(
                Risk(
                    project_id=project_id,
                    type=RiskType(out.type),
                    severity=RiskSeverity(out.severity),
                    entity_type=out.entity_type,
                    entity_id=_entity_uuid(out.entity_id),
                    title=out.title,
                    detail=detail,
                    opened_at=now,
                    updated_at=now,
                )
            )
            continue
        row.severity = RiskSeverity(out.severity)
        row.title, row.detail, row.updated_at = out.title, detail, now
    for row in open_rows.values():  # what no longer fires is resolved
        row.status = RiskStatus.RESOLVED
        row.resolved_at = now
        row.updated_at = now
    return critical


def _entity_uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def in_progress_projects() -> list[uuid.UUID]:
    async with open_session(DbContext.system(), job=True) as db:
        return list(
            await db.scalars(
                select(Project.id)
                .where(Project.status == ProjectStatus.IN_PROGRESS)
                .order_by(Project.id)
            )
        )


# --------------------------------------------------------------------------- triggers (D165)

# Remove the member only if its score is still the one we read: an event that arrived during
# the evaluation re-added it with a newer score, and the next flush evaluates again.
_REMOVE_IF_SAME = """
local s = redis.call('ZSCORE', KEYS[1], ARGV[1])
if s and tonumber(s) == tonumber(ARGV[2]) then return redis.call('ZREM', KEYS[1], ARGV[1]) end
return 0
"""


async def mark_dirty(project_id: uuid.UUID, now: datetime) -> None:
    """After a change commits: evaluate this project in ~30 s, and drop its cached dashboard."""
    redis = get_redis()
    try:
        await redis.zadd(DIRTY_KEY, {str(project_id): now.timestamp()}, nx=True)
    except RedisError as exc:  # the 15-minute sweep still catches it
        log.warning("monitoring_mark_failed", error=type(exc).__name__)
    await cache.invalidate(redis, f"project:{project_id}")


async def due_projects(now: datetime) -> list[tuple[str, float]]:
    """Projects whose first unevaluated change is at least 30 s old, with that score."""
    rows: list[Any] = list(
        await get_redis().zrangebyscore(
            DIRTY_KEY, "-inf", now.timestamp() - DEBOUNCE_SECONDS, withscores=True
        )
    )
    out: list[tuple[str, float]] = []
    for member, score in rows:  # (member, score) pairs
        out.append((member.decode() if isinstance(member, bytes) else str(member), float(score)))
    return out


async def clear_if_unchanged(project_id: str, score: float) -> bool:
    redis = get_redis()
    removed = await redis.eval(_REMOVE_IF_SAME, 1, DIRTY_KEY, project_id, repr(score))
    return bool(removed)


# --------------------------------------------------------------------------- reads


async def _latest(db: AsyncSession, project_id: uuid.UUID) -> ForecastSnapshot | None:
    return await db.scalar(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.project_id == project_id)
        .order_by(ForecastSnapshot.day.desc())
        .limit(1)
    )


def _risk_out(r: Risk) -> ProjectRisk:
    detail = r.detail or {}
    return ProjectRisk(
        id=r.id,
        type=r.type.value,
        severity=r.severity.value,
        entity_type=r.entity_type,
        entity_id=str(r.entity_id) if r.entity_id else None,
        title=r.title,
        why=str(detail.get("why", "")),
        actions=[str(a) for a in detail.get("actions", [])],
        opened_at=r.opened_at,
    )


async def _open_risks(db: AsyncSession, project_id: uuid.UUID, *, members: bool) -> list[Risk]:
    q = select(Risk).where(Risk.project_id == project_id, Risk.status == RiskStatus.OPEN)
    if members:
        q = q.where(Risk.type.not_in(CLIENT_ONLY))
    rows = list(await db.scalars(q))
    rank = {RiskSeverity.CRITICAL: 0, RiskSeverity.MEDIUM: 1, RiskSeverity.LOW: 2}
    return sorted(rows, key=lambda r: (rank[r.severity], r.opened_at, r.id))


async def risks(ctx: Ctx, project_id: uuid.UUID, *, status: str = "OPEN") -> RiskList:
    """Open (or resolved) risks, worst first; members never get the client-only ones."""
    ws = await wsp.load(ctx, project_id)
    members_view = ws.is_member
    async with open_session(DbContext.system(), job=True) as db:
        if status == "OPEN":
            rows = await _open_risks(db, project_id, members=members_view)
        else:
            q = select(Risk).where(
                Risk.project_id == project_id, Risk.status == RiskStatus.RESOLVED
            )
            if members_view:
                q = q.where(Risk.type.not_in(CLIENT_ONLY))
            rows = list(await db.scalars(q.order_by(Risk.resolved_at.desc(), Risk.id).limit(100)))
        snap = await _latest(db, project_id)
        # Built inside the session: the rows can't be read once it closes.
        return RiskList(
            items=[_risk_out(r) for r in rows], evaluated_at=snap.evaluated_at if snap else None
        )


async def dashboard(ctx: Ctx, project_id: uuid.UUID) -> DashboardForClient | DashboardForMember:
    """The Overview's numbers, role-shaped and cached 30 s per project and shape (D151)."""
    ws = await wsp.load(ctx, project_id)
    if ws.project.status != ProjectStatus.IN_PROGRESS:
        raise DomainError(
            "The dashboard opens when the project starts.", code=ErrorCode.INVALID_STATE
        )
    shape = "member" if ws.is_member else "client"

    async def load() -> str:
        model = await _build_dashboard(ws, ctx.now, client=shape == "client")
        return model.model_dump_json()

    text = await cache.cached(
        get_redis(),
        name="dashboard",
        scope=f"project:{project_id}",
        parts=(shape,),
        ttl_seconds=DASHBOARD_TTL,
        loader=load,
    )
    if shape == "client":
        return DashboardForClient.model_validate_json(text)
    return DashboardForMember.model_validate_json(text)


async def _build_dashboard(
    ws: wsp.Workspace, now: datetime, *, client: bool
) -> DashboardForClient | DashboardForMember:
    project = ws.project
    async with open_session(DbContext.system(), job=True) as db:
        snap = await _latest(db, project.id)
        if snap is not None:
            data = snap.forecast
            evaluated_at: datetime | None = snap.evaluated_at
        else:  # never evaluated yet: compute in memory (a read never writes)
            loaded = await load_input(db, project, ws.team, now)
            data = snapshot_json(loaded, engine.evaluate(loaded.data), now)
            evaluated_at = None
        open_rows = await _open_risks(db, project.id, members=not client)
        # Read the rows while the session is open (they can't be read once it closes).
        top_risks = [_risk_out(r) for r in open_rows[:3]]
        as_engine = _as_engine(open_rows)
        counts = dict(
            (
                await db.execute(
                    select(Task.status, func.count())
                    .where(Task.project_id == project.id)
                    .group_by(Task.status)
                )
            )
            .tuples()
            .all()
        )
    start = project.start_date
    upcoming = sorted(
        (m for m in data["milestones"] if m["state"] != "DONE"),
        key=lambda m: (m["forecast_ef"], m["planned_ef"], m["id"]),
    )
    nxt = upcoming[0] if upcoming else None
    base: dict[str, Any] = {
        "progress_pct": data["progress_pct"],
        "schedule": Schedule(actual_pct=data["progress_pct"], planned_pct=data["planned_pct"]),
        "forecast": ForecastSummary(
            finish_day=data["finish_day"],
            finish_date=_day_date(start, data["finish_day"]),
            baseline_days=data["baseline_days"],
            impact_days=data["impact_days"],
        ),
        "health": engine.team_health(as_engine),
        "overall_risk": engine.overall_risk(as_engine),
        "top_risks": top_risks,
        "next_milestone": NextMilestone(
            id=uuid.UUID(nxt["id"]),
            name=nxt["name"],
            status=nxt["status"],
            progress_pct=nxt["progress_pct"],
            planned_finish_date=_day_date(start, nxt["planned_ef"]),
            forecast_finish_date=_day_date(start, nxt["forecast_ef"]),
        )
        if nxt
        else None,
        "tasks": TaskCounts(
            todo=counts.get(TaskStatus.TODO, 0),
            in_progress=counts.get(TaskStatus.IN_PROGRESS, 0),
            review=counts.get(TaskStatus.REVIEW, 0),
            done=counts.get(TaskStatus.DONE, 0),
        ),
        "evaluated_at": evaluated_at,
    }
    if not client:
        return DashboardForMember(**base)
    # Phase 10 brings escrow: released and committed are honestly zero until then (D151).
    return DashboardForClient(
        **base,
        budget=Budget(
            budget_paisa=project.budget_paisa,
            released_paisa=0,
            committed_paisa=0,
            remaining_paisa=project.budget_paisa,
        ),
    )


def _as_engine(rows: list[Risk]) -> list[engine.RiskOut]:
    return [
        engine.RiskOut(r.type.value, r.severity.value, r.entity_type, None, r.title, "")
        for r in rows
    ]


async def plan_forecast(
    project: Project, now: datetime
) -> tuple[dict[str, Any] | None, datetime | None]:
    """The forecast the plan shows (D152): the latest stored evaluation, or — before the first
    one — the same computation in memory (a read never writes). Returns (data, evaluated_at)."""
    async with open_session(DbContext.system(), job=True) as db:
        snap = await _latest(db, project.id)
        if snap is not None:
            return dict(snap.forecast), snap.evaluated_at
        team = await wsp.team_of(db, project.id)
        if team is None:
            return None, None
        try:
            loaded = await load_input(db, project, team, now)
        except CpmError:
            return None, None
        return snapshot_json(loaded, engine.evaluate(loaded.data), now), None


# --------------------------------------------------------------------------- activity


SUMMARY = {
    "checkin.posted": "{actor} posted a check-in",
    "checkin.missed": "{subject} missed a weekly check-in",
    "comment.posted": "{actor} commented",
    "comment.replied": "{actor} replied",
    "task.moved": "{actor} moved a task",
    "task.done": "{actor} finished a task",
    "task.reopened": "{actor} reopened a task",
    "task.evidence_added": "{actor} added evidence to a task",
    "work.started": "{subject} started work",
    "blocker.reported": "{actor} reported a blocker",
    "blocker.answered": "{actor} helped with a blocker",
    "member.left": "{subject} left the team",
    "member.replaced": "{subject} joined as a replacement",
}


def _cursor(at: datetime, eid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([at.isoformat(), str(eid)]).encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, eid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(at), uuid.UUID(str(eid))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DomainError(
            "That page link is invalid.", code=ErrorCode.BAD_REQUEST, fields={"cursor": "Invalid"}
        ) from exc


async def activity(
    ctx: Ctx, project_id: uuid.UUID, *, cursor: str | None = None, limit: int = 20
) -> Page[ActivityItem]:
    """The project's evidence feed, newest first, as plain sentences (no free text)."""
    ws = await wsp.load(ctx, project_id)
    q = select(ActivityEvent).where(ActivityEvent.project_id == project_id)
    if cursor is not None:
        at, eid = _decode(cursor)
        q = q.where(
            or_(ActivityEvent.at < at, and_(ActivityEvent.at == at, ActivityEvent.id < eid))
        )
    rows = list(
        await ctx.db.scalars(
            q.order_by(ActivityEvent.at.desc(), ActivityEvent.id.desc()).limit(limit + 1)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    names = await wsp.people(ws)

    def person(uid: uuid.UUID | None) -> PersonRef | None:
        return PersonRef(id=uid, name=names.get(uid, "Former member")) if uid else None

    items = []
    for ev in rows:
        actor, subject = person(ev.actor_id), person(ev.subject_id)
        template = SUMMARY.get(ev.type, "Project activity")
        items.append(
            ActivityItem(
                id=ev.id,
                type=ev.type,
                actor=actor,
                subject=subject,
                summary=template.format(
                    actor=actor.name if actor else "DevSync",
                    subject=who.name if (who := subject or actor) else "A member",
                ),
                entity_type=ev.entity_type,
                entity_id=ev.entity_id,
                at=ev.at,
            )
        )
    return Page[ActivityItem](
        items=items, next_cursor=_cursor(rows[-1].at, rows[-1].id) if more and rows else None
    )


async def evidence_summary(ctx: Ctx, project_id: uuid.UUID) -> EvidenceSummary:
    """Per-member activity for the Evidence tab (§13.5 #38): counts from the evidence events.
    Members in a stable order: lead first, then by name (D140)."""
    ws = await wsp.load(ctx, project_id)
    async with open_session(DbContext.system(), job=True) as db:
        members = list(
            await db.execute(
                # Plain columns, not entities: they're read after the session closes.
                select(
                    TeamMember.id,
                    TeamMember.developer_id,
                    TeamMember.is_lead,
                    TeamMember.status,
                    User.display_name,
                    ProjectSlot.label,
                )
                .join(User, User.id == TeamMember.developer_id)
                .join(ProjectSlot, ProjectSlot.id == TeamMember.slot_id)
                .where(
                    TeamMember.team_id == ws.team.id,
                    TeamMember.status.in_(
                        (
                            MemberStatus.ACTIVE,
                            MemberStatus.COMPLETED,
                            MemberStatus.LEFT,
                            MemberStatus.REMOVED,
                        )
                    ),
                )
            )
        )
        events = list(
            await db.execute(
                select(
                    ActivityEvent.type,
                    ActivityEvent.actor_id,
                    ActivityEvent.subject_id,
                    ActivityEvent.data,
                    ActivityEvent.at,
                ).where(ActivityEvent.project_id == project_id)
            )
        )
        on_time = dict(
            (
                await db.execute(
                    select(Checkin.team_member_id, func.count())
                    .where(Checkin.project_id == project_id, Checkin.on_time.is_(True))
                    .group_by(Checkin.team_member_id)
                )
            )
            .tuples()
            .all()
        )
    out = []
    for member_id, uid, _is_lead, status, name, label in sorted(
        members, key=lambda row: (not row[2], row[4].casefold(), row[0])
    ):
        mine = [e for e in events if uid in (e.actor_id, e.subject_id)]
        done = [e for e in mine if e.type == "task.done" and e.subject_id == uid]
        reopened = [e for e in mine if e.type == "task.reopened" and e.subject_id == uid]
        hours = sum((Decimal(str(e.data.get("estimate_hours", "0"))) for e in done), Decimal(0))
        hours -= sum(
            (Decimal(str(e.data.get("estimate_hours", "0"))) for e in reopened), Decimal(0)
        )
        posted = [e for e in mine if e.type == "checkin.posted" and e.actor_id == uid]
        missed = [e for e in mine if e.type == "checkin.missed" and e.subject_id == uid]
        out.append(
            MemberEvidence(
                member=PersonRef(id=uid, name=name),
                slot_label=label or "Team member",
                status=status.value,
                checkins_on_time=int(on_time.get(member_id, 0)),
                checkins_expected=len(posted) + len(missed),
                tasks_done=max(0, len(done) - len(reopened)),
                hours_done=str(max(hours, Decimal(0))),
                comments=sum(1 for e in mine if e.type == "comment.posted" and e.actor_id == uid),
                replies=sum(1 for e in mine if e.type == "comment.replied" and e.actor_id == uid),
                blockers_answered=sum(
                    1 for e in mine if e.type == "blocker.answered" and e.actor_id == uid
                ),
                last_active_at=max(
                    (
                        e.at
                        for e in mine
                        if e.actor_id == uid and e.type in team_svc.ACTIVITY_SIGNALS
                    ),
                    default=None,
                ),
            )
        )
    return EvidenceSummary(members=out)
