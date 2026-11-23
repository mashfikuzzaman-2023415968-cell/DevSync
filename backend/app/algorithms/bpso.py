"""Binary particle swarm optimisation — [PCS] Algorithm 2, Eq. 13–16 — with the DevSync repair
operator (spec §9.3). PURE: no clock (the caller passes `should_stop`), seeded NumPy generator.

    init     x^p ~ Bernoulli(N/k), v^p ~ U(b_l, b_u)              (D111; paper lines 3–6)
    repeat   v ← ω·v + z1·r1·(L^p − x) + z2·r2·(g − x)            (Eq. 14; ω = inertia, A13)
             v ← clamp(v, −v_max, v_max)                          (ours; off in replication)
             x_i ← 1 if sigmoid(v_i) ≥ rand() else 0              (Eq. 15–16)
             x ← repair(x)                                        (ours; off in replication)
             F(x) > F(L^p) ⇒ L^p ← x;  F(L^p) > F(g) ⇒ g ← L^p   (lines 12–17)
    until        MAX_IT, `early_stop_iters` without improvement, or the caller's timeout

**Repair** (§9.3, devsync only), in order: (1) fill each slot to its count — drop the extras with
the lowest marginal score, add the missing ones with the highest; (2) meet the newcomer minimum
by swapping the weakest non-newcomer for the best newcomer in the same slot; (3) while over
budget, swap the member with the worst score per paisa for the best cheaper candidate in the same
slot; (4) cover missing skills by a same-slot swap; (5) anything still infeasible scores −∞.
Locked indices are selected first and never removed. Ties break by candidate index, so a run is
reproducible from its snapshot, parameters and seed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from app.algorithms.fitness import NEG_INF, Problem, fitness, infeasibility


@dataclass(frozen=True)
class PsoParams:
    """`pso.*` settings (§6.2)."""

    particles: int = 30
    max_iter: int = 200
    z1: float = 1.5
    z2: float = 1.5
    inertia: float = 1.0
    v_max: float = 4.0
    bounds: tuple[float, float] = (-1.0, 1.0)
    early_stop_iters: int = 40
    archive_size: int = 10

    def __post_init__(self) -> None:
        if self.particles < 1 or self.max_iter < 1 or self.early_stop_iters < 1:
            raise ValueError("particles, max_iter and early_stop_iters must be at least 1")
        if self.bounds[0] >= self.bounds[1]:
            raise ValueError("bounds must satisfy b_l < b_u")
        if self.v_max <= 0:
            raise ValueError("v_max must be positive")


@dataclass(frozen=True)
class PsoResult:
    team: tuple[int, ...]  # candidate indices of gbest (empty when nothing feasible was found)
    fitness: float  # −∞ when infeasible
    feasible: bool
    convergence: tuple[float, ...]  # gbest fitness after each iteration (−∞ until feasible)
    iterations: int
    evaluations: int
    timed_out: bool
    early_stopped: bool
    seed: int
    archive: tuple[tuple[tuple[int, ...], float], ...] = field(default=())  # best distinct teams


def _sigmoid(v: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-v))


class _Repair:
    """The repair operator over one problem (precomputed per-slot orders)."""

    def __init__(self, problem: Problem) -> None:
        self.p = problem
        self.score = [problem.terms(i).total for i in range(problem.size)]
        self.by_slot: dict[str, list[int]] = {s: [] for s in problem.slots}
        for i, cand in enumerate(problem.candidates):
            self.by_slot[cand.slot_id].append(i)

    def _best(self, pool: list[int]) -> int | None:
        return max(pool, key=lambda i: (self.score[i], -i)) if pool else None

    def _worst(self, pool: list[int]) -> int | None:
        return min(pool, key=lambda i: (self.score[i], -i)) if pool else None

    def __call__(self, selected: set[int]) -> set[int]:
        p = self.p
        sel = set(selected) | set(p.locked)
        # (1) slot counts.
        for slot, need in p.slots.items():
            members = [i for i in self.by_slot[slot] if i in sel]
            while len(members) > need:
                drop = self._worst([i for i in members if i not in p.locked])
                if drop is None:
                    break
                sel.discard(drop)
                members.remove(drop)
            while len(members) < need:
                taken = {p.candidates[i].developer_id for i in sel}
                pool = [i for i in self.by_slot[slot]
                        if i not in sel and p.candidates[i].developer_id not in taken]  # fmt: skip
                add = self._best(pool)
                if add is None:
                    break
                sel.add(add)
                members.append(add)
        # Candidates in no slot can't exist (Problem validates), so sel now matches the slots.
        # (2) newcomer minimum.
        while sum(p.candidates[i].newcomer for i in sel) < p.min_newcomers:
            if not self._swap(sel, lambda out, inn: (not p.candidates[out].newcomer
                                                     and p.candidates[inn].newcomer)):  # fmt: skip
                break
        # (3) budget: worst score per paisa first, to the best cheaper same-slot alternative.
        while sum(p.candidates[i].price_paisa for i in sel) > p.budget_after_fee_paisa:
            if not self._cheaper(sel):
                break
        # (4) skill coverage.
        for skill in sorted(self._missing(sel)):
            self._swap(sel, self._brings(skill))
        return sel

    def _brings(self, skill: str) -> Callable[[int, int], bool]:
        """A swap that brings `skill` into the team (step 4)."""

        def allowed(out: int, inn: int) -> bool:
            cands = self.p.candidates
            return skill in cands[inn].skills and skill not in cands[out].skills

        return allowed

    def _missing(self, sel: set[int]) -> frozenset[str]:
        held: set[str] = set()
        for i in sel:
            held |= self.p.candidates[i].skills
        return self.p.required_skills - held

    def _newcomers_ok_after(self, sel: set[int], out: int, inn: int) -> bool:
        p = self.p
        count = sum(p.candidates[i].newcomer for i in sel)
        count += int(p.candidates[inn].newcomer) - int(p.candidates[out].newcomer)
        return count >= min(p.min_newcomers, sum(p.candidates[i].newcomer for i in sel))

    def _swap(self, sel: set[int], allowed: Callable[[int, int], bool]) -> bool:
        """Best same-slot swap (largest score change) that `allowed` permits; never a locked one."""
        p = self.p
        taken = {p.candidates[i].developer_id for i in sel}
        best: tuple[float, int, int] | None = None
        for out in sorted(sel - set(p.locked)):
            slot = p.candidates[out].slot_id
            for inn in self.by_slot[slot]:
                if inn in sel or p.candidates[inn].developer_id in taken or not allowed(out, inn):
                    continue
                gain = self.score[inn] - self.score[out]
                if best is None or (gain, -out, -inn) > (best[0], -best[1], -best[2]):
                    best = (gain, out, inn)
        if best is None:
            return False
        sel.discard(best[1])
        sel.add(best[2])
        return True

    def _cheaper(self, sel: set[int]) -> bool:
        p = self.p
        taken = {p.candidates[i].developer_id for i in sel}
        order = sorted(
            sel - set(p.locked),
            key=lambda i: (self.score[i] / max(p.candidates[i].price_paisa, 1), i),
        )
        for out in order:
            price = p.candidates[out].price_paisa
            pool = [
                inn for inn in self.by_slot[p.candidates[out].slot_id]
                if inn not in sel and p.candidates[inn].developer_id not in taken
                and p.candidates[inn].price_paisa < price
                and self._newcomers_ok_after(sel, out, inn)
            ]  # fmt: skip
            inn = self._best(pool)
            if inn is not None:
                sel.discard(out)
                sel.add(inn)
                return True
        return False


def repair(problem: Problem, selection: set[int]) -> set[int]:
    """The §9.3 repair operator on one selection (devsync). Returns a new set; the result is
    feasible when a feasible team reachable by these steps exists, and is otherwise flagged by
    `fitness` as −∞. Locked indices are always kept."""
    return _Repair(problem)(selection)


def initialise(
    rng: np.random.Generator, particles: int, k: int, n: int, bounds: tuple[float, float]
) -> tuple[np.ndarray, np.ndarray]:
    """Lines 3–6 as resolved in D111: positions x ~ Bernoulli(N/k) (so a particle starts near a
    team of N), velocities v ~ U(b_l, b_u). The paper draws positions from U(b_l, b_u) and
    velocities from U(−|b|, |b|), which gives no valid 0/1 start."""
    x = rng.random((particles, k)) < (n / k)
    v = rng.uniform(bounds[0], bounds[1], (particles, k))
    return x, v


def velocity_update(
    v: np.ndarray,
    *,
    x: np.ndarray,
    pbest: np.ndarray,
    gbest: np.ndarray,
    r1: np.ndarray,
    r2: np.ndarray,
    params: PsoParams,
    clamp: bool,
) -> np.ndarray:
    """Eq. 14: v ← ω·v + z1·r1·(L − x) + z2·r2·(g − x), ω = `inertia` (1.0 = the paper, A13);
    then the v_max clamp (ours, off in replication)."""
    xf = x.astype(float)
    out = (
        params.inertia * v
        + params.z1 * r1 * (pbest.astype(float) - xf)
        + params.z2 * r2 * (gbest.astype(float) - xf)
    )
    clamped: np.ndarray = np.clip(out, -params.v_max, params.v_max)
    return clamped if clamp else out


def position_update(v: np.ndarray, rand: np.ndarray) -> np.ndarray:
    """Eq. 15–16: x_i = 1 if sigmoid(v_i) ≥ rand() else 0."""
    chosen: np.ndarray = _sigmoid(v) >= rand
    return chosen


class _Swarm:
    """Particle state for one run (positions, velocities, personal and global bests)."""

    def __init__(self, problem: Problem, params: PsoParams, rng: np.random.Generator) -> None:
        self.problem, self.params, self.rng = problem, params, rng
        self.k, self.n = problem.size, problem.team_size
        self.fixer = None if problem.replication else _Repair(problem)
        self.archive: dict[tuple[int, ...], float] = {}
        self.evaluations = 0
        self.x, self.v = initialise(rng, params.particles, self.k, self.n, params.bounds)
        self.pbest = np.zeros_like(self.x)
        self.pbest_fit = np.full(params.particles, NEG_INF)
        for p_i in range(params.particles):
            f = self._evaluate(p_i)
            self.pbest[p_i], self.pbest_fit[p_i] = self.x[p_i], f
        g_i = int(np.argmax(self.pbest_fit))
        self.gbest, self.gbest_fit = self.pbest[g_i].copy(), float(self.pbest_fit[g_i])

    def _evaluate(self, p_i: int) -> float:
        """Repair particle `p_i` in place (devsync), score it and remember feasible teams."""
        sel = set(np.flatnonzero(self.x[p_i]).tolist())
        if self.fixer is not None:
            sel = self.fixer(sel)
            row = np.zeros(self.k, dtype=bool)
            row[list(sel)] = True
            self.x[p_i] = row
        self.evaluations += 1
        f = fitness(self.problem, sel)
        if f > NEG_INF:
            self.archive[tuple(sorted(sel))] = f
        return f

    def step(self) -> bool:
        """One iteration of Algorithm 2's main loop; True when gbest improved."""
        prm, rng = self.params, self.rng
        r1 = rng.random((prm.particles, self.k))
        r2 = rng.random((prm.particles, self.k))
        clamp = self.fixer is not None  # the v_max clamp is a DevSync safeguard
        self.v = velocity_update(
            self.v,
            x=self.x,
            pbest=self.pbest,
            gbest=self.gbest,
            r1=r1,
            r2=r2,
            params=prm,
            clamp=clamp,
        )
        self.x = position_update(self.v, rng.random((prm.particles, self.k)))
        improved = False
        for p_i in range(prm.particles):
            f = self._evaluate(p_i)
            if f > self.pbest_fit[p_i]:
                self.pbest[p_i], self.pbest_fit[p_i] = self.x[p_i], f
                if f > self.gbest_fit:
                    self.gbest, self.gbest_fit = self.x[p_i].copy(), f
                    improved = True
        return improved


