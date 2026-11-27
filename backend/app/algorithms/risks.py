"""Risk engine and monitoring metrics (spec §9.11, §9.10; DECISIONS D151, D161). PURE.

One function per §9.11 rule, plus team health, overall risk, schedule progress, budget usage and
the forecast's delay causes. Everything comes in as plain data (the service loads it); every
threshold comes from settings; nothing reads a clock or a database.

Decisions applied here (D151):
- milestone states → forecast states: APPROVED / AUTO_APPROVED / PAID (and REFUNDED) are DONE;
  ACTIVE / SUBMITTED / CHANGES_REQUESTED / DISPUTED are ACTIVE; PLANNED / FUNDED NOT_STARTED;
- CRITICAL_PATH_DELAY and SLACK_EATEN look at started (ACTIVE) milestones only — the cause; the
  ripple onto later milestones shows once, in DEADLINE_IMPACT;
- STALLED_TASK is LOW from `stalled_days` and MEDIUM from twice that; INACTIVE_MEMBER is MEDIUM
  from `inactive_days` and CRITICAL from `repair_days` (with a repair suggestion);
- CAPACITY compares a member's open task hours with their committed hours a week × weeks until
  those tasks' deadlines (at least one; a task without a deadline uses its milestone's forecast);
- SKILL_DEPENDENCY's "skill held by exactly one active member" is the member's slot skill, and
  "inactive ≥ 5 days or overloaded" is ≥ `stalled_days` idle or an open CAPACITY risk;
- BUDGET and AUTO_APPROVAL_SOON read money and submissions that arrive in Phase 10 (zeros now).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any

from app.algorithms.forecast import (
    ACTIVE,
    DONE,
    NOT_STARTED,
    MilestoneForecastInput,
    forecast,
)

CRITICAL = "CRITICAL"
MEDIUM = "MEDIUM"
LOW = "LOW"
SEVERITY_RANK = {LOW: 1, MEDIUM: 2, CRITICAL: 3}

HEALTHY = "HEALTHY"
AT_RISK = "AT_RISK"
CRITICAL_HEALTH = "CRITICAL"

_STATE = {
    "APPROVED": DONE,
    "AUTO_APPROVED": DONE,
    "PAID": DONE,
    "REFUNDED": DONE,
    "ACTIVE": ACTIVE,
    "SUBMITTED": ACTIVE,
    "CHANGES_REQUESTED": ACTIVE,
    "DISPUTED": ACTIVE,
    "PLANNED": NOT_STARTED,
    "FUNDED": NOT_STARTED,
}
_WEIGHT = {
    "TODO": Fraction(0),
    "IN_PROGRESS": Fraction(1, 2),
    "REVIEW": Fraction(17, 20),
    "DONE": Fraction(1),
}
AUTO_APPROVAL_WINDOW_HOURS = 48  # §9.11 "within 2 days"
SLACK_EATEN_SHARE = Fraction(1, 2)  # §9.11 "used > 50% of its slack"
BUDGET_MARGIN = Fraction(1, 5)  # §9.11 "progress + 20 points"
DEADLINE_CRITICAL_SHARE = Fraction(1, 10)  # §9.11 "impact > 10% of D"
HEALTH_CRITICAL_AT = 2  # §9.11 team health: Critical from 2 CRITICAL risks
HEALTH_MEDIUMS_AT = 2  # At risk from 2 MEDIUM risks (or 1 CRITICAL)


def milestone_state(status: str) -> str:
    """The forecast state of a milestone status (D151); unknown statuses fail loudly."""
    try:
        return _STATE[status]
    except KeyError as exc:
        raise ValueError(f"unknown milestone status {status!r}") from exc


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class MilestoneIn:
    id: str
    name: str
    status: str
    duration_days: int
    share_bp: int
    predecessors: tuple[str, ...]
    planned_es: int
    planned_ef: int
    slack: int
    critical: bool
    progress: Fraction
    actual_start_day: int | None = None
    actual_finish_day: int | None = None
    skill_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskIn:
    id: str
    title: str
    milestone_id: str
    status: str
    assignee_id: str | None
    estimate_hours: Decimal
    deadline_day: int | None
    idle_days: int  # whole days since the task's last activity


@dataclass(frozen=True)
class MemberIn:
    user_id: str
    name: str
    slot_skill_id: str
    hours_per_week: int
    inactive_days: int


@dataclass(frozen=True)
class MoneyIn:
    """Phase 10 fills these; until then they are zeros and BUDGET can't fire."""

    budget_paisa: int
    released_paisa: int = 0
    committed_paisa: int = 0  # funded, not released
    wallet_paisa: int | None = None
    next_milestone_paisa: int | None = None


