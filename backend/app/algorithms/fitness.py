"""Team fitness — [PCS] Eq. 17–19 — and feasibility (spec §9.3). PURE.

A *problem* is the frozen candidate snapshot of one formation run: the shortlisted bids (one
candidate per bid, each in one slot), the slots' counts, the deadline T^d, the budget after the
platform fee C (A10), the skills the plan needs, the weights C1–C4 and the newcomer minimum.
A *selection* is a set of candidate indices (a 0/1 position vector in PSO terms).

    t̄_i = t_i / T^d                                           (Eq. 19)
    c̄_i = c_i / C                                             (Eq. 18, C = budget after fee, A10)
    F(X) = Σ_{x_i = 1} ( C1·C_i + C2·X_(M,i) − C3·t̄_i − C4·c̄_i )   if feasible        (Eq. 17)
         = −∞                                                     otherwise (A3)

C1 + C2 + C3 + C4 = 1 (the client's sliders, normalised here). With `include_performance` (A7,
off by default) the member term also gets C5·P_i, where C5 equals C1 and all five weights are then
normalised to sum to 1 (D114). Floats are fine here (D105); stored values are rounded by callers.

**Feasibility.** In `devsync` mode a team is feasible when it has exactly N members, each slot
has exactly its count, developers are distinct, Σ c_i ≤ C, every required skill is held by a
member, and at least `min_newcomers` members are newcomers. `pcs_replication` checks only the
paper's Eq. 13 (Σ x_i = N, distinct developers): the slots, team budget, skill coverage and the
newcomer minimum are DevSync extensions (D114).
"""

from __future__ import annotations

import enum
import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from app.algorithms.filtering import Mode

NEG_INF = -math.inf


@dataclass(frozen=True)
class Candidate:
    """One shortlisted bid, frozen into the run's snapshot (§14.13 row 7)."""

    bid_id: str
    developer_id: str
    slot_id: str
    competency: float  # C_i (or C_{i,s} when fitness.use_skill_competency; the service decides)
    teamwork: float  # X_(M,i)
    performance: float  # P_i (used only with include_performance, A7)
    days: int  # t_i
    price_paisa: int  # c_i
    newcomer: bool
    skills: frozenset[str] = frozenset()  # skill ids the developer holds (for coverage)


@dataclass(frozen=True)
class Weights:
    """The client's priority sliders C1–C4 (any non-negative values; normalised to sum 1)."""

    competency: float
    teamwork: float
    time: float
    cost: float

    def normalised(self, include_performance: bool = False) -> tuple[float, ...]:
        raw = [self.competency, self.teamwork, self.time, self.cost]
        if any(w < 0 or not math.isfinite(w) for w in raw):
            raise ValueError("weights must be finite and non-negative")
        if include_performance:
            raw.append(self.competency)  # C5 = C1 before normalising (D114)
        total = sum(raw)
        if total <= 0:
            raise ValueError("at least one weight must be positive")
        return tuple(w / total for w in raw)


