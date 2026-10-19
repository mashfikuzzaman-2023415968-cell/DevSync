"""CPM unit, property and performance tests (spec §9.10, §17 Phase 4, §18.2).

The headline case is the "Online ordering system" plan from §18.2, whose ES/EF/LS/LF
values the Phase 4 gate checks. Other cases cover a single milestone, parallel branches
with slack, multiple critical paths, long chains, cycle detection and input validation.
"""

from __future__ import annotations

import time
from datetime import date
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms.cpm import (
    CpmCycleError,
    CpmNode,
    CpmValidationError,
    MilestoneInput,
    compute_cpm,
    find_cycle,
    schedule_dates,
)

# The §18.2 "Online ordering system" plan (ids double as readable names).
ORDERING_SYSTEM = [
    MilestoneInput("Requirements", 4, (), "Requirements & design"),
    MilestoneInput("Database", 5, ("Requirements",), "Database"),
    MilestoneInput("Backend API", 8, ("Database",), "Backend API"),
    MilestoneInput("Frontend", 9, ("Requirements",), "Frontend"),
    MilestoneInput("Integration", 3, ("Backend API", "Frontend"), "Integration"),
    MilestoneInput("Testing", 4, ("Integration",), "Testing & launch"),
]


def test_ordering_system_matches_spec_18_2() -> None:
    """Golden values from §18.2: duration 24, the documented ES/EF and Frontend's slack 4."""
    result = compute_cpm(ORDERING_SYSTEM)
    assert result.duration == 24
    assert result.nodes["Requirements"] == CpmNode(0, 4, 0, 4, 0, True)
    assert result.nodes["Database"] == CpmNode(4, 9, 4, 9, 0, True)
    assert result.nodes["Backend API"] == CpmNode(9, 17, 9, 17, 0, True)
    assert result.nodes["Frontend"] == CpmNode(4, 13, 8, 17, 4, False)
    assert result.nodes["Integration"] == CpmNode(17, 20, 17, 20, 0, True)
    assert result.nodes["Testing"] == CpmNode(20, 24, 20, 24, 0, True)
    assert result.critical_paths == (
        ("Requirements", "Database", "Backend API", "Integration", "Testing"),
    )


def test_single_milestone() -> None:
    result = compute_cpm([MilestoneInput("only", 5)])
    assert result.duration == 5
    assert result.nodes["only"] == CpmNode(0, 5, 0, 5, 0, True)
    assert result.critical_paths == (("only",),)


def test_empty_plan() -> None:
    result = compute_cpm([])
    assert result.duration == 0
    assert result.nodes == {}
    assert result.critical_paths == ()


def test_parallel_branches_with_slack() -> None:
    """Two branches off a start; the shorter one has slack, the longer is critical."""
    plan = [
        MilestoneInput("start", 2),
        MilestoneInput("short", 2, ("start",)),
        MilestoneInput("long", 5, ("start",)),
        MilestoneInput("end", 1, ("short", "long")),
    ]
    result = compute_cpm(plan)
    assert result.duration == 8  # 2 + 5 + 1
    assert result.nodes["long"].critical
    assert not result.nodes["short"].critical
    assert result.nodes["short"].slack == 3  # long finishes 3 days after short
    assert result.critical_paths == (("start", "long", "end"),)


def test_multiple_critical_paths() -> None:
    """A diamond with two equal-length branches has two critical paths, both reported."""
    plan = [
        MilestoneInput("A", 2),
        MilestoneInput("B", 3, ("A",)),
        MilestoneInput("C", 3, ("A",)),
        MilestoneInput("D", 2, ("B", "C")),
    ]
    result = compute_cpm(plan)
    assert result.duration == 7
    assert all(result.nodes[m].critical for m in ("A", "B", "C", "D"))
    assert set(result.critical_paths) == {("A", "B", "D"), ("A", "C", "D")}


def test_long_chain() -> None:
    plan = [MilestoneInput("m0", 3)]
    plan += [MilestoneInput(f"m{i}", 3, (f"m{i - 1}",)) for i in range(1, 10)]
    result = compute_cpm(plan)
    assert result.duration == 30
    assert all(node.critical for node in result.nodes.values())
    assert result.critical_paths == (tuple(f"m{i}" for i in range(10)),)


def test_cycle_is_detected_and_reported_in_order() -> None:
    """A dependency cycle raises CpmCycleError whose `cycle` is an ordered, closed walk."""
    plan = [
        MilestoneInput("A", 1, ("C",)),
        MilestoneInput("B", 1, ("A",)),
        MilestoneInput("C", 1, ("B",)),
    ]
    with pytest.raises(CpmCycleError) as exc:
        compute_cpm(plan)
    cycle = exc.value.cycle
    assert cycle[0] == cycle[-1]  # closes on itself
    assert set(cycle) == {"A", "B", "C"}
    # Each consecutive pair is a real predecessor edge.
    preds = {m.id: m.predecessors for m in plan}
    assert all(cycle[i + 1] in preds[cycle[i]] for i in range(len(cycle) - 1))


