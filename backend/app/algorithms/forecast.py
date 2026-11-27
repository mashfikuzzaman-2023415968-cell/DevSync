"""Schedule forecasting over a baseline CPM plan (spec §9.10 step 5). PURE.

Given the baseline schedule (planned earliest start/finish per milestone) and each
milestone's current state — done, active with some progress, or not started — this
projects when every milestone and the whole project will actually finish, and by how
many days the project will miss (or beat) its baseline duration. Used by the plan page
(baseline-vs-forecast) and, from Phase 9, the monitoring and risk engine.

Milestones are processed in a topological order (planned earliest start is one), so a
not-started milestone sees its predecessors' already-forecast finishes. No clock: the
caller passes `today` as a project-day index (0 = project start).

Exact arithmetic (DECISIONS D161): progress comes from `numeric(5,1)` estimates and fixed
weights, so it is a rational number. The services pass it as a `Fraction`
(`milestone_progress_exact`), and the remaining time is then computed exactly before `ceil`; in
binary floating point a value such as 4·0.6/0.4 lands a hair above or below an integer and `ceil`
could add a day that doesn't exist. Floats are still accepted (the §9.10 rule is unchanged).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

DONE = "DONE"
ACTIVE = "ACTIVE"
NOT_STARTED = "NOT_STARTED"

# Task status weights for milestone progress p (spec §9.10).
_TASK_WEIGHTS = {"TODO": 0.0, "IN_PROGRESS": 0.5, "REVIEW": 0.85, "DONE": 1.0}
_EXACT_WEIGHTS = {
    "TODO": Fraction(0),
    "IN_PROGRESS": Fraction(1, 2),
    "REVIEW": Fraction(17, 20),
    "DONE": Fraction(1),
}


@dataclass(frozen=True)
class MilestoneForecastInput:
    """One milestone's plan and current state for forecasting.

    `status` is normalized to DONE / ACTIVE / NOT_STARTED by the service.
    `progress` is p ∈ [0, 1]; `elapsed_days` is days since the milestone's actual start;
    `actual_finish` is the day offset a DONE milestone finished on.
    """

    id: str
    duration_days: int
    predecessors: tuple[str, ...]
    status: str
    planned_es: int
    planned_ef: int
    progress: float | Fraction = 0.0
    elapsed_days: int = 0
    actual_finish: int | None = None


@dataclass(frozen=True)
class MilestoneForecast:
    """Forecast finish day offset for one milestone (and its forecast start, if recomputed)."""

    forecast_finish: int
    forecast_start: int | None = None


@dataclass(frozen=True)
class ForecastResult:
    """Per-milestone forecasts plus the project finish and deadline impact."""

    nodes: dict[str, MilestoneForecast]
    project_finish: int
    baseline_duration: int
    deadline_impact: int  # project_finish - baseline_duration (positive = late)


def milestone_progress(tasks: list[tuple[float, str]]) -> float:
    """Progress p of a milestone from its tasks: Σ(estimate × weight) / Σ estimate (§9.10).

    `tasks` is a list of (estimate_hours, task_status). Weights: TODO 0, IN_PROGRESS 0.5,
    REVIEW 0.85, DONE 1. An empty or zero-estimate milestone has progress 0.
    """
    total = sum(estimate for estimate, _ in tasks)
    if total <= 0:
        return 0.0
    done = sum(estimate * _TASK_WEIGHTS.get(status, 0.0) for estimate, status in tasks)
    return done / total


def milestone_progress_exact(tasks: Iterable[tuple[Decimal, str]]) -> Fraction:
    """`milestone_progress` without rounding (D161): estimates are exact decimals (one place),
    weights exact fractions, so p is an exact rational. Unknown statuses weigh 0."""
    pairs = [(Fraction(estimate), status) for estimate, status in tasks]
    total = sum((estimate for estimate, _ in pairs), Fraction(0))
    if total <= 0:
        return Fraction(0)
    done = sum(
        (estimate * _EXACT_WEIGHTS.get(status, Fraction(0)) for estimate, status in pairs),
        Fraction(0),
    )
    return done / total


def remaining_days(duration_days: int, elapsed_days: int, progress: float | Fraction) -> int:
    """Whole days left for an active milestone with progress p ∈ (0, 1]: the slower of the plan
    and the current pace, rounded up (§9.10 step 5). Exact when p is a Fraction (D161)."""
    if isinstance(progress, Fraction):
        by_plan_exact = duration_days * (1 - progress)
        by_pace_exact = elapsed_days * (1 - progress) / progress
        return math.ceil(max(by_plan_exact, by_pace_exact))
    by_plan = duration_days * (1 - progress)
    by_pace = elapsed_days * (1 - progress) / progress
    return math.ceil(max(by_plan, by_pace))


def _order(milestones: list[MilestoneForecastInput]) -> list[str]:
    """A topological order: planned earliest start then finish then id (ES respects deps)."""
    return [m.id for m in sorted(milestones, key=lambda m: (m.planned_es, m.planned_ef, m.id))]


def forecast(
    milestones: list[MilestoneForecastInput],
    today: int,
    baseline_duration: int,
) -> ForecastResult:
    """Project each milestone's finish and the project finish/impact (spec §9.10 step 5)."""
    by_id = {m.id: m for m in milestones}
    finish: dict[str, int] = {}
    nodes: dict[str, MilestoneForecast] = {}

    for mid in _order(milestones):
        m = by_id[mid]
        pred_ef = max((finish[p] for p in m.predecessors), default=0)

        if m.status == DONE:
            # Finished: use the recorded actual finish (fall back to planned if absent).
            ef = m.actual_finish if m.actual_finish is not None else m.planned_ef
            nodes[mid] = MilestoneForecast(forecast_finish=ef)
        elif m.status == ACTIVE:
            if m.progress > 0:
                # Remaining from both the plan and the current pace; take the slower (safer).
                ef = today + remaining_days(m.duration_days, m.elapsed_days, m.progress)
            else:
                # Started but no measurable progress yet.
                ef = max(m.planned_ef, today + m.duration_days)
            nodes[mid] = MilestoneForecast(forecast_finish=ef)
        else:  # NOT_STARTED
            # Starts when predecessors are forecast done; no earlier than today if overdue.
            es = max(pred_ef, today) if m.planned_es <= today else pred_ef
            ef = es + m.duration_days
            nodes[mid] = MilestoneForecast(forecast_finish=ef, forecast_start=es)

        finish[mid] = nodes[mid].forecast_finish

    project_finish = max(finish.values(), default=0)
    return ForecastResult(
        nodes=nodes,
        project_finish=project_finish,
        baseline_duration=baseline_duration,
        deadline_impact=project_finish - baseline_duration,
    )