def run_bpso(
    problem: Problem,
    params: PsoParams,
    seed: int,
    *,
    should_stop: Callable[[], bool] | None = None,
    on_iteration: Callable[[int, float], None] | None = None,
) -> PsoResult:
    """Algorithm 2. `should_stop` is checked once per iteration (the caller's timeout);
    `on_iteration(iteration, gbest_fitness)` reports progress (SSE)."""
    if problem.size == 0 or problem.team_size > problem.size:
        return PsoResult((), NEG_INF, False, (), 0, 0, False, False, seed)
    swarm = _Swarm(problem, params, np.random.default_rng(seed))
    convergence: list[float] = []
    since_improved = 0
    timed_out = early_stopped = False
    done = 0
    while done < params.max_iter:
        if should_stop is not None and should_stop():
            timed_out = True
            break
        improved = swarm.step()
        done += 1
        convergence.append(swarm.gbest_fit)
        if on_iteration is not None:
            on_iteration(done, swarm.gbest_fit)
        since_improved = 0 if improved else since_improved + 1
        if since_improved >= params.early_stop_iters:
            early_stopped = True
            break
    fit = swarm.gbest_fit
    team = tuple(np.flatnonzero(swarm.gbest).tolist()) if fit > NEG_INF else ()
    ranked = sorted(swarm.archive.items(), key=lambda kv: (-kv[1], kv[0]))[: params.archive_size]
    return PsoResult(
        team=team,
        fitness=fit,
        feasible=fit > NEG_INF and infeasibility(problem, team) is None,
        convergence=tuple(convergence),
        iterations=done,
        evaluations=swarm.evaluations,
        timed_out=timed_out,
        early_stopped=early_stopped,
        seed=seed,
        archive=tuple(ranked),
    )