def test_find_cycle_returns_none_for_a_dag() -> None:
    assert find_cycle(ORDERING_SYSTEM) is None


@pytest.mark.parametrize(
    ("plan", "message"),
    [
        ([MilestoneInput("x", 1), MilestoneInput("x", 2)], "duplicate"),
        ([MilestoneInput("x", 1, ("ghost",))], "unknown predecessor"),
        ([MilestoneInput("x", 1, ("x",))], "itself"),
        ([MilestoneInput("x", 1), MilestoneInput("y", 1, ("x", "x"))], "twice"),
        ([MilestoneInput("x", 0)], "duration"),
        ([MilestoneInput("x", -3)], "duration"),
    ],
)
def test_validation_errors(plan: list[MilestoneInput], message: str) -> None:
    with pytest.raises(CpmValidationError, match=message):
        compute_cpm(plan)


def test_find_cycle_ignores_unknown_predecessors() -> None:
    """Called directly (before validation), `find_cycle` skips ids it doesn't know."""
    assert find_cycle([MilestoneInput("x", 1, ("ghost",))]) is None


def test_schedule_dates_offsets_from_start() -> None:
    result = compute_cpm(ORDERING_SYSTEM)
    dates = schedule_dates(result, date(2026, 11, 2))
    assert dates["Requirements"] == (date(2026, 11, 2), date(2026, 11, 6))  # ES 0, EF 4
    assert dates["Testing"] == (date(2026, 11, 22), date(2026, 11, 26))  # ES 20, EF 24


# --------------------------------------------------------------------------- property tests


@st.composite
def dags(draw: st.DrawFn) -> list[MilestoneInput]:
    """Random acyclic plans: each milestone depends only on earlier ones (acyclic by build)."""
    n = draw(st.integers(min_value=1, max_value=10))
    milestones: list[MilestoneInput] = []
    for i in range(n):
        earlier = [f"m{j}" for j in range(i)]
        preds = draw(st.lists(st.sampled_from(earlier), unique=True)) if earlier else []
        duration = draw(st.integers(min_value=1, max_value=12))
        milestones.append(MilestoneInput(f"m{i}", duration, tuple(preds)))
    return milestones


@given(plan=dags())
@settings(max_examples=200)
def test_schedule_is_internally_consistent(plan: list[MilestoneInput]) -> None:
    result = compute_cpm(plan)
    by_id = {m.id: m for m in plan}
    for mid, node in result.nodes.items():
        assert node.ef == node.es + by_id[mid].duration_days
        assert node.lf == node.ls + by_id[mid].duration_days
        assert node.slack == node.ls - node.es == node.lf - node.ef
        assert node.slack >= 0
        # A milestone never starts before any predecessor finishes.
        for p in by_id[mid].predecessors:
            assert node.es >= result.nodes[p].ef
    assert result.duration == max(node.ef for node in result.nodes.values())


@given(plan=dags())
@settings(max_examples=200)
def test_at_least_one_tight_critical_path(plan: list[MilestoneInput]) -> None:
    result = compute_cpm(plan)
    assert result.critical_paths  # always at least one
    for path in result.critical_paths:
        assert all(result.nodes[mid].critical for mid in path)
        for a, b in pairwise(path):
            assert result.nodes[a].ef == result.nodes[b].es  # finish-to-start tight


@given(plan=dags())
@settings(max_examples=100)
def test_a_back_edge_makes_a_cycle(plan: list[MilestoneInput]) -> None:
    """Reversing an existing dependency edge closes a two-node loop, which must be detected."""
    edge = next(((m.predecessors[0], m.id) for m in plan if m.predecessors), None)
    if edge is None:
        return  # an edgeless plan can't be made cyclic
    pred, child = edge  # `child` depends on `pred`; now make `pred` also depend on `child`
    looped = [
        MilestoneInput(m.id, m.duration_days, (*m.predecessors, child)) if m.id == pred else m
        for m in plan
    ]
    with pytest.raises(CpmCycleError):
        compute_cpm(looped)


# --------------------------------------------------------------------------- performance


@pytest.mark.perf
def test_cpm_300_milestones_under_50ms() -> None:
    """Spec §9.10/§16.5 step 16: 300 milestones must compute in under 50 ms."""
    plan = [MilestoneInput("m0", 2)]
    plan += [MilestoneInput(f"m{i}", 2, (f"m{i - 1}",)) for i in range(1, 300)]
    start = time.perf_counter()
    result = compute_cpm(plan)
    elapsed = time.perf_counter() - start
    assert result.duration == 600
    assert elapsed < 0.05, f"CPM took {elapsed * 1000:.1f} ms for 300 milestones"
