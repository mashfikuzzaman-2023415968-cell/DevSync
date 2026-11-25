"""`formation_runner.repair_outcome` (D128, D138): ranking a repair from its frozen snapshot, with
no database — remaining members locked, the impact per candidate, the reasons when nobody fits,
and the same inputs giving the same result."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.formation_runner import repair_outcome
from app.services.repair import queue

pytestmark = pytest.mark.unit

PARAMS: dict[str, Any] = {
    "weights": {"competency": 0.35, "teamwork": 0.25, "time": 0.2, "cost": 0.2},
    "min_newcomers": 0,
    "mode": "devsync",
    "pso": {"particles": 10, "max_iter": 20, "z1": 1.5, "z2": 1.5, "inertia": 1.0, "v_max": 4.0,
            "bounds": [-1.0, 1.0], "early_stop_iters": 10, "timeout_seconds": 10},
    "exact": {"max_candidates": 18, "max_combinations": 2_000_000},
}  # fmt: skip


def cand(bid: str, slot: str, days: int, price: int, c: float = 0.7) -> dict[str, Any]:
    return {"bid_id": bid, "developer_id": f"d-{bid}", "developer_name": bid.title(),
            "slot_id": slot, "slot_label": slot, "competency": c, "teamwork": 0.6,
            "performance": 0.6, "days": days, "price_paisa": price, "hours_per_week": 20,
            "newcomer": False, "skills": [f"k-{slot}"]}  # fmt: skip


def snapshot(
    budget: int = 1_000_000, pool: tuple[dict[str, Any], ...] | None = None
) -> dict[str, Any]:
    remaining = [cand("ann", "fe", 20, 300_000)]
    pool = pool if pool is not None else (cand("bob", "be", 10, 300_000, 0.9),
                                          cand("cat", "be", 30, 200_000, 0.5))  # fmt: skip
    return {
        "candidates": [*remaining, *pool],
        "slots": {"fe": 1, "be": 1},
        "required_skills": ["k-fe", "k-be"],
        "critical_skills": [],
        "deadline_days": 30,
        "budget_after_fee_paisa": budget,
        "remaining": [0],
        "pool": list(range(1, 1 + len(pool))),
        "unavailable": 0,
        "departed": {"member_id": "m", "slot_id": "be", "skill_id": "k-be", "slot_label": "Backend",
                     "days": 20},
        "plan": [
            {"id": "a", "name": "API", "duration_days": 10, "predecessors": [], "skills": ["k-be"],
             "done": False},
            {"id": "u", "name": "UI", "duration_days": 8, "predecessors": [], "skills": ["k-fe"],
             "done": False},
        ],
        "baseline_days": 10,
        "started": False,
    }  # fmt: skip


def test_ranked_candidates_with_their_impact() -> None:
    out = repair_outcome(snapshot(), PARAMS, 7)
    assert out["status"] == "READY"
    rows = out["candidates"]
    assert [r["bid_id"] for r in rows] == ["bob", "cat"]  # faster and stronger first
    bob, cat = rows
    # API is the departed backend's milestone: 10 days × 10/20 → 5; × 30/20 → 15.
    assert bob["impact"]["affected_milestones"] == ["API"]
    assert (bob["impact"]["new_days"], bob["impact"]["delay_days"]) == (8, -2)  # UI (8) is longer
    assert (cat["impact"]["new_days"], cat["impact"]["delay_days"]) == (15, 5)
    assert bob["team_price_paisa"] == 600_000
    assert bob["impact"]["budget_delta_paisa"] == -400_000
    assert out["impact"]["affected_milestones"] == ["API"]
    assert repair_outcome(snapshot(), PARAMS, 7) == out  # same inputs, same result


def test_reasons_when_nobody_fits() -> None:
    low = repair_outcome(snapshot(budget=450_000), PARAMS, 7)
    assert low["status"] == "NO_CANDIDATES"
    assert low["reasons"][0]["code"] == "REMAINING_BUDGET_TOO_LOW"
    assert low["reasons"][0]["shortfall_paisa"] == 50_000  # 300,000 + 200,000 − 450,000
    empty = repair_outcome(snapshot(pool=()), PARAMS, 7)
    assert [r["code"] for r in empty["reasons"]] == ["NO_BIDS_FOR_SLOT"]
    assert empty["reasons"][0]["message"] == "Nobody else bid for this role."


def test_queue_ignores_nothing() -> None:
    queue(None)  # no proposal → nothing to send
