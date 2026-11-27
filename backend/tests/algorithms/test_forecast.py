"""Forecast unit tests (spec §9.10 step 5, §17 Phase 4): done, active p>0, active p=0,
not started, and late-predecessor propagation, plus the milestone-progress helper."""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms.forecast import (
    MilestoneForecastInput,
    forecast,
    milestone_progress,
    milestone_progress_exact,
    remaining_days,
)


def mk(
    mid: str,
    duration: int,
    status: str,
    planned_es: int,
    planned_ef: int,
    *,
    predecessors: tuple[str, ...] = (),
    progress: float | Fraction = 0.0,
    elapsed: int = 0,
    actual_finish: int | None = None,
) -> MilestoneForecastInput:
    return MilestoneForecastInput(
        id=mid,
        duration_days=duration,
        predecessors=predecessors,
        status=status,
        planned_es=planned_es,
        planned_ef=planned_ef,
        progress=progress,
        elapsed_days=elapsed,
        actual_finish=actual_finish,
    )


# --------------------------------------------------------------------------- progress


@pytest.mark.parametrize(
    ("tasks", "expected"),
    [
        ([], 0.0),
        ([(10.0, "TODO")], 0.0),
        ([(10.0, "DONE")], 1.0),
        (
            [(2.0, "DONE"), (2.0, "IN_PROGRESS"), (2.0, "REVIEW"), (2.0, "TODO")],
            (1 + 0.5 + 0.85) / 4,
        ),
        ([(0.0, "DONE")], 0.0),  # zero estimate guards against divide-by-zero
    ],
)
def test_milestone_progress(tasks: list[tuple[float, str]], expected: float) -> None:
    assert milestone_progress(tasks) == pytest.approx(expected)


# --------------------------------------------------------------------------- per-milestone rules


def test_done_uses_actual_finish() -> None:
    result = forecast([mk("m", 4, "DONE", 0, 4, actual_finish=5)], today=6, baseline_duration=4)
    assert result.nodes["m"].forecast_finish == 5


def test_done_without_actual_finish_falls_back_to_planned() -> None:
    result = forecast([mk("m", 4, "DONE", 0, 4)], today=6, baseline_duration=4)
    assert result.nodes["m"].forecast_finish == 4


def test_active_with_progress_takes_the_slower_of_plan_and_pace() -> None:
    # dur 10, p 0.25, e 4, today 10: by_plan 7.5, by_pace 12 → remaining 12 → finish 22.
    result = forecast(
        [mk("m", 10, "ACTIVE", 0, 10, progress=0.25, elapsed=4)],
        today=10,
        baseline_duration=10,
    )
    assert result.nodes["m"].forecast_finish == 22


def test_active_with_progress_rounds_remaining_up() -> None:
    # dur 7, p 0.3, e 5, today 10: by_plan 4.9, by_pace 11.666…→ ceil 12 → finish 22.
    result = forecast(
        [mk("m", 7, "ACTIVE", 0, 7, progress=0.3, elapsed=5)],
        today=10,
        baseline_duration=7,
    )
    assert result.nodes["m"].forecast_finish == 22


def test_active_with_zero_progress_is_max_of_planned_and_today_plus_duration() -> None:
    result = forecast(
        [mk("m", 8, "ACTIVE", 8, 16, progress=0.0)],
        today=12,
        baseline_duration=16,
    )
    assert result.nodes["m"].forecast_finish == 20  # max(16, 12 + 8)


def test_not_started_before_its_planned_start_uses_predecessor_finish() -> None:
    plan = [
        mk("a", 4, "DONE", 0, 4, actual_finish=4),
        mk("b", 5, "NOT_STARTED", 4, 9, predecessors=("a",)),
    ]
    result = forecast(plan, today=2, baseline_duration=9)
    assert result.nodes["b"].forecast_start == 4  # planned_es 4 > today 2 → predecessor finish
    assert result.nodes["b"].forecast_finish == 9


def test_not_started_overdue_cannot_start_before_today() -> None:
    result = forecast(
        [mk("m", 3, "NOT_STARTED", 5, 8)],  # planned to start day 5, no predecessors
        today=10,
        baseline_duration=8,
    )
    assert result.nodes["m"].forecast_start == 10  # overdue → no earlier than today
    assert result.nodes["m"].forecast_finish == 13


def test_late_predecessor_pushes_successor_and_the_project() -> None:
    # `a` finished late (day 18 vs planned 16); `b` cannot start until `a` is done.
    plan = [
        mk("a", 16, "DONE", 0, 16, actual_finish=18),
        mk("b", 4, "NOT_STARTED", 16, 20, predecessors=("a",)),
    ]
    result = forecast(plan, today=18, baseline_duration=20)
    assert result.nodes["b"].forecast_start == 18
    assert result.nodes["b"].forecast_finish == 22
    assert result.project_finish == 22
    assert result.deadline_impact == 2  # two days late


