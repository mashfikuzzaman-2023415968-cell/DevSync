"""Risk engine (spec §9.11, §18.2; D151, D161; `app/algorithms/risks.py`). Pure.

Every rule fires and resolves at its boundary (one test per rule and per severity step), the
started-milestones-only rule of D151, the milestone state mapping, team health, overall risk,
schedule progress and budget usage, and the §18.2 "Inventory dashboard" on day 12: forecast 25
(+2), exactly one CRITICAL (Dashboard frontend), SLACK_EATEN on the API, DEADLINE_IMPACT MEDIUM,
INACTIVE_MEMBER MEDIUM, health At risk, overall CRITICAL. FR-MON ids are in the names.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest

from app.algorithms import risks as r
from app.algorithms.risks import (
    MemberIn,
    MilestoneIn,
    MoneyIn,
    ProjectIn,
    SubmittedIn,
    TaskIn,
    Thresholds,
    evaluate,
    milestone_progress,
    milestone_state,
    overall_risk,
    team_health,
)

pytestmark = pytest.mark.unit
TH = Thresholds(inactive_days=7, repair_days=10, stalled_days=5)


def ms(  # noqa: PLR0917 - a compact table-style fixture builder
    mid: str,
    name: str,
    status: str,
    dur: int,
    es: int,
    ef: int,
    *,
    preds: tuple[str, ...] = (),
    slack: int = 0,
    critical: bool = True,
    p: Fraction = Fraction(0),
    start: int | None = None,
    finish: int | None = None,
    skills: tuple[str, ...] = (),
    share: int = 1000,
) -> MilestoneIn:
    return MilestoneIn(
        id=mid,
        name=name,
        status=status,
        duration_days=dur,
        share_bp=share,
        predecessors=preds,
        planned_es=es,
        planned_ef=ef,
        slack=slack,
        critical=critical,
        progress=p,
        actual_start_day=start,
        actual_finish_day=finish,
        skill_ids=skills,
    )


def tasks(milestone: str, done: int, todo: int, owner: str | None = None) -> list[TaskIn]:
    out = [
        TaskIn(
            f"{milestone}-d{i}",
            f"{milestone} done {i}",
            milestone,
            "DONE",
            owner,
            Decimal("1.0"),
            None,
            0,
        )
        for i in range(done)
    ]
    out += [
        TaskIn(
            f"{milestone}-t{i}",
            f"{milestone} todo {i}",
            milestone,
            "TODO",
            owner,
            Decimal("1.0"),
            None,
            0,
        )
        for i in range(todo)
    ]
    return out


def member(uid: str, skill: str, inactive: int = 0, hours: int = 20) -> MemberIn:
    return MemberIn(uid, uid.title(), skill, hours, inactive)


def inventory(day: int = 12, inactive: int = 8) -> ProjectIn:
    """§18.2 item 2 on `day` (the history is fixed in project days; only "today" moves)."""
    api_tasks = tasks("API", 7, 3, "nusrat")
    dash_tasks = tasks("DASH", 4, 6, "tanvir")
    milestones = (
        ms("REQ", "Requirements", "APPROVED", 3, 0, 3, finish=3, skills=("ba",), share=1000),
        ms(
            "UI",
            "UI design",
            "APPROVED",
            5,
            3,
            8,
            preds=("REQ",),
            finish=8,
            skills=("design",),
            share=1500,
        ),
        ms(
            "API",
            "Inventory API",
            "ACTIVE",
            7,
            3,
            10,
            preds=("REQ",),
            slack=6,
            critical=False,
            p=milestone_progress(api_tasks),
            start=4,
            skills=("backend",),
            share=2000,
        ),
        ms(
            "DASH",
            "Dashboard frontend",
            "ACTIVE",
            8,
            8,
            16,
            preds=("UI",),
            p=milestone_progress(dash_tasks),
            start=8,
            skills=("react",),
            share=2500,
        ),
        ms(
            "INT",
            "Integration",
            "PLANNED",
            3,
            16,
            19,
            preds=("API", "DASH"),
            skills=("backend", "react"),
            share=1500,
        ),
        ms(
            "TEST",
            "Testing & handover",
            "PLANNED",
            4,
            19,
            23,
            preds=("INT",),
            skills=("qa",),
            share=1500,
        ),
    )
    members = (
        member("arif", "backend"),  # lead
        member("nusrat", "backend"),
        member("tanvir", "react"),
        member("sadia", "qa"),
        member("rafi", "design", inactive=inactive),  # design work is done: no skill risk
    )
    return ProjectIn(
        today=day,
        baseline_duration=23,
        milestones=milestones,
        tasks=tuple(api_tasks + dash_tasks),
        members=members,
        money=MoneyIn(budget_paisa=12_000_000),
        thresholds=TH,
    )


def kinds(p: ProjectIn) -> list[tuple[str, str, str | None]]:
    return sorted((x.type, x.severity, x.entity_id) for x in evaluate(p).risks)


# --------------------------------------------------------------------------- the demo case


def test_FR_MON_4_inventory_dashboard_on_day_12() -> None:  # noqa: N802
    p = inventory()
    assert p.milestones[2].progress == Fraction(7, 10)
    assert p.milestones[3].progress == Fraction(2, 5)
    e = evaluate(p)
    assert (e.finish_day, e.impact_days) == (25, 2)
    assert kinds(p) == [
        ("CRITICAL_PATH_DELAY", "CRITICAL", "DASH"),
        ("DEADLINE_IMPACT", "MEDIUM", None),
        ("INACTIVE_MEMBER", "MEDIUM", "rafi"),
        ("SLACK_EATEN", "MEDIUM", "API"),
    ]
    delay = next(x for x in e.risks if x.type == "CRITICAL_PATH_DELAY")
    assert delay.title == "Dashboard frontend late pushes the deadline by 2 days"
    assert delay.detail == {"planned_finish_day": 16, "forecast_finish_day": 18, "days_late": 2}
    assert (e.health, e.overall) == ("AT_RISK", "CRITICAL")
    assert e.causes == ("API", "DASH")  # API 6 days past plan (slack), DASH 2 (critical)
    look = {o.id: o for o in e.outlook}
    assert {k: look[k].forecast_ef for k in look} == {
        "REQ": 3,
        "UI": 8,
        "API": 16,
        "DASH": 18,
        "INT": 21,
        "TEST": 25,
    }


def test_two_days_later_the_inactive_member_turns_critical() -> None:
    e = evaluate(inventory(day=14, inactive=10))
    inactive = next(x for x in e.risks if x.type == "INACTIVE_MEMBER")
    assert inactive.severity == "CRITICAL"
    assert "FIND_REPLACEMENT" in inactive.actions
    assert e.health == "CRITICAL"  # two CRITICAL risks


# --------------------------------------------------------------------------- rules at boundaries


def _one(
    status: str = "ACTIVE",
    *,
    critical: bool = True,
    slack: int = 0,
    p: Fraction,
    start: int,
    dur: int = 10,
    today: int,
    extra_tasks: tuple[TaskIn, ...] = (),
    members: tuple[MemberIn, ...] = (),
    money: MoneyIn | None = None,
) -> ProjectIn:
    m = ms("M", "Build", status, dur, 0, dur, slack=slack, critical=critical, p=p, start=start)
    return ProjectIn(
        today=today,
        baseline_duration=dur + slack,
        milestones=(m,),
        tasks=extra_tasks,
        members=members,
        money=money or MoneyIn(budget_paisa=1_000_000),
        thresholds=TH,
    )


def test_critical_path_delay_fires_one_day_late_and_resolves_on_time() -> None:
    late = _one(p=Fraction(1, 2), start=0, today=6)  # remaining max(5, 6) → finish 12 vs 10
    assert ("CRITICAL_PATH_DELAY", "CRITICAL", "M") in kinds(late)
    on_time = _one(p=Fraction(1, 2), start=0, today=5)  # remaining 5 → finish 10
    assert not [k for k in kinds(on_time) if k[0] == "CRITICAL_PATH_DELAY"]


def test_slack_eaten_needs_more_than_half_the_slack() -> None:
    half = _one(critical=False, slack=4, p=Fraction(1, 2), start=0, today=6)  # 2 late of 4
    assert not [k for k in kinds(half) if k[0] == "SLACK_EATEN"]
    more = _one(critical=False, slack=4, p=Fraction(1, 2), start=0, today=7)  # 4 late of 4
    assert ("SLACK_EATEN", "MEDIUM", "M") in kinds(more)


def test_a_not_started_milestone_pushed_late_is_not_flagged_again() -> None:
    """D151: the ripple shows once, in DEADLINE_IMPACT, not as a second CRITICAL."""
    p = inventory()
    later = [x for x in evaluate(p).risks if x.entity_id in ("INT", "TEST")]
    assert later == []


@pytest.mark.parametrize(
    ("impact_days", "severity"), [(0, None), (1, "MEDIUM"), (2, "MEDIUM"), (3, "CRITICAL")]
)
def test_deadline_impact_steps_at_ten_percent(impact_days: int, severity: str | None) -> None:
    # D = 20, so 10% is 2 days: 2 is MEDIUM, 3 is CRITICAL.
    m = ms("M", "Build", "APPROVED", 20, 0, 20, finish=20 + impact_days)
    p = ProjectIn(
        today=25,
        baseline_duration=20,
        milestones=(m,),
        tasks=(),
        members=(),
        money=MoneyIn(budget_paisa=1),
        thresholds=TH,
    )
    found = [x for x in evaluate(p).risks if x.type == "DEADLINE_IMPACT"]
    assert [x.severity for x in found] == ([severity] if severity else [])


@pytest.mark.parametrize(("idle", "severity"), [(4, None), (5, "LOW"), (9, "LOW"), (10, "MEDIUM")])
def test_stalled_task_steps(idle: int, severity: str | None) -> None:
    t = TaskIn("T", "Paging", "M", "IN_PROGRESS", None, Decimal("2.0"), None, idle)
    p = _one(p=Fraction(1, 2), start=0, today=1, extra_tasks=(t,))
    found = [x.severity for x in evaluate(p).risks if x.type == "STALLED_TASK"]
    assert found == ([severity] if severity else [])
    review = replace(t, status="REVIEW")
    assert not [x for x in evaluate(replace(p, tasks=(review,))).risks if x.type == "STALLED_TASK"]


@pytest.mark.parametrize(
    ("days", "severity"), [(6, None), (7, "MEDIUM"), (9, "MEDIUM"), (10, "CRITICAL")]
)
def test_inactive_member_steps(days: int, severity: str | None) -> None:
    p = _one(p=Fraction(1, 2), start=0, today=1, members=(member("zahid", "x", inactive=days),))
    found = [x.severity for x in evaluate(p).risks if x.type == "INACTIVE_MEMBER"]
    assert found == ([severity] if severity else [])


def test_capacity_compares_open_hours_with_weekly_hours() -> None:
    def load(hours: str, deadline: int | None) -> list[str]:
        t = TaskIn("T", "Big", "M", "TODO", "zahid", Decimal(hours), deadline, 0)
        p = _one(
            p=Fraction(1, 2),
            start=0,
            today=1,
            extra_tasks=(t,),
            members=(member("zahid", "x", hours=10),),
        )
        return [x.severity for x in evaluate(p).risks if x.type == "CAPACITY"]

    assert load("10.0", 5) == []  # one week (at least): 10 h fits
    assert load("10.1", 5) == ["MEDIUM"]
    assert load("20.0", 15) == []  # two weeks
    assert load("20.1", 15) == ["MEDIUM"]
    # No deadline: the milestone's forecast finish (day 6 here) decides, so one week.
    assert load("10.0", None) == []
    assert load("10.1", None) == ["MEDIUM"]
    done = TaskIn("T", "Big", "M", "DONE", "zahid", Decimal("99.0"), 2, 0)
    p = _one(
        p=Fraction(1, 2),
        start=0,
        today=1,
        extra_tasks=(done,),
        members=(member("zahid", "x", hours=10),),
    )
    assert not [x for x in evaluate(p).risks if x.type == "CAPACITY"]


def _idle(p: ProjectIn, who: str, days: int) -> ProjectIn:
    members = tuple(replace(m, inactive_days=days) if m.user_id == who else m for m in p.members)
    return replace(p, members=members)


def test_skill_dependency_needs_a_single_idle_or_overloaded_holder() -> None:
    base = inventory(inactive=0)
    assert ("SKILL_DEPENDENCY", "MEDIUM", "tanvir") in kinds(_idle(base, "tanvir", 5))
    assert not [k for k in kinds(_idle(base, "tanvir", 4)) if k[0] == "SKILL_DEPENDENCY"]
    # Two backend holders (arif, nusrat): idle Nusrat is no single point of failure.
    assert not [k for k in kinds(_idle(base, "nusrat", 6)) if k[0] == "SKILL_DEPENDENCY"]


def test_budget_and_auto_approval_wait_for_phase_10_inputs() -> None:
    quiet = _one(p=Fraction(1, 2), start=0, today=1)
    assert not [x for x in evaluate(quiet).risks if x.type in ("BUDGET", "AUTO_APPROVAL_SOON")]
    money = MoneyIn(
        budget_paisa=1000,
        released_paisa=500,
        committed_paisa=0,
        wallet_paisa=10,
        next_milestone_paisa=100,
    )
    spent = _one(p=Fraction(1, 4), start=0, today=1, money=money)  # 50% spent vs 25% + 20 points
    found = sorted(
        (x.severity, x.entity_type, x.client_only)
        for x in evaluate(spent).risks
        if x.type == "BUDGET"
    )
    assert found == [("LOW", "WALLET", True), ("MEDIUM", "PROJECT", True)]
    soon = replace(
        quiet, submitted=(SubmittedIn("M", "Build", 47.0), SubmittedIn("N", "Other", 49.0))
    )
    auto = [x for x in evaluate(soon).risks if x.type == "AUTO_APPROVAL_SOON"]
    assert [(x.entity_id, x.client_only) for x in auto] == [("M", True)]


# --------------------------------------------------------------------------- summaries


def test_team_health_thresholds() -> None:
    def risk(severity: str) -> r.RiskOut:
        return r.RiskOut("X", severity, "P", None, "t", "w")

    assert team_health([]) == "HEALTHY"
    assert team_health([risk("MEDIUM"), risk("LOW"), risk("LOW")]) == "HEALTHY"
    assert team_health([risk("MEDIUM"), risk("MEDIUM")]) == "AT_RISK"
    assert team_health([risk("CRITICAL")]) == "AT_RISK"
    assert team_health([risk("CRITICAL"), risk("CRITICAL")]) == "CRITICAL"
    assert overall_risk([]) is None
    assert overall_risk([risk("LOW"), risk("MEDIUM")]) == "MEDIUM"


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("APPROVED", "DONE"),
        ("AUTO_APPROVED", "DONE"),
        ("PAID", "DONE"),
        ("ACTIVE", "ACTIVE"),
        ("SUBMITTED", "ACTIVE"),
        ("CHANGES_REQUESTED", "ACTIVE"),
        ("DISPUTED", "ACTIVE"),
        ("PLANNED", "NOT_STARTED"),
        ("FUNDED", "NOT_STARTED"),
    ],
)
def test_milestone_state_mapping(status: str, state: str) -> None:
    assert milestone_state(status) == state


def test_an_unknown_milestone_state_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown"):
        milestone_state("ARCHIVED")


def test_progress_weights_and_schedule() -> None:
    mixed = [
        TaskIn(str(i), "t", "M", s, None, Decimal("2.0"), None, 0)
        for i, s in enumerate(("TODO", "IN_PROGRESS", "REVIEW", "DONE"))
    ]
    assert milestone_progress(mixed) == Fraction(0 + 1 + Fraction(17, 10) + 2, 8)
    assert milestone_progress([]) == 0
    e = evaluate(inventory())
    # Shares: REQ 1000 + UI 1500 done; API 2000 × 0.7 = 1400; DASH 2500 × 0.4 = 1000 → 4900.
    assert e.progress == Fraction(4900, 10000)
    # Planned done by day 12: REQ (3), UI (8), API (10) → 4500 / 10000.
    assert e.planned_progress == Fraction(4500, 10000)
    assert (e.released_share, e.committed_share) == (0, 0)
