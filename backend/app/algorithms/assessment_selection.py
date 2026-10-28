"""Question selection for a role assessment attempt (role assessment spec §5.2). PURE.

Given a blueprint's allocation (questions per competency and difficulty), the approved pool
(ids, competency, difficulty and how often each was served — never text or answers), the
questions this candidate saw in the last 180 days and a seed, pick and order the attempt's
questions:

1. per competency and difficulty, prefer questions the candidate hasn't seen recently; fall back
   to seen ones only when nothing else is left (the attempt records `reused_seen`);
2. among the preferred ones take the 5 served least often and pick one at random (seeded
   "randomesque" exposure control);
3. never the same question twice;
4. order: walk the pattern medium, easy, hard, taking each time the next competency in a
   weight-ordered queue that still has a question of that difficulty, and moving it to the back
   — so the attempt opens with a medium question and alternates competencies.

Raises `SelectionUnavailable` when the pool can no longer supply the allocation (questions were
retired, or the human-review switch narrowed the pool); the slot then falls back (§5.4).
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

EXPOSURE_WINDOW = 5  # pick among the 5 least-served questions
ORDER_PATTERN = (2, 1, 3)  # medium, easy, hard


class SelectionUnavailable(Exception):
    """The current pool can't supply the blueprint's allocation."""


@dataclass(frozen=True)
class PoolQuestion:
    question_id: str
    competency_id: str
    difficulty: int
    times_served: int


@dataclass(frozen=True)
class Allocation:
    competency_id: str
    code: str
    weight_bp: int
    easy: int
    medium: int
    hard: int

    def of(self, difficulty: int) -> int:
        return {1: self.easy, 2: self.medium, 3: self.hard}[difficulty]


@dataclass(frozen=True)
class Selection:
    question_ids: tuple[str, ...]
    reused_seen: bool


def _queue_order(allocations: Sequence[Allocation]) -> list[Allocation]:
    return sorted(allocations, key=lambda a: (-a.weight_bp, a.code))


def select_questions(
    allocations: Sequence[Allocation],
    pool: Iterable[PoolQuestion],
    recently_seen: frozenset[str],
    seed: int,
) -> Selection:
    rng = random.Random(seed)  # noqa: S311 - exposure control, not security
    pool = list(pool)
    chosen: set[str] = set()
    picked: dict[tuple[str, int], list[str]] = {}
    reused = False
    for a in _queue_order(allocations):
        for difficulty in (1, 2, 3):
            eligible = sorted(
                (q for q in pool if q.competency_id == a.competency_id and q.difficulty == difficulty),
                key=lambda q: (q.times_served, q.question_id),
            )
            for _ in range(a.of(difficulty)):
                left = [q for q in eligible if q.question_id not in chosen]
                fresh = [q for q in left if q.question_id not in recently_seen]
                candidates = fresh or left
                if not candidates:
                    raise SelectionUnavailable(f"{a.code}: no {difficulty} question left")
                if not fresh:
                    reused = True
                q = rng.choice(candidates[:EXPOSURE_WINDOW])
                chosen.add(q.question_id)
                picked.setdefault((a.competency_id, difficulty), []).append(q.question_id)
    return Selection(order_questions(allocations, picked), reused)


def order_questions(
    allocations: Sequence[Allocation], picked: dict[tuple[str, int], list[str]]
) -> tuple[str, ...]:
    """Deterministic order of the chosen questions (§5.2 step 5)."""
    remaining = {k: list(v) for k, v in picked.items()}
    queue = [a.competency_id for a in _queue_order(allocations)]
    total = sum(len(v) for v in remaining.values())
    out: list[str] = []
    step = 0
    while len(out) < total:
        difficulty = ORDER_PATTERN[step % len(ORDER_PATTERN)]
        step += 1
        for i, competency in enumerate(queue):
            bucket = remaining.get((competency, difficulty))
            if bucket:
                out.append(bucket.pop(0))
                queue.append(queue.pop(i))
                break
    return tuple(out)
