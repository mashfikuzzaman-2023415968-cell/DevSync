"""Schedule forecasting over a baseline CPM plan (spec §9.10 step 5). PURE.

Given the baseline schedule (planned earliest start/finish per milestone) and each
milestone's current state — done, active with some progress, or not started — this
projects when every milestone and the whole project will actually finish, and by how
many days the project will miss (or beat) its baseline duration. Used by the plan page
(baseline-vs-forecast) and, from Phase 9, the monitoring and risk engine.

Milestones are processed in a topological order (planned earliest start is one), so a
not-started milestone sees its predecessors' already-forecast finishes. No clock: the
caller passes `today` as a project-day index (0 = project start).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DONE = "DONE"
ACTIVE = "ACTIVE"
NOT_STARTED = "NOT_STARTED"

# Task status weights for milestone progress p (spec §9.10).
_TASK_WEIGHTS = {"TODO": 0.0, "IN_PROGRESS": 0.5, "REVIEW": 0.85, "DONE": 1.0}


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
    progress: float = 0.0
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
                by_plan = m.duration_days * (1 - m.progress)
                by_pace = m.elapsed_days * (1 - m.progress) / m.progress
                ef = today + math.ceil(max(by_plan, by_pace))
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
