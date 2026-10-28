"""Role assessment scoring (role assessment spec §5.3). PURE, integers only.

The Python reference of the formula that `score_role_attempt` runs in SQL; both are checked
against the shared vectors in `tests/fixtures/assessment_scoring_vectors.json`.

- Each question is worth its difficulty weight: easy 2, medium 3, hard 4. Unanswered (skipped
  or out of time) counts as wrong.
- Per competency: `score_bp = floor(10000 × earned / possible)`.
- Overall: `overall_bp = floor(Σ weight_bp × score_bp / 10000)`.
- Pass ⇔ `overall_bp ≥ overall pass mark` and every competency weighing at least the heavy
  weight scores at least the floor. Both comparisons are inclusive.
- A terminated (two-leave rule) or voided attempt never passes, whatever the score.
- Evidence score (0–1, three decimals) = `overall_bp / 10000` rounded down.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

DIFFICULTY_WEIGHT = {1: 2, 2: 3, 3: 4}
TOTAL_BP = 10_000


@dataclass(frozen=True)
class ScoredCompetency:
    competency_id: str
    code: str
    name: str
    weight_bp: int


@dataclass(frozen=True)
class AnsweredQuestion:
    competency_id: str
    difficulty: int
    correct: bool  # False when wrong, skipped or unanswered


@dataclass(frozen=True)
class CompetencyScore:
    competency_id: str
    code: str
    name: str
    weight_bp: int
    earned_w: int
    possible_w: int
    score_bp: int


@dataclass(frozen=True)
class AssessmentScore:
    breakdown: tuple[CompetencyScore, ...]
    overall_bp: int
    passed: bool
    score: Decimal  # evidence score, 0.000–1.000

    @property
    def strongest(self) -> CompetencyScore:
        return min(self.breakdown, key=lambda c: (-c.score_bp, -c.weight_bp, c.code))

    @property
    def weakest(self) -> CompetencyScore:
        return min(self.breakdown, key=lambda c: (c.score_bp, -c.weight_bp, c.code))


def evidence_score(overall_bp: int) -> Decimal:
    """`overall_bp / 10000` rounded down to three decimals."""
    return Decimal(overall_bp // 10) / Decimal(1000)


def score_attempt(
    competencies: Sequence[ScoredCompetency],
    answers: Sequence[AnsweredQuestion],
    *,
    pass_overall_bp: int,
    floor_bp: int,
    heavy_weight_bp: int,
    ended_early: bool = False,
) -> AssessmentScore:
    breakdown: list[CompetencyScore] = []
    for c in competencies:
        mine = [a for a in answers if a.competency_id == c.competency_id]
        possible = sum(DIFFICULTY_WEIGHT[a.difficulty] for a in mine)
        earned = sum(DIFFICULTY_WEIGHT[a.difficulty] for a in mine if a.correct)
        score_bp = (TOTAL_BP * earned) // possible if possible else 0
        breakdown.append(
            CompetencyScore(
                c.competency_id, c.code, c.name, c.weight_bp, earned, possible, score_bp
            )
        )
    overall_bp = sum(c.weight_bp * c.score_bp for c in breakdown) // TOTAL_BP
    heavy_ok = all(c.score_bp >= floor_bp for c in breakdown if c.weight_bp >= heavy_weight_bp)
    passed = not ended_early and overall_bp >= pass_overall_bp and heavy_ok
    return AssessmentScore(tuple(breakdown), overall_bp, passed, evidence_score(overall_bp))