@dataclass(frozen=True)
class SubmittedIn:
    milestone_id: str
    name: str
    hours_to_auto_approval: float


@dataclass(frozen=True)
class Thresholds:
    inactive_days: int
    repair_days: int
    stalled_days: int


@dataclass(frozen=True)
class ProjectIn:
    today: int  # project day (calendar days since start, Asia/Dhaka)
    baseline_duration: int
    milestones: tuple[MilestoneIn, ...]
    tasks: tuple[TaskIn, ...]
    members: tuple[MemberIn, ...]
    money: MoneyIn
    thresholds: Thresholds
    submitted: tuple[SubmittedIn, ...] = ()


# --------------------------------------------------------------------------- outputs


@dataclass(frozen=True)
class RiskOut:
    type: str
    severity: str
    entity_type: str
    entity_id: str | None
    title: str
    why: str
    actions: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)
    client_only: bool = False

    @property
    def key(self) -> tuple[str, str, str | None]:
        return (self.type, self.entity_type, self.entity_id)


@dataclass(frozen=True)
class MilestoneOutlook:
    id: str
    state: str
    planned_es: int
    planned_ef: int
    forecast_es: int
    forecast_ef: int
    progress: Fraction
    days_late: int


@dataclass(frozen=True)
class Evaluation:
    outlook: tuple[MilestoneOutlook, ...]
    finish_day: int
    impact_days: int
    risks: tuple[RiskOut, ...]
    health: str
    overall: str | None
    progress: Fraction  # Σ share × progress / Σ share
    planned_progress: Fraction  # Σ share of milestones planned done by today / Σ share
    released_share: Fraction
    committed_share: Fraction
    causes: tuple[str, ...]  # started milestones whose forecast finish is past plan, worst first


# --------------------------------------------------------------------------- helpers


def milestone_progress(tasks: Iterable[TaskIn]) -> Fraction:
    """§9.10: Σ(estimate × weight) / Σ estimate, exactly; no tasks → 0."""
    items = list(tasks)
    total = sum((Fraction(t.estimate_hours) for t in items), Fraction(0))
    if total == 0:
        return Fraction(0)
    done = sum(
        (Fraction(t.estimate_hours) * _WEIGHT.get(t.status, Fraction(0)) for t in items),
        Fraction(0),
    )
    return done / total


def _forecast(p: ProjectIn) -> dict[str, MilestoneOutlook]:
    inputs = []
    for m in p.milestones:
        state = milestone_state(m.status)
        elapsed = max(0, p.today - m.actual_start_day) if m.actual_start_day is not None else 0
        inputs.append(
            MilestoneForecastInput(
                id=m.id,
                duration_days=m.duration_days,
                predecessors=m.predecessors,
                status=state,
                planned_es=m.planned_es,
                planned_ef=m.planned_ef,
                progress=m.progress,
                elapsed_days=elapsed,
                actual_finish=m.actual_finish_day,
            )
        )
    result = forecast(inputs, p.today, p.baseline_duration)
    out: dict[str, MilestoneOutlook] = {}
    for m in p.milestones:
        node = result.nodes[m.id]
        state = milestone_state(m.status)
        start = node.forecast_start
        if start is None:
            start = m.actual_start_day if m.actual_start_day is not None else m.planned_es
        out[m.id] = MilestoneOutlook(
            id=m.id,
            state=state,
            planned_es=m.planned_es,
            planned_ef=m.planned_ef,
            forecast_es=start,
            forecast_ef=node.forecast_finish,
            progress=Fraction(1) if state == DONE else m.progress,
            days_late=node.forecast_finish - m.planned_ef,
        )
    return out


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


# --------------------------------------------------------------------------- the rules


