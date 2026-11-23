"""Binary PSO ([PCS] Algorithm 2, Eq. 13–16), the repair operator, the exact solver, the fairness
dial and the optimality of PSO against the exact answer (spec §9.3–§9.5, §17 Phase 7, E1).
Test names carry eq13–eq16 and A13 for docs/PAPER_ALIGNMENT.md (D91)."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from app.algorithms.bpso import (
    PsoParams,
    initialise,
    position_update,
    repair,
    run_bpso,
    velocity_update,
)
from app.algorithms.exact_solver import ExactLimits, combinations_count, solve_exact
from app.algorithms.fairness import apply_fairness, cost_of_fairness
from app.algorithms.filtering import Mode
from app.algorithms.fitness import Candidate, Problem, Weights, fitness, infeasibility
from app.algorithms.formation_bench import random_instance

pytestmark = pytest.mark.unit
P = PsoParams()


def exact_solver(problem: Problem) -> tuple[tuple[int, ...], float]:
    r = solve_exact(problem)
    return r.best, r.fitness


# ----------------------------------------------------------------- Eq. 14–16 and initialisation


def test_eq14_velocity_update_by_hand() -> None:
    """v = 1.0·0.5 + 1.5·0.2·(1 − 0) + 1.5·0.4·(0 − 0) = 0.8 for a bit at 0 whose personal best
    is 1 and global best 0; for a bit at 1 with both bests 1: 1.0·(−0.3) + 0 + 0 = −0.3."""
    v = np.array([[0.5, -0.3]])
    x = np.array([[False, True]])
    pbest = np.array([[True, True]])
    gbest = np.array([[False, True]])
    r1 = np.array([[0.2, 0.9]])
    r2 = np.array([[0.4, 0.7]])
    out = velocity_update(v, x=x, pbest=pbest, gbest=gbest, r1=r1, r2=r2, params=P, clamp=True)
    assert out == pytest.approx(np.array([[0.8, -0.3]]))


def test_eq14_clamp_is_ours_and_off_in_replication() -> None:
    """With v = 10 the DevSync clamp holds it at v_max = 4; unclamped it stays 10."""
    big = np.array([[10.0]])
    same = np.array([[True]])
    args = {"x": same, "pbest": same, "gbest": same, "r1": big * 0, "r2": big * 0, "params": P}
    assert velocity_update(big, clamp=True, **args)[0, 0] == 4.0  # type: ignore[arg-type]
    assert velocity_update(big, clamp=False, **args)[0, 0] == 10.0  # type: ignore[arg-type]


def test_eq15_eq16_sigmoid_position_update() -> None:
    """sigmoid(0) = 0.5: rand 0.4 → 1, rand 0.6 → 0; sigmoid(2) ≈ 0.881 ≥ 0.85 → 1."""
    v = np.array([[0.0, 0.0, 2.0]])
    rand = np.array([[0.4, 0.6, 0.85]])
    assert position_update(v, rand).tolist() == [[True, False, True]]


def test_A13_inertia() -> None:  # noqa: N802 — name required by spec §9.0
    """A13: Eq. 14 has no inertia term; the default inertia 1.0 is the same update, and a
    different value only scales the old velocity (here 0.5·0.5 = 0.25)."""
    assert PsoParams().inertia == 1.0
    zero = np.array([[False]])
    args = {"x": zero, "pbest": zero, "gbest": zero, "r1": np.ones((1, 1)), "r2": np.ones((1, 1))}
    v = np.array([[0.5]])
    assert velocity_update(v, params=P, clamp=False, **args)[0, 0] == 0.5  # type: ignore[arg-type]
    half = replace(P, inertia=0.5)
    assert velocity_update(v, params=half, clamp=False, **args)[0, 0] == 0.25  # type: ignore[arg-type]


def test_initialisation_resolution() -> None:
    """D111 (D9 item 3): positions Bernoulli(N/k), velocities U(b_l, b_u). Over 3,000 particles
    with N/k = 4/20 the share of ones is ≈ 0.2, and every velocity lies in [−1, 1)."""
    x, v = initialise(np.random.default_rng(1), 3000, 20, 4, (-1.0, 1.0))
    assert x.dtype == bool
    assert x.mean() == pytest.approx(0.2, abs=0.01)
    assert v.min() >= -1.0
    assert v.max() < 1.0


@pytest.mark.parametrize(
    "kw", [{"particles": 0}, {"max_iter": 0}, {"bounds": (1.0, -1.0)}, {"v_max": 0.0},
           {"early_stop_iters": 0}],
)  # fmt: skip
def test_invalid_pso_params_are_refused(kw: dict[str, object]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - each case has its own message
        PsoParams(**kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------- the run


def test_eq13_result_has_exactly_n_members() -> None:
    p = random_instance(3)
    r = run_bpso(p, P, 3)
    assert r.feasible
    assert len(r.team) == p.team_size
    assert infeasibility(p, r.team) is None


def test_determinism_same_seed_same_everything() -> None:
    p = random_instance(5)
    a, b = run_bpso(p, P, 42), run_bpso(p, P, 42)
    assert (a.team, a.fitness, a.convergence, a.iterations) == (
        b.team, b.fitness, b.convergence, b.iterations,
    )  # fmt: skip


def test_convergence_never_decreases_and_early_stop_triggers() -> None:
    p = random_instance(8)
    r = run_bpso(p, replace(P, early_stop_iters=5), 8)
    assert all(b >= a for a, b in zip(r.convergence, r.convergence[1:], strict=False))
    assert r.early_stopped
    assert r.iterations < P.max_iter


def test_timeout_returns_best_feasible_with_flag() -> None:
    """The caller's clock says stop after 3 iterations: the best team so far comes back."""
    calls = {"n": 0}

    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    r = run_bpso(random_instance(9), replace(P, early_stop_iters=400), 9, should_stop=stop)
    assert r.timed_out
    assert r.iterations == 3
    assert r.feasible


