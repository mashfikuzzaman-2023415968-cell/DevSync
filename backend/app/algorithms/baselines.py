"""The greedy baseline team (experiment E3's baseline, spec §19; §17 Phase 7 test 11). PURE.

"Top (C + P) within budget and slots": fill each slot with its highest-ranked candidates by
competency + performance (ties by index), skipping a candidate when taking them would make the
team's cheapest possible completion exceed the budget. No newcomer minimum, no weights: this is
what a client picking the "best-rated" people would do, and what DevSync is compared against.
"""

from __future__ import annotations

from app.algorithms.fitness import Problem


def greedy_team(problem: Problem) -> tuple[int, ...]:
    """The greedy team, or () when no team fits the budget this way."""
    by_slot: dict[str, list[int]] = {s: [] for s in problem.slots}
    for i, c in enumerate(problem.candidates):
        by_slot[c.slot_id].append(i)
    for members in by_slot.values():
        members.sort(key=lambda i: (-(problem.candidates[i].competency
                                      + problem.candidates[i].performance), i))  # fmt: skip

    def cheapest_rest(start_slot: int, taken: set[int]) -> int:
        total = 0
        for slot in list(problem.slots)[start_slot:]:
            prices = sorted(problem.candidates[i].price_paisa for i in by_slot[slot]
                            if i not in taken)  # fmt: skip
            total += sum(prices[: problem.slots[slot]])
        return total

    team: list[int] = []
    spent = 0
    slots = list(problem.slots)
    for pos, slot in enumerate(slots):
        need = problem.slots[slot]
        picked = 0
        for i in by_slot[slot]:
            if picked == need:
                break
            price = problem.candidates[i].price_paisa
            rest_of_slot = sorted(problem.candidates[j].price_paisa for j in by_slot[slot]
                                  if j != i and j not in team)[: need - picked - 1]  # fmt: skip
            later = cheapest_rest(pos + 1, set(team) | {i})
            if spent + price + sum(rest_of_slot) + later <= problem.budget_after_fee_paisa:
                team.append(i)
                spent += price
                picked += 1
        if picked < need:
            return ()
    return tuple(sorted(team))