def critical_path_delay(p: ProjectIn, look: dict[str, MilestoneOutlook]) -> list[RiskOut]:
    """A started critical milestone forecast to finish after its planned finish (CRITICAL)."""
    out = []
    for m in p.milestones:
        o = look[m.id]
        if m.critical and o.state == ACTIVE and o.days_late > 0:
            out.append(
                RiskOut(
                    type="CRITICAL_PATH_DELAY",
                    severity=CRITICAL,
                    entity_type="MILESTONE",
                    entity_id=m.id,
                    title=f"{m.name} late pushes the deadline by {_days(o.days_late)}",
                    why=(
                        f"{m.name} is on the critical path and is forecast to finish on day "
                        f"{o.forecast_ef} instead of day {o.planned_ef}, at its current pace."
                    ),
                    actions=("REPLAN", "MESSAGE_TEAM"),
                    detail={
                        "planned_finish_day": o.planned_ef,
                        "forecast_finish_day": o.forecast_ef,
                        "days_late": o.days_late,
                    },
                )
            )
    return out


def slack_eaten(p: ProjectIn, look: dict[str, MilestoneOutlook]) -> list[RiskOut]:
    """A started non-critical milestone that used more than half of its slack (MEDIUM)."""
    out = []
    for m in p.milestones:
        o = look[m.id]
        if m.critical or o.state != ACTIVE or m.slack <= 0 or o.days_late <= 0:
            continue
        used = Fraction(o.days_late, m.slack)
        if used > SLACK_EATEN_SHARE:
            pct = min(100, math.floor(used * 100))
            out.append(
                RiskOut(
                    type="SLACK_EATEN",
                    severity=MEDIUM,
                    entity_type="MILESTONE",
                    entity_id=m.id,
                    title=f"{m.name} has used {pct}% of its slack",
                    why=(
                        f"{m.name} had {_days(m.slack)} of slack and is forecast "
                        f"{_days(o.days_late)} late; more delay will push the deadline."
                    ),
                    actions=("REPLAN",),
                    detail={"slack_days": m.slack, "days_late": o.days_late, "used_pct": pct},
                )
            )
    return out


def deadline_impact(p: ProjectIn, finish: int, impact: int) -> list[RiskOut]:
    """The project is forecast to finish ≥ 1 day late (CRITICAL above 10% of D, else MEDIUM)."""
    if impact < 1:
        return []
    severe = Fraction(impact) > DEADLINE_CRITICAL_SHARE * p.baseline_duration
    return [
        RiskOut(
            type="DEADLINE_IMPACT",
            severity=CRITICAL if severe else MEDIUM,
            entity_type="PROJECT",
            entity_id=None,
            title=f"The project is forecast to finish {_days(impact)} late",
            why=(
                f"At the current pace the work ends on day {finish} of a {p.baseline_duration}-"
                "day plan."
            ),
            actions=("REPLAN",),
            detail={
                "forecast_finish_day": finish,
                "planned_days": p.baseline_duration,
                "impact_days": impact,
            },
        )
    ]


def stalled_tasks(p: ProjectIn) -> list[RiskOut]:
    """An IN_PROGRESS task with no activity for `stalled_days` (LOW) or twice that (MEDIUM)."""
    limit = p.thresholds.stalled_days
    out = []
    for t in p.tasks:
        if t.status != "IN_PROGRESS" or t.idle_days < limit:
            continue
        out.append(
            RiskOut(
                type="STALLED_TASK",
                severity=MEDIUM if t.idle_days >= 2 * limit else LOW,
                entity_type="TASK",
                entity_id=t.id,
                title=f"“{t.title}” hasn't moved for {_days(t.idle_days)}",
                why=(
                    "It is in progress with no moves, evidence or comments for "
                    f"{_days(t.idle_days)}."
                ),
                actions=("MESSAGE_MEMBER",),
                detail={"idle_days": t.idle_days},
            )
        )
    return out