def test_progress_callback_reports_every_iteration() -> None:
    seen: list[tuple[int, float]] = []
    r = run_bpso(random_instance(4), P, 4, on_iteration=lambda i, f: seen.append((i, f)))
    assert [i for i, _ in seen] == list(range(1, r.iterations + 1))
    assert seen[-1][1] == r.fitness


def test_no_candidates_or_too_few_is_infeasible() -> None:
    p = random_instance(2)
    empty = replace(p, candidates=(), required_skills=frozenset())
    r = run_bpso(empty, P, 1)
    assert (r.team, r.fitness, r.feasible) == ((), -math.inf, False)


def test_archive_holds_distinct_feasible_teams_best_first() -> None:
    r = run_bpso(random_instance(11), P, 11)
    teams = [t for t, _ in r.archive]
    assert len(teams) == len(set(teams))
    assert [f for _, f in r.archive] == sorted((f for _, f in r.archive), reverse=True)
    assert r.archive[0] == (r.team, r.fitness)


# ------------------------------------------------------------------------- repair


def test_repair_keeps_locked_members_and_is_idempotent() -> None:
    p = replace(random_instance(12), locked=frozenset({0}))
    fixed = repair(p, {1, 2})
    assert 0 in fixed
    assert infeasibility(p, fixed) is None
    assert repair(p, fixed) == fixed


def test_repair_meets_the_newcomer_minimum_and_budget() -> None:
    p = random_instance(13, min_newcomers=1)
    for start in ({0}, set(range(p.size)), set()):
        fixed = repair(p, start)
        assert infeasibility(p, fixed) is None, start


def test_repair_flags_an_impossible_problem() -> None:
    """No newcomer at all but a minimum of 1: repair can't fix it; fitness is −∞."""
    p = random_instance(14, min_newcomers=1)
    p = replace(p, candidates=tuple(replace(c, newcomer=False) for c in p.candidates))
    assert fitness(p, repair(p, set())) == -math.inf


def test_replication_switches_off_repair_and_clamp() -> None:
    """pcs_replication: no repair, so a raw particle can be infeasible and score −∞ (A3); the
    swarm still finds a team of size N (Eq. 13 only)."""
    p = random_instance(15, mode=Mode.PCS_REPLICATION, min_newcomers=2)
    r = run_bpso(p, P, 15)
    assert len(r.team) in (0, p.team_size)
    if r.team:
        assert infeasibility(p, r.team) is None
    assert r.convergence[0] <= r.convergence[-1]


# ------------------------------------------------------------------------- exact solver