@dataclass(frozen=True)
class Problem:
    """Everything fitness and the optimisers need; built once per run by the service."""

    candidates: tuple[Candidate, ...]
    slots: Mapping[str, int]  # slot id -> count
    deadline_days: int  # T^d
    budget_after_fee_paisa: int  # C (A10)
    weights: Weights
    min_newcomers: int = 0
    required_skills: frozenset[str] = frozenset()
    include_performance: bool = False
    mode: Mode = Mode.DEVSYNC
    locked: frozenset[int] = frozenset()  # indices that must stay selected (forced inclusion)
    _terms: tuple[MemberTerms, ...] = field(default=(), compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.deadline_days <= 0 or self.budget_after_fee_paisa <= 0:
            raise ValueError("deadline and budget must be positive")
        if any(c < 1 for c in self.slots.values()) or not self.slots:
            raise ValueError("every slot needs a count of at least 1")
        if self.min_newcomers < 0:
            raise ValueError("min_newcomers must not be negative")
        known = set(self.slots)
        for cand in self.candidates:
            if cand.slot_id not in known:
                raise ValueError(f"candidate {cand.bid_id} is in an unknown slot")
            if cand.days < 0 or cand.price_paisa < 0:
                raise ValueError("days and prices must not be negative")
        if any(i < 0 or i >= len(self.candidates) for i in self.locked):
            raise ValueError("locked index out of range")
        object.__setattr__(self, "_terms", tuple(member_terms(self, i) for i in range(self.size)))

    @property
    def size(self) -> int:
        return len(self.candidates)

    @property
    def team_size(self) -> int:
        """N (Eq. 13)."""
        return sum(self.slots.values())

    @property
    def replication(self) -> bool:
        return self.mode is Mode.PCS_REPLICATION

    def terms(self, i: int) -> MemberTerms:
        return self._terms[i]


@dataclass(frozen=True)
class MemberTerms:
    """One member's contribution to Eq. 17, by term (used for the breakdown and explanations)."""

    comp: float  # +C1·C_i
    team: float  # +C2·X_(M,i)
    time: float  # −C3·t̄_i
    cost: float  # −C4·c̄_i
    perf: float = 0.0  # +C5·P_i (A7, optional)

    @property
    def total(self) -> float:
        return self.comp + self.team + self.time + self.cost + self.perf


def member_terms(problem: Problem, i: int) -> MemberTerms:
    """Eq. 17's per-member term with Eq. 18–19 normalisation."""
    cand = problem.candidates[i]
    w = problem.weights.normalised(problem.include_performance)
    t_bar = cand.days / problem.deadline_days  # Eq. 19
    c_bar = cand.price_paisa / problem.budget_after_fee_paisa  # Eq. 18 (A10)
    perf = w[4] * cand.performance if problem.include_performance else 0.0
    return MemberTerms(
        comp=w[0] * cand.competency,
        team=w[1] * cand.teamwork,
        time=-w[2] * t_bar,
        cost=-w[3] * c_bar,
        perf=perf,
    )


class Infeasible(enum.StrEnum):
    """Why a selection is not a valid team (the first failing rule, in this order)."""

    SIZE = "SIZE"
    SLOT_COUNT = "SLOT_COUNT"
    DUPLICATE_DEVELOPER = "DUPLICATE_DEVELOPER"
    OVER_BUDGET = "OVER_BUDGET"
    SKILL_COVERAGE = "SKILL_COVERAGE"
    NEWCOMERS = "NEWCOMERS"


def infeasibility(problem: Problem, selection: Iterable[int]) -> Infeasible | None:
    """None when `selection` is a feasible team (§9.3 "Feasible"), else the first failed rule."""
    chosen = sorted(set(selection))
    members = [problem.candidates[i] for i in chosen]

    def coverage_ok() -> bool:
        held: set[str] = set()
        for m in members:
            held |= m.skills
        return problem.required_skills <= held

    per_slot = Counter(m.slot_id for m in members)
    # Ordered rules; replication checks only Eq. 13 (size) and distinct developers (D114).
    rules: list[tuple[Infeasible, Callable[[], bool]]] = [
        (Infeasible.SIZE, lambda: len(chosen) == problem.team_size),
        (Infeasible.DUPLICATE_DEVELOPER,
         lambda: len({m.developer_id for m in members}) == len(members)),
    ]  # fmt: skip
    if not problem.replication:
        rules += [
            (Infeasible.SLOT_COUNT,
             lambda: all(per_slot.get(s, 0) == n for s, n in problem.slots.items())),
            (Infeasible.OVER_BUDGET,
             lambda: sum(m.price_paisa for m in members) <= problem.budget_after_fee_paisa),
            (Infeasible.SKILL_COVERAGE, coverage_ok),
            (Infeasible.NEWCOMERS,
             lambda: sum(m.newcomer for m in members) >= problem.min_newcomers),
        ]  # fmt: skip
    for reason, ok in rules:
        if not ok():
            return reason
    return None


def fitness(problem: Problem, selection: Iterable[int]) -> float:
    """Eq. 17: the sum of member terms for a feasible team, −∞ otherwise (A3)."""
    chosen = sorted(set(selection))
    if infeasibility(problem, chosen) is not None:
        return NEG_INF
    return sum(problem.terms(i).total for i in chosen)


@dataclass(frozen=True)
class Breakdown:
    """Per-member contribution to a team's fitness, for "why this team" (§9.7)."""

    bid_id: str
    comp: float
    team: float
    time: float
    cost: float
    perf: float
    total: float


def breakdown(problem: Problem, selection: Sequence[int]) -> tuple[Breakdown, ...]:
    out = []
    for i in sorted(set(selection)):
        t = problem.terms(i)
        out.append(Breakdown(problem.candidates[i].bid_id, t.comp, t.team, t.time, t.cost,
                             t.perf, t.total))  # fmt: skip
    return tuple(out)


# --------------------------------------------------------------------------- presets (D115)

BALANCED = Weights(0.35, 0.25, 0.2, 0.2)
PRESET_EMPHASIS = 1.0  # weight added to the preset's own term before normalising


def preset_weights(preset: str) -> Weights:
    """The four presets (§9.2: Quality→P, Balanced→C, Fast→t, Budget→c for Algorithm 1's
    advancement). Each is Balanced plus extra weight on its own term, so its best team is never
    worse on that term than Balanced's (exchange argument, D115): Quality never less competent,
    Fast never slower, Budget never more expensive."""
    base = [BALANCED.competency, BALANCED.teamwork, BALANCED.time, BALANCED.cost]
    emphasis = {"balanced": None, "quality": 0, "fast": 2, "budget": 3}
    if preset not in emphasis:
        raise ValueError(f"unknown preset {preset!r}")
    index = emphasis[preset]
    if index is not None:
        base[index] += PRESET_EMPHASIS
    total = sum(base)
    return Weights(*(w / total for w in base))