def inactive_members(p: ProjectIn) -> list[RiskOut]:
    """No check-in and no task activity for `inactive_days` (MEDIUM) or `repair_days`
    (CRITICAL, with the repair suggestion — a suggestion only, §9.9)."""
    th = p.thresholds
    out = []
    for m in p.members:
        if m.inactive_days < th.inactive_days:
            continue
        critical = m.inactive_days >= th.repair_days
        out.append(
            RiskOut(
                type="INACTIVE_MEMBER",
                severity=CRITICAL if critical else MEDIUM,
                entity_type="MEMBER",
                entity_id=m.user_id,
                title=f"{m.name} has been inactive for {_days(m.inactive_days)}",
                why=(
                    f"No check-in, task move, comment or post from {m.name} in "
                    f"{_days(m.inactive_days)}."
                    + (" You can ask for their removal and a replacement." if critical else "")
                ),
                actions=("MESSAGE_MEMBER", "FIND_REPLACEMENT") if critical else ("MESSAGE_MEMBER",),
                detail={"inactive_days": m.inactive_days},
            )
        )
    return out


def capacity(p: ProjectIn, look: dict[str, MilestoneOutlook]) -> list[RiskOut]:
    """A member's open task hours exceed their weekly hours × weeks until those deadlines."""
    out = []
    for m in p.members:
        mine = [t for t in p.tasks if t.assignee_id == m.user_id and t.status != "DONE"]
        if not mine or m.hours_per_week <= 0:
            continue
        hours = sum((t.estimate_hours for t in mine), Decimal(0))
        last = max(
            t.deadline_day if t.deadline_day is not None else look[t.milestone_id].forecast_ef
            for t in mine
        )
        weeks = max(1, math.ceil(max(0, last - p.today) / 7))
        available = m.hours_per_week * weeks
        if hours > available:
            out.append(
                RiskOut(
                    type="CAPACITY",
                    severity=MEDIUM,
                    entity_type="MEMBER",
                    entity_id=m.user_id,
                    title=f"{m.name} has more work than time",
                    why=(
                        f"{hours.normalize():f} open task hours against {m.hours_per_week} hours a "
                        f"week for {weeks} {'week' if weeks == 1 else 'weeks'}."
                    ),
                    actions=("REASSIGN",),
                    detail={"open_hours": str(hours), "available_hours": available, "weeks": weeks},
                )
            )
    return out


def skill_dependency(
    p: ProjectIn, look: dict[str, MilestoneOutlook], overloaded: set[str]
) -> list[RiskOut]:
    """A not-done critical milestone needs a skill only one active member holds, and that member
    is idle for `stalled_days` or overloaded (MEDIUM)."""
    holders: dict[str, list[MemberIn]] = {}
    for m in p.members:
        holders.setdefault(m.slot_skill_id, []).append(m)
    flagged: dict[str, set[str]] = {}
    for ms in p.milestones:
        if not ms.critical or look[ms.id].state == DONE:
            continue
        for skill in ms.skill_ids:
            only = holders.get(skill, [])
            if len(only) != 1:
                continue
            member = only[0]
            idle = member.inactive_days >= p.thresholds.stalled_days
            if idle or member.user_id in overloaded:
                flagged.setdefault(member.user_id, set()).add(ms.name)
    out = []
    for member in p.members:
        names = flagged.get(member.user_id)
        if not names:
            continue
        listed = ", ".join(sorted(names))
        out.append(
            RiskOut(
                type="SKILL_DEPENDENCY",
                severity=MEDIUM,
                entity_type="MEMBER",
                entity_id=member.user_id,
                title=f"Only {member.name} can do the work on {listed}",
                why=(
                    f"{listed} is on the critical path and needs a skill only {member.name} has "
                    "on this team, and they are inactive or overloaded."
                ),
                actions=("MESSAGE_MEMBER", "REASSIGN"),
                detail={"milestones": sorted(names)},
            )
        )
    return out


def budget(p: ProjectIn, progress: Fraction) -> list[RiskOut]:
    """Spending ahead of progress (MEDIUM), or a wallet short of the next milestone (LOW).
    Client and admin only (it reads the client's wallet, D151)."""
    money = p.money
    out = []
    if money.budget_paisa > 0:
        spent = Fraction(money.released_paisa + money.committed_paisa, money.budget_paisa)
        if spent > progress + BUDGET_MARGIN:
            out.append(
                RiskOut(
                    type="BUDGET",
                    severity=MEDIUM,
                    entity_type="PROJECT",
                    entity_id=None,
                    title="Spending is ahead of progress",
                    why="More of the budget is released or committed than the work done so far.",
                    actions=("REVIEW_BUDGET",),
                    client_only=True,
                )
            )
    if (
        money.wallet_paisa is not None
        and money.next_milestone_paisa is not None
        and money.wallet_paisa < money.next_milestone_paisa
    ):
        out.append(
            RiskOut(
                type="BUDGET",
                severity=LOW,
                entity_type="WALLET",
                entity_id=None,
                title="Your wallet won't cover the next milestone",
                why="Add funds before the next milestone needs funding.",
                actions=("ADD_FUNDS",),
                client_only=True,
            )
        )
    return out