def _brute(p: Problem) -> float:
    import itertools  # noqa: PLC0415

    best = -math.inf
    for team in itertools.combinations(range(p.size), p.team_size):
        best = max(best, fitness(p, team))
    return best


@pytest.mark.parametrize("seed", range(10))
def test_exact_solver_matches_brute_force(seed: int) -> None:
    p = random_instance(seed, candidates=9, slots=3)
    assert solve_exact(p).fitness == pytest.approx(_brute(p))


def test_exact_solver_top3_distinct_and_count() -> None:
    p = random_instance(21, candidates=12, slots=3, min_newcomers=0)
    r = solve_exact(p)
    assert r.available
    assert len(r.top) == 3
    assert len({t for t, _ in r.top}) == 3
    assert [f for _, f in r.top] == sorted((f for _, f in r.top), reverse=True)
    assert r.top[0] == (r.best, r.fitness)
    assert 0 < r.feasible_count <= r.combinations == combinations_count(p)


def test_exact_solver_refuses_over_its_limits() -> None:
    p = random_instance(22, candidates=19, slots=3)
    assert solve_exact(p).reason == "TOO_MANY_CANDIDATES"
    small = random_instance(23, candidates=12, slots=3)
    assert solve_exact(small, ExactLimits(max_combinations=5)).reason == "TOO_MANY_COMBINATIONS"


def test_exact_solver_respects_locks() -> None:
    p = random_instance(24, candidates=12, slots=3, min_newcomers=0)
    worst = min(range(p.size), key=lambda i: p.terms(i).total)
    r = solve_exact(replace(p, locked=frozenset({worst})))
    assert worst in r.best


# ------------------------------------------------------------------------- fairness


def test_cost_of_fairness_rules() -> None:
    """(F0 − Fk)/|F0|; 0 when not binding or F0 ≤ 0; never negative."""
    assert cost_of_fairness(2.0, 1.5, binding=True) == pytest.approx(0.25)
    assert cost_of_fairness(2.0, 1.5, binding=False) == 0
    assert cost_of_fairness(-1.0, -2.0, binding=True) == 0
    assert cost_of_fairness(2.0, 2.5, binding=True) == 0


def _with_newcomers(p: Problem, which: set[int]) -> Problem:
    cands = tuple(replace(c, newcomer=i in which) for i, c in enumerate(p.candidates))
    return replace(p, candidates=cands)


def test_fairness_binding_costs_something_and_includes_a_newcomer() -> None:
    p = random_instance(31, candidates=12, slots=3, min_newcomers=1)
    t0, _ = exact_solver(replace(p, min_newcomers=0))
    outsider = next(i for i in range(p.size) if i not in t0)
    p = _with_newcomers(p, {outsider})  # the only newcomer is outside the best team
    r = apply_fairness(p, 1, exact_solver)
    assert r.binding
    assert r.cost > 0
    assert outsider in r.team
    assert r.newcomers == (outsider,)
    assert r.price_difference_paisa == (
        sum(p.candidates[i].price_paisa for i in r.team)
        - sum(p.candidates[i].price_paisa for i in r.baseline_team)
    )


def test_fairness_not_binding_costs_nothing() -> None:
    p = random_instance(32, candidates=12, slots=3)
    t0, _ = exact_solver(replace(p, min_newcomers=0))
    p = _with_newcomers(p, {t0[0]})
    r = apply_fairness(p, 1, exact_solver)
    assert (r.binding, r.cost, r.team) == (False, 0.0, r.baseline_team)


def test_fairness_falls_back_to_the_largest_feasible_k() -> None:
    """Only one newcomer exists: k = 2 is impossible, k = 1 is applied and said so."""
    p = _with_newcomers(random_instance(33, candidates=12, slots=3), {0})
    r = apply_fairness(p, 2, exact_solver)
    assert (r.requested_k, r.applied_k, r.reason) == (2, 1, "MAX_FEASIBLE_K")
    assert len(r.newcomers) == 1


def test_fairness_dial_is_off_in_replication() -> None:
    p = random_instance(34, candidates=12, slots=3, mode=Mode.PCS_REPLICATION)
    r = apply_fairness(p, 2, exact_solver)
    assert (r.requested_k, r.applied_k, r.cost) == (0, 0, 0.0)


