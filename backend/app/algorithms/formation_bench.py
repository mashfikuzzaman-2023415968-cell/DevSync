"""Seeded random formation problems for experiment E1/E2 and the optimality tests (§19). PURE.

Simulated data: candidates with competency, teamwork and performance ~ U(0.3, 0.95), 5–30 days
against a 30-day deadline, prices ৳10,000–40,000 (in paisa), about 30 % newcomers, one skill per
slot; the budget after fee is 1.6 × the cheapest possible team, so the budget binds sometimes but
not always. Each slot gets at least its count of candidates, so every instance has a feasible team
unless the newcomer minimum can't be met.
"""

from __future__ import annotations

import random

from app.algorithms.filtering import Mode
from app.algorithms.fitness import Candidate, Problem, preset_weights


def random_instance(
    seed: int,
    *,
    candidates: int | None = None,
    slots: int | None = None,
    preset: str = "balanced",
    min_newcomers: int = 1,
    mode: Mode = Mode.DEVSYNC,
) -> Problem:
    """A reproducible small problem: 8–18 candidates over 3–5 slots unless given."""
    rng = random.Random(seed)  # noqa: S311 - simulation, not security
    n_slots = slots if slots is not None else rng.randint(3, 5)
    counts = {f"s{j}": 1 for j in range(n_slots)}
    if n_slots > 3:  # noqa: PLR2004 - one slot with two places on bigger teams
        counts["s0"] = 2
    team = sum(counts.values())
    n = candidates if candidates is not None else rng.randint(max(8, team + 2), 18)
    names = list(counts)
    cands = []
    for i in range(n):
        slot = names[i % len(names)]
        cands.append(
            Candidate(
                bid_id=f"b{i:03d}",
                developer_id=f"d{i:03d}",
                slot_id=slot,
                competency=rng.uniform(0.3, 0.95),
                teamwork=rng.uniform(0.3, 0.95),
                performance=rng.uniform(0.4, 0.9),
                days=rng.randint(5, 30),
                price_paisa=rng.randint(10, 40) * 100_000,
                newcomer=rng.random() < 0.3,  # noqa: PLR2004
                skills=frozenset({slot}),
            )
        )
    cheapest = 0
    for slot, need in counts.items():
        prices = sorted(c.price_paisa for c in cands if c.slot_id == slot)
        cheapest += sum(prices[:need])
    return Problem(
        candidates=tuple(cands),
        slots=counts,
        deadline_days=30,
        budget_after_fee_paisa=int(cheapest * 1.6),
        weights=preset_weights(preset),
        min_newcomers=min_newcomers,
        required_skills=frozenset(counts),
        mode=mode,
    )