def auto_approval_soon(p: ProjectIn) -> list[RiskOut]:
    """A submitted milestone auto-approves within 2 days (LOW, client only)."""
    return [
        RiskOut(
            type="AUTO_APPROVAL_SOON",
            severity=LOW,
            entity_type="MILESTONE",
            entity_id=s.milestone_id,
            title=f"{s.name} approves itself soon",
            why="Review it before the automatic approval.",
            actions=("REVIEW_SUBMISSION",),
            client_only=True,
        )
        for s in p.submitted
        if 0 <= s.hours_to_auto_approval <= AUTO_APPROVAL_WINDOW_HOURS
    ]


# --------------------------------------------------------------------------- summaries


def team_health(risks: Iterable[RiskOut]) -> str:
    """Healthy (no CRITICAL, ≤ 1 MEDIUM), At risk (≥ 2 MEDIUM or 1 CRITICAL), Critical (≥ 2
    CRITICAL) — §9.11."""
    items = list(risks)
    critical = sum(1 for r in items if r.severity == CRITICAL)
    medium = sum(1 for r in items if r.severity == MEDIUM)
    if critical >= HEALTH_CRITICAL_AT:
        return CRITICAL_HEALTH
    if critical >= 1 or medium >= HEALTH_MEDIUMS_AT:
        return AT_RISK
    return HEALTHY


def overall_risk(risks: Iterable[RiskOut]) -> str | None:
    """The highest open severity, or None when there is no risk."""
    best = max((SEVERITY_RANK[r.severity] for r in risks), default=0)
    return next((s for s, rank in SEVERITY_RANK.items() if rank == best), None)


def schedule_progress(p: ProjectIn, look: dict[str, MilestoneOutlook]) -> tuple[Fraction, Fraction]:
    """(Σ share × progress, Σ share of milestones planned to be done by today) / Σ share."""
    total = sum(m.share_bp for m in p.milestones)
    if total == 0:
        return Fraction(0), Fraction(0)
    actual = sum((m.share_bp * look[m.id].progress for m in p.milestones), Fraction(0)) / total
    planned = Fraction(sum(m.share_bp for m in p.milestones if m.planned_ef <= p.today), total)
    return actual, planned


def evaluate(p: ProjectIn) -> Evaluation:
    """Run every rule and the summaries over one project."""
    look = _forecast(p)
    finish = max((o.forecast_ef for o in look.values()), default=0)
    impact = finish - p.baseline_duration
    progress, planned = schedule_progress(p, look)
    cap = capacity(p, look)
    overloaded = {r.entity_id for r in cap if r.entity_id is not None}
    risks = [
        *critical_path_delay(p, look),
        *slack_eaten(p, look),
        *deadline_impact(p, finish, impact),
        *skill_dependency(p, look, overloaded),
        *cap,
        *budget(p, progress),
        *stalled_tasks(p),
        *inactive_members(p),
        *auto_approval_soon(p),
    ]
    risks.sort(key=lambda r: (-SEVERITY_RANK[r.severity], r.type, r.entity_type, r.entity_id or ""))
    budget_total = p.money.budget_paisa
    causes = sorted(
        (o for o in look.values() if o.state == ACTIVE and o.days_late > 0),
        key=lambda o: (-o.days_late, o.id),
    )
    return Evaluation(
        outlook=tuple(sorted(look.values(), key=lambda o: (o.planned_es, o.planned_ef, o.id))),
        finish_day=finish,
        impact_days=impact,
        risks=tuple(risks),
        health=team_health(risks),
        overall=overall_risk(risks),
        progress=progress,
        planned_progress=planned,
        released_share=Fraction(p.money.released_paisa, budget_total)
        if budget_total
        else Fraction(0),
        committed_share=(
            Fraction(p.money.committed_paisa, budget_total) if budget_total else Fraction(0)
        ),
        causes=tuple(o.id for o in causes),
    )