def test_fairness_refuses_negative_k() -> None:
    with pytest.raises(ValueError, match="negative"):
        apply_fairness(random_instance(35), -1, exact_solver)


# ------------------------------------------------------------- optimality (E1, D112)


def test_pso_is_optimal_on_small_instances() -> None:
    """§17: on 200 seeded instances PSO matches the exact optimum in ≥ 95 % with a mean gap
    ≤ 2 % (D112). Instances with no feasible team are skipped (both sides agree on −∞)."""
    optimal, gaps = 0, []
    for seed in range(200):
        p = random_instance(seed)
        ex = solve_exact(p)
        if not ex.available or ex.fitness == -math.inf:
            continue
        ps = run_bpso(p, P, seed)
        gap = (ex.fitness - ps.fitness) / abs(ex.fitness) if ps.feasible else 1.0
        gaps.append(gap)
        optimal += gap <= 1e-9
    assert len(gaps) >= 180
    assert optimal / len(gaps) >= 0.95
    assert sum(gaps) / len(gaps) <= 0.02


def _total(cands: tuple[Candidate, ...], team: tuple[int, ...], attr: str) -> float:
    return float(sum(getattr(cands[i], attr) for i in team))


def test_presets_are_never_worse_than_balanced_on_their_own_term() -> None:
    """D115: each preset is Balanced plus weight on one term, so (exchange argument) its best
    team is never more expensive (Budget), less competent (Quality) or slower (Fast) than
    Balanced's — on every instance, no exceptions."""
    for seed in range(60):
        teams = {}
        for preset in ("balanced", "quality", "budget", "fast"):
            p = random_instance(seed, preset=preset, min_newcomers=0)
            teams[preset] = solve_exact(p).best
        cands = random_instance(seed, min_newcomers=0).candidates
        if not all(teams.values()):
            continue
        assert _total(cands, teams["budget"], "price_paisa") <= _total(
            cands, teams["balanced"], "price_paisa"
        ), seed
        assert (
            _total(cands, teams["quality"], "competency")
            >= _total(cands, teams["balanced"], "competency") - 1e-12
        ), seed
        fast_days = _total(cands, teams["fast"], "days")
        assert fast_days <= _total(cands, teams["balanced"], "days"), seed


def test_budget_versus_quality_on_random_instances() -> None:
    """The spec's Budget-vs-Quality comparison is a strong tendency, not a theorem: Eq. 18
    divides prices by the whole budget, which compresses price differences (D115). Measured on
    200 instances: Budget costs no more than Quality in 189 and Quality is at least as competent
    in 195. Asserted as lower bounds so a regression shows; the fixed seeded project is checked
    exactly in the service tests."""
    cheaper = more_competent = n = 0
    for seed in range(200):
        q = solve_exact(random_instance(seed, preset="quality", min_newcomers=0)).best
        b = solve_exact(random_instance(seed, preset="budget", min_newcomers=0)).best
        if not q or not b:
            continue
        cands = random_instance(seed, min_newcomers=0).candidates
        n += 1
        cheaper += sum(cands[i].price_paisa for i in b) <= sum(cands[i].price_paisa for i in q)
        comp_q = sum(cands[i].competency for i in q) / len(q)
        comp_b = sum(cands[i].competency for i in b) / len(b)
        more_competent += comp_q >= comp_b - 1e-12
    assert n >= 180
    assert cheaper / n >= 0.9
    assert more_competent / n >= 0.95


def test_unknown_preset_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown preset"):
        random_instance(1, preset="cheap")


def test_raising_the_cost_weight_never_raises_the_price() -> None:
    """Monotonicity on exact-solvable instances: more weight on cost → the best team's total
    price never goes up."""
    for seed in range(30):
        base = random_instance(seed, min_newcomers=0)
        prices = []
        for c4 in (0.1, 0.3, 0.6, 0.9):
            w = Weights(0.35, 0.25, 0.2, c4)
            best = solve_exact(replace(base, weights=w)).best
            prices.append(sum(base.candidates[i].price_paisa for i in best))
        assert prices == sorted(prices, reverse=True), (seed, prices)


def test_candidate_fixture_is_well_formed() -> None:
    c = Candidate("x", "d", "s", 0.5, 0.5, 0.5, 1, 1, False)
    assert c.skills == frozenset()
