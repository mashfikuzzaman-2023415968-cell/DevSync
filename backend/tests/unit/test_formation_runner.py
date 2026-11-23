"""The pure half of `app/services/formation_runner.py` (spec §9.2–§9.8, D105–D109): rebuilding a
run's problem from its frozen snapshot and parameters, running it, and shaping the stored result.
The database half (`execute_run`, `write_explanations`, `execute_verify`) is driven end to end
through the API in `tests/security/test_formation_api.py`."""

from __future__ import annotations

import copy
import math
from types import SimpleNamespace
from typing import Any

import pytest

from app.algorithms.filtering import Mode
from app.services import formation_runner as runner
from app.services.formation_runner import CONVERGENCE_POINTS

pytestmark = pytest.mark.unit


def _cand(
    n: int, slot: str, *, comp: float, price: int, days: int, newcomer: bool = False
) -> dict[str, Any]:
    return {
        "bid_id": f"b{n}", "developer_id": f"d{n}", "developer_name": f"Dev {n}",
        "slot_id": slot, "slot_label": slot.upper(), "competency": comp, "teamwork": 0.5,
        "performance": 0.6, "days": days, "price_paisa": price, "newcomer": newcomer,
        "skills": [f"skill-{slot}"],
    }  # fmt: skip


def _snapshot() -> dict[str, Any]:
    return {
        "candidates": [
            _cand(1, "fe", comp=0.9, price=40_000, days=20),
            _cand(2, "fe", comp=0.6, price=20_000, days=15, newcomer=True),
            _cand(3, "be", comp=0.8, price=45_000, days=25),
            _cand(4, "be", comp=0.5, price=25_000, days=18, newcomer=True),
        ],
        "slots": {"fe": 1, "be": 1},
        "required_skills": ["skill-be", "skill-fe"],
        "critical_skills": ["skill-be"],
        "deadline_days": 30,
        "budget_after_fee_paisa": 100_000,
        "relaxations": [{"step": 1, "p0": 0.5, "c0": 0.4}],
    }


def _params(**over: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "weights": {"competency": 0.4, "teamwork": 0.2, "time": 0.2, "cost": 0.2},
        "min_newcomers": 0,
        "include_performance": False,
        "mode": "devsync",
        "pso": {"particles": 8, "max_iter": 30, "z1": 1.5, "z2": 1.5, "inertia": 1.0,
                "v_max": 4.0, "bounds": [-1.0, 1.0], "early_stop_iters": 10},
        "exact": {"max_candidates": 18, "max_combinations": 2_000_000},
    }  # fmt: skip
    params.update(over)
    return params


def _run(snapshot: dict[str, Any] | None = None, seed: int = 7, **params: Any) -> Any:
    return SimpleNamespace(candidate_snapshot=snapshot or _snapshot(), params=_params(**params),
                           seed=seed)  # fmt: skip


# ------------------------------------------------------------------------------ problem_from


def test_problem_from_rebuilds_the_frozen_inputs() -> None:
    problem, pso, limits = runner.problem_from(_snapshot(), _params())
    assert problem.size == 4
    assert dict(problem.slots) == {"fe": 1, "be": 1}
    assert problem.deadline_days == 30
    assert problem.budget_after_fee_paisa == 100_000
    assert problem.required_skills == frozenset({"skill-fe", "skill-be"})
    assert problem.mode is Mode.DEVSYNC
    assert problem.min_newcomers == 0
    first = problem.candidates[0]
    assert (first.bid_id, first.slot_id, first.price_paisa, first.days) == ("b1", "fe", 40_000, 20)
    assert first.skills == frozenset({"skill-fe"})
    assert (pso.particles, pso.max_iter, pso.bounds, pso.early_stop_iters) == (
        8,
        30,
        (-1.0, 1.0),
        10,
    )
    assert (limits.max_candidates, limits.max_combinations) == (18, 2_000_000)


def test_k_overrides_the_runs_newcomer_minimum() -> None:
    """The fairness dial re-solves the same run with other k values."""
    problem, _, _ = runner.problem_from(_snapshot(), _params(min_newcomers=0), k=2)
    assert problem.min_newcomers == 2
    same, _, _ = runner.problem_from(_snapshot(), _params(min_newcomers=1))
    assert same.min_newcomers == 1


def test_older_params_without_optional_keys_use_the_defaults() -> None:
    params = _params()
    del params["include_performance"], params["mode"]
    problem, _, _ = runner.problem_from(_snapshot(), params)
    assert problem.include_performance is False
    assert problem.mode is Mode.DEVSYNC


def test_pcs_replication_mode_is_carried_through() -> None:
    problem, _, _ = runner.problem_from(_snapshot(), _params(mode="pcs_replication"))
    assert problem.mode is Mode.PCS_REPLICATION


def test_a_candidate_in_an_unknown_slot_is_refused() -> None:
    snap = _snapshot()
    snap["candidates"][0]["slot_id"] = "ops"
    with pytest.raises(ValueError, match="unknown slot"):
        runner.problem_from(snap, _params())


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("deadline_days", 0, "deadline and budget"),
        ("budget_after_fee_paisa", -1, "deadline and budget"),
        ("slots", {}, "every slot"),
    ],
)
def test_an_impossible_snapshot_is_refused(key: str, value: Any, message: str) -> None:
    snap = _snapshot()
    snap[key] = value
    if key == "slots":
        snap["candidates"] = []
    with pytest.raises(ValueError, match=message):
        runner.problem_from(snap, _params())