def test_on_track_project_has_no_deadline_impact() -> None:
    plan = [
        mk("a", 4, "DONE", 0, 4, actual_finish=4),
        mk("b", 5, "ACTIVE", 4, 9, predecessors=("a",), progress=0.5, elapsed=2),
    ]
    result = forecast(plan, today=6, baseline_duration=9)
    # b: by_plan 2.5, by_pace 2 → remaining 3 (ceil 2.5) → finish 6 + 3 = 9.
    assert result.nodes["b"].forecast_finish == 9
    assert result.project_finish == 9
    assert result.deadline_impact == 0


def test_empty_plan_forecasts_nothing() -> None:
    result = forecast([], today=0, baseline_duration=0)
    assert result.nodes == {}
    assert result.project_finish == 0
    assert result.deadline_impact == 0


# ---------------------------------------------------------------- exact arithmetic (D161)


def test_float_rounding_would_add_a_phantom_day_the_exact_rule_does_not() -> None:
    """p = 0.6 after 3 days: 3·0.4/0.6 is exactly 2, but in float64 it is 2.0000000000000004
    and ceil makes it 3. The exact path keeps the §9.10 answer."""
    assert math.ceil(3 * (1 - 0.6) / 0.6) == 3  # the float trap this guards against
    assert remaining_days(4, 3, Fraction(3, 5)) == 2
    exact = milestone_progress_exact([(Decimal("3.0"), "DONE"), (Decimal("2.0"), "TODO")])
    assert exact == Fraction(3, 5)
    plan = [mk("m", 4, "ACTIVE", 0, 4, progress=exact, elapsed=3)]
    assert forecast(plan, today=3, baseline_duration=4).nodes["m"].forecast_finish == 5


def test_exact_progress_uses_the_spec_weights() -> None:
    tasks = [
        (Decimal("2.0"), "TODO"),
        (Decimal("2.0"), "IN_PROGRESS"),
        (Decimal("2.0"), "REVIEW"),
        (Decimal("4.0"), "DONE"),
        (Decimal("1.5"), "SOMETHING_ELSE"),  # unknown statuses weigh 0
    ]
    expected = (Fraction(1) + Fraction(17, 10) + Fraction(4)) / Fraction(23, 2)
    assert milestone_progress_exact(tasks) == expected
    assert milestone_progress_exact([]) == 0
    assert milestone_progress_exact([(Decimal("0"), "DONE")]) == 0


def test_inventory_dashboard_forecast_is_25_days_plus_2() -> None:
    """§18.2 item 2 on day 12: API p = 0.7 since day 4, Dashboard p = 0.4 since day 8."""
    plan = [
        mk("REQ", 3, "DONE", 0, 3, actual_finish=3),
        mk("UI", 5, "DONE", 3, 8, predecessors=("REQ",), actual_finish=8),
        mk("API", 7, "ACTIVE", 3, 10, predecessors=("REQ",), progress=Fraction(7, 10), elapsed=8),
        mk("DASH", 8, "ACTIVE", 8, 16, predecessors=("UI",), progress=Fraction(2, 5), elapsed=4),
        mk("INT", 3, "NOT_STARTED", 16, 19, predecessors=("API", "DASH")),
        mk("TEST", 4, "NOT_STARTED", 19, 23, predecessors=("INT",)),
    ]
    result = forecast(plan, today=12, baseline_duration=23)
    finishes = {k: v.forecast_finish for k, v in result.nodes.items()}
    assert finishes == {"REQ": 3, "UI": 8, "API": 16, "DASH": 18, "INT": 21, "TEST": 25}
    assert result.project_finish == 25
    assert result.deadline_impact == 2


@pytest.mark.property
@settings(max_examples=300, deadline=None)
@given(
    st.integers(min_value=1, max_value=60),
    st.integers(min_value=0, max_value=60),
    st.integers(min_value=1, max_value=999),
    st.integers(min_value=1, max_value=999),
)
def test_exact_and_float_agree_unless_the_float_error_crosses_an_integer(
    duration: int, elapsed: int, done: int, total_extra: int
) -> None:
    p = Fraction(done, done + total_extra)
    exact = remaining_days(duration, elapsed, p)
    true_value = max(duration * (1 - p), elapsed * (1 - p) / p)
    assert exact == math.ceil(true_value)  # the definition, with no rounding
    approx = remaining_days(duration, elapsed, float(p))
    if true_value.denominator != 1:  # not an integer: float noise can't cross one
        assert approx == exact
    else:
        assert approx in (exact, exact + 1)