def test_a_negative_newcomer_minimum_is_refused() -> None:
    with pytest.raises(ValueError, match="min_newcomers"):
        runner.problem_from(_snapshot(), _params(), k=-1)


@pytest.mark.parametrize("missing", ["weights", "pso", "exact", "min_newcomers"])
def test_params_missing_a_required_part_fail_loudly(missing: str) -> None:
    params = _params()
    del params[missing]
    with pytest.raises(KeyError):
        runner.problem_from(_snapshot(), params)


def test_an_unknown_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="greedy"):
        runner.problem_from(_snapshot(), _params(mode="greedy"))


# ------------------------------------------------------------------------- rounding helpers


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [(None, 3, None), (math.nan, 3, None), (math.inf, 3, None), (-math.inf, 3, None),
     (0.123456, 3, 0.123), (0.98765, 4, 0.9877), (1.0, 3, 1.0)],
)  # fmt: skip
def test_rounding_drops_values_json_cannot_hold(
    value: float | None, places: int, expected: float | None
) -> None:
    assert runner._r(value, places) == expected


def test_rounding_never_returns_negative_zero() -> None:
    result = runner._r(-0.0)
    assert result == 0.0
    assert math.copysign(1.0, result or 0.0) == 1.0


def test_a_short_convergence_series_is_kept_whole() -> None:
    series = tuple(i / 10 for i in range(CONVERGENCE_POINTS))
    assert runner._downsample(series) == [round(v, 4) for v in series]
    assert runner._downsample(()) == []


def test_a_long_convergence_series_keeps_both_ends_and_the_point_budget() -> None:
    series = tuple(float(i) for i in range(1000))
    out = runner._downsample(series)
    assert len(out) == CONVERGENCE_POINTS
    assert out[0] == 0.0
    assert out[-1] == 999.0
    assert out == sorted(out)  # order kept


def test_an_infinite_point_in_the_series_becomes_null() -> None:
    """Before PSO finds a feasible team its best fitness is -inf; JSON has no such number."""
    assert runner._downsample((-math.inf, 0.5)) == [None, 0.5]


# ----------------------------------------------------------------- outcome_for + build_result


def test_a_run_produces_a_feasible_team_one_per_slot_within_budget() -> None:
    run = _run()
    problem, out = runner.outcome_for(run)
    result = runner.build_result(run.candidate_snapshot, problem, out)
    assert result["feasible"] is True
    assert sorted(m["slot_id"] for m in result["team"]) == ["be", "fe"]
    assert result["price_paisa"] == sum(m["price_paisa"] for m in result["team"])
    assert result["price_paisa"] <= result["budget_after_fee_paisa"] == 100_000
    assert result["max_days"] <= result["deadline_days"] == 30
    assert result["candidates"] == 4
    assert result["relaxations"] == [{"step": 1, "p0": 0.5, "c0": 0.4}]
    assert len(result["convergence"]) <= CONVERGENCE_POINTS
    assert sum(t["recommended"] for t in result["top"]) == 1
    assert result["verification"]["available"] is True  # 4 candidates: the exact solver runs
    for member in result["team"]:
        assert set(member["contribution"]) == {"comp", "team", "time", "cost", "perf", "total"}


def test_the_same_seed_reproduces_the_same_result() -> None:
    """D109: an admin's verify re-runs a finished run and must get the same team and fitness."""
    a = runner.build_result(_snapshot(), *runner.outcome_for(_run(seed=11)))
    b = runner.build_result(_snapshot(), *runner.outcome_for(_run(seed=11)))
    assert a == b


def test_the_newcomer_minimum_puts_newcomers_on_the_team() -> None:
    run = _run(min_newcomers=2)
    result = runner.build_result(run.candidate_snapshot, *runner.outcome_for(run))
    assert result["feasible"] is True
    assert result["newcomers"] == 2
    assert all(m["is_newcomer"] for m in result["team"])


def test_a_budget_no_team_fits_is_reported_infeasible_not_an_error() -> None:
    snap = _snapshot()
    snap["budget_after_fee_paisa"] = 10_000  # the cheapest pair costs 45,000
    run = _run(snapshot=snap)
    result = runner.build_result(snap, *runner.outcome_for(run))
    assert result["feasible"] is False
    assert result["team"] == []
    assert result["price_paisa"] == 0


def test_the_snapshot_is_not_changed_by_a_run() -> None:
    snap = _snapshot()
    before = copy.deepcopy(snap)
    runner.build_result(snap, *runner.outcome_for(_run(snapshot=snap)))
    assert snap == before


def test_should_stop_ends_the_run_early_and_says_so() -> None:
    run = _run()
    problem, out = runner.outcome_for(run, should_stop=lambda: True)
    result = runner.build_result(run.candidate_snapshot, problem, out)
    assert result["timed_out"] is True


def test_progress_is_reported_while_the_run_works() -> None:
    seen: list[tuple[str, int, float]] = []
    runner.outcome_for(_run(), on_progress=lambda stage, i, best: seen.append((stage, i, best)))
    assert seen, "no progress events"
    assert all(isinstance(stage, str) and i >= 0 for stage, i, _ in seen)
