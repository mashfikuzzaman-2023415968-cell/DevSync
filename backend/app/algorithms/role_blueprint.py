"""Role assessment blueprint builder (role assessment spec §5.1). PURE, deterministic.

A blueprint says which competencies a newcomer is assessed on for one project slot, with what
weight, how many questions of which difficulty, how long and with which pass rule. It depends
only on the project and the slot — never on the candidate — so every newcomer bidding for the
slot faces the same assessment. It is rule-based and explainable: each competency carries plain
reasons ("Core skill of this role (FastAPI)", "The requirements mention: login, roles").

Steps (numbers as in the spec):
 1. Normalise the project text (NFC, lowercase, control characters out, whitespace collapsed,
    capped at 20,000 characters).
 2. Related skills: among the milestones that include the slot's skill, the two other skills
    that appear most often (ties by name, then id).
 3. Candidates: the primary skill's competencies plus the related skills' core competencies.
    A candidate whose bank has fewer than `min_approved_per_competency` approved questions can
    never supply its share and is left out here (step 7b).
 4. Base points: 80 shared by the primary competencies, 20 by the related ones (100 when there
    are no related skills).
 5. Keyword boost: whole-word keyword hits in the text, each keyword counted at most 3 times,
    boost = min(hits, 5) × 4.
 6. Rank by score, then core first, then position, then code.
 7. Select up to 6, at least 3 from the primary skill; fewer than 4 (or 3 primary) → unavailable.
 8. Weights in basis points: proportional to score, clamped to [1,000, 4,000], rounded to
    multiples of 500, summing to exactly 10,000.
 9. Questions per competency by largest remainder (minimum 1), then the global difficulty mix
    assigned round-robin to what each competency's approved pool can supply (with one spare).
    A competency that can't supply its allocation is removed and the weights are redone (8).
 10–12. Reasons, label and a SHA-256 fingerprint of the canonical blueprint.

All arithmetic on points and weights is exact (`Fraction`), so the same input always gives the
same blueprint and fingerprint, and text that moves no weight across a 500 bp step changes
nothing.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import floor

BLUEPRINT_ALGO_VERSION = 1
MAX_TEXT = 20_000
MAX_RELATED_SKILLS = 2
MAX_COMPETENCIES = 6
MIN_COMPETENCIES = 4
MIN_PRIMARY = 3
PRIMARY_POINTS = Fraction(80)
RELATED_POINTS = Fraction(20)
KEYWORD_CAP = 3  # each keyword counts at most this often
HITS_CAP = 5  # boost = min(hits, 5) × 4
POINTS_PER_HIT = 4
TOTAL_BP = 10_000
MIN_WEIGHT_BP = 1_000
MAX_WEIGHT_BP = 4_000
WEIGHT_STEP_BP = 500
MAX_REASONS = 3
DIFFICULTIES = (1, 2, 3)  # easy, medium, hard
DIFFICULTY_NAMES = {1: "easy", 2: "medium", 3: "hard"}
# Tie order when two difficulties are needed equally: medium, then easy, then hard (§5.1 step 9).
DIFFICULTY_TIE_ORDER = (2, 1, 3)


class UnavailableReason(enum.StrEnum):
    INSUFFICIENT_COMPETENCIES = "INSUFFICIENT_COMPETENCIES"
    INSUFFICIENT_PRIMARY_COMPETENCIES = "INSUFFICIENT_PRIMARY_COMPETENCIES"


@dataclass(frozen=True)
class Competency:
    id: str
    skill_id: str
    code: str
    name: str
    is_core: bool
    keywords: tuple[str, ...]
    position: int


@dataclass(frozen=True)
class DifficultyMix:
    easy: int = 4
    medium: int = 5
    hard: int = 3

    @property
    def total(self) -> int:
        return self.easy + self.medium + self.hard

    def of(self, difficulty: int) -> int:
        return {1: self.easy, 2: self.medium, 3: self.hard}[difficulty]

    def as_dict(self) -> dict[str, int]:
        return {"easy": self.easy, "medium": self.medium, "hard": self.hard}


@dataclass(frozen=True)
class PassRule:
    overall_bp: int = 6000
    floor_bp: int = 4000
    heavy_weight_bp: int = 2000

    def as_dict(self) -> dict[str, int]:
        return {
            "overall_bp": self.overall_bp,
            "floor_bp": self.floor_bp,
            "heavy_weight_bp": self.heavy_weight_bp,
        }


@dataclass(frozen=True)
class BlueprintParams:
    question_count: int = 12
    time_limit_seconds: int = 900
    difficulty_mix: DifficultyMix = DifficultyMix()
    pass_rule: PassRule = PassRule()
    min_approved_per_competency: int = 4

    def __post_init__(self) -> None:
        if self.difficulty_mix.total != self.question_count:
            raise ValueError("the difficulty mix must add up to the question count")


@dataclass(frozen=True)
class BlueprintInput:
    primary_skill_id: str
    skill_names: Mapping[str, str]  # skill id -> name (primary and every milestone skill)
    milestones: Sequence[frozenset[str]]  # skill ids per milestone
    text: str  # title + summary + description + requirements
    catalogue: Mapping[str, Sequence[Competency]]  # skill id -> active competencies
    bank_counts: Mapping[tuple[str, int], int]  # (competency id, difficulty) -> approved count
    params: BlueprintParams = BlueprintParams()


@dataclass(frozen=True)
class BlueprintCompetency:
    competency_id: str
    skill_id: str
    code: str
    name: str
    weight_bp: int
    question_count: int
    easy: int
    medium: int
    hard: int
    reasons: tuple[str, ...]

    def of(self, difficulty: int) -> int:
        return {1: self.easy, 2: self.medium, 3: self.hard}[difficulty]


@dataclass(frozen=True)
class Blueprint:
    algo_version: int
    fingerprint: str
    primary_skill_id: str
    label: str
    competencies: tuple[BlueprintCompetency, ...]  # by weight (desc), then code
    question_count: int
    time_limit_seconds: int
    difficulty_mix: DifficultyMix
    pass_rule: PassRule


@dataclass(frozen=True)
class Unavailable:
    algo_version: int
    fingerprint: str
    primary_skill_id: str
    label: str
    reason: UnavailableReason
    time_limit_seconds: int
    pass_rule: PassRule


# ------------------------------------------------------------------------------------- text


def normalise_text(text: str) -> str:
    """NFC, lowercase, control characters removed, whitespace collapsed, capped (step 1)."""
    text = unicodedata.normalize("NFC", text).lower()
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT]


def keyword_hits(text: str, keyword: str) -> int:
    """Whole-word (phrase) matches of a keyword in normalised text, capped at 3 (step 5)."""
    kw = normalise_text(keyword)
    if not kw:
        return 0
    pattern = re.compile(r"(?<![\w])" + re.escape(kw) + r"(?![\w])")
    return min(len(pattern.findall(text)), KEYWORD_CAP)


# ---------------------------------------------------------------------------------- builder


@dataclass(frozen=True)
class _Candidate:
    competency: Competency
    primary: bool
    score: Fraction
    hits: tuple[str, ...]  # keywords found in the text, in catalogue order

    def rank_key(self) -> tuple[Fraction, int, int, str]:
        c = self.competency
        return (-self.score, 0 if c.is_core else 1, c.position, c.code)


def related_skills(primary: str, milestones: Sequence[frozenset[str]], names: Mapping[str, str]) -> list[tuple[str, int]]:
    """The (skill id, milestone count) of the top two other skills next to the primary (step 2)."""
    counts: dict[str, int] = {}
    for skills in milestones:
        if primary in skills:
            for skill in skills:
                if skill != primary:
                    counts[skill] = counts.get(skill, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], names.get(kv[0], ""), kv[0]))
    return [kv for kv in ranked if kv[1] > 0][:MAX_RELATED_SKILLS]


def _candidates(inp: BlueprintInput, related: list[tuple[str, int]], text: str) -> list[_Candidate]:
    min_total = inp.params.min_approved_per_competency
    primary = [c for c in inp.catalogue.get(inp.primary_skill_id, ())]
    others = [c for skill, _ in related for c in inp.catalogue.get(skill, ()) if c.is_core]
    pools = [(c, True) for c in primary] + [(c, False) for c in others]
    codes = [c.code for c, _ in pools]
    if len(set(codes)) != len(codes):
        raise ValueError("competency codes must be unique across the candidate skills")
    n_primary, n_related = len(primary), len(others)
    primary_points = PRIMARY_POINTS if n_related else PRIMARY_POINTS + RELATED_POINTS
    out: list[_Candidate] = []
    for c, is_primary in pools:
        if sum(inp.bank_counts.get((c.id, d), 0) for d in DIFFICULTIES) < min_total:
            continue  # this competency's bank can never supply its share (step 7b)
        base = primary_points / n_primary if is_primary else RELATED_POINTS / n_related
        found = [kw for kw in c.keywords if keyword_hits(text, kw)]
        hits = sum(keyword_hits(text, kw) for kw in c.keywords)
        boost = Fraction(min(hits, HITS_CAP) * POINTS_PER_HIT)
        out.append(_Candidate(c, is_primary, base + boost, tuple(found)))
    return sorted(out, key=_Candidate.rank_key)


def _select(ranked: list[_Candidate]) -> list[_Candidate]:
    """Top six, swapping the lowest related ones for primary ones until three are primary (7a)."""
    chosen = ranked[:MAX_COMPETENCIES]
    spare_primary = [c for c in ranked[MAX_COMPETENCIES:] if c.primary]
    while sum(c.primary for c in chosen) < MIN_PRIMARY and spare_primary:
        lowest_related = max(
            (i for i, c in enumerate(chosen) if not c.primary), default=None
        )
        if lowest_related is None:
            break
        chosen[lowest_related] = spare_primary.pop(0)
        chosen.sort(key=_Candidate.rank_key)
    return chosen


def _round_half_up(value: Fraction, step: int) -> int:
    return floor(value / step + Fraction(1, 2)) * step


def weights_bp(chosen: Sequence[_Candidate]) -> dict[str, int] | None:
    """Step 8: proportional, clamped to [1,000, 4,000], rounded to 500, summing to 10,000.

    Returns None when no valid set exists (every weight at the 4,000 cap and still short).
    """
    scores = {c.competency.code: c.score for c in chosen}
    fixed: dict[str, Fraction] = {}
    while True:  # iterative clamping (water-filling) on exact fractions
        free = {k: v for k, v in scores.items() if k not in fixed}
        if not free:
            break
        room = TOTAL_BP - sum(fixed.values())
        total = sum(free.values())
        share = {k: room * v / total for k, v in free.items()}
        clamped = {
            k: Fraction(MAX_WEIGHT_BP) if w > MAX_WEIGHT_BP else Fraction(MIN_WEIGHT_BP)
            for k, w in share.items()
            if w > MAX_WEIGHT_BP or w < MIN_WEIGHT_BP
        }
        if not clamped:
            fixed.update(share)
            break
        fixed.update(clamped)
    weights = {k: _round_half_up(w, WEIGHT_STEP_BP) for k, w in fixed.items()}
    order = sorted(weights, key=lambda k: (-weights[k], k))  # largest first, ties by code
    diff = TOTAL_BP - sum(weights.values())
    if diff > 0:
        largest = order[0]
        weights[largest] += diff
        excess = max(0, weights[largest] - MAX_WEIGHT_BP)
        weights[largest] -= excess
        while excess > 0:
            below = [k for k in sorted(weights, key=lambda k: (-weights[k], k)) if weights[k] < MAX_WEIGHT_BP]
            if not below:
                return None
            weights[below[0]] += WEIGHT_STEP_BP
            excess -= WEIGHT_STEP_BP
    elif diff < 0:
        deficit = -diff
        while deficit > 0:
            above = [k for k in sorted(weights, key=lambda k: (-weights[k], k)) if weights[k] > MIN_WEIGHT_BP]
            if not above:
                return None
            take = min(deficit, weights[above[0]] - MIN_WEIGHT_BP)
            weights[above[0]] -= take
            deficit -= take
    return weights


def allocate_questions(weights: Mapping[str, int], question_count: int) -> dict[str, int]:
    """Largest remainder over the weights, minimum one question each (step 9)."""
    quotas = {k: Fraction(question_count * w, TOTAL_BP) for k, w in weights.items()}
    counts = {k: max(1, floor(q)) for k, q in quotas.items()}
    remainder = {k: quotas[k] - floor(quotas[k]) for k in quotas}
    by_remainder = sorted(weights, key=lambda k: (-remainder[k], -weights[k], k))
    i = 0
    while sum(counts.values()) < question_count:
        counts[by_remainder[i % len(by_remainder)]] += 1
        i += 1
    while sum(counts.values()) > question_count:  # the minimum-one rule overshot
        victims = sorted(
            (k for k in counts if counts[k] > 1), key=lambda k: (remainder[k], weights[k], k)
        )
        counts[victims[0]] -= 1
    return counts


def assign_difficulties(
    order: Sequence[str],
    counts: Mapping[str, int],
    pools: Mapping[str, Mapping[int, int]],
    mix: DifficultyMix,
) -> dict[str, dict[int, int]] | str:
    """Give each question slot a difficulty (step 9); returns the code that can't be supplied.

    Competencies are walked in weight order, round-robin, one slot at a time. Each slot gets the
    difficulty with the highest remaining global need that the competency's approved pool can
    supply with one spare (count ≥ already assigned + 2); ties medium, easy, hard.
    """
    need = {d: mix.of(d) for d in DIFFICULTIES}
    assigned: dict[str, dict[int, int]] = {k: dict.fromkeys(DIFFICULTIES, 0) for k in order}
    remaining = dict(counts)
    while any(remaining[k] > 0 for k in order):
        for code in order:
            if remaining[code] == 0:
                continue
            options = [
                d
                for d in DIFFICULTY_TIE_ORDER
                if need[d] > 0 and pools[code].get(d, 0) >= assigned[code][d] + 2
            ]
            if not options:
                return code
            best = max(options, key=lambda d: (need[d], -DIFFICULTY_TIE_ORDER.index(d)))
            assigned[code][best] += 1
            need[best] -= 1
            remaining[code] -= 1
    return assigned


def _reasons(cand: _Candidate, primary_name: str, related_counts: Mapping[str, int], names: Mapping[str, str]) -> tuple[str, ...]:
    c = cand.competency
    reasons: list[str] = []
    if cand.primary:
        reasons.append(
            f"Core skill of this role ({primary_name})" if c.is_core
            else f"Part of this role's skill ({primary_name})"
        )  # fmt: skip
    else:
        n = related_counts[c.skill_id]
        skill = names.get(c.skill_id, "This skill")
        reasons.append(f"{skill} is needed in {n} milestone{'s' if n != 1 else ''} of this role")
    if cand.hits:
        reasons.append("The requirements mention: " + ", ".join(cand.hits[:MAX_REASONS]))
    return tuple(reasons[:MAX_REASONS])


def fingerprint(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _unavailable(inp: BlueprintInput, reason: UnavailableReason) -> Unavailable:
    p = inp.params
    name = inp.skill_names.get(inp.primary_skill_id, "")
    payload = {
        "algo_version": BLUEPRINT_ALGO_VERSION,
        "primary_skill_id": inp.primary_skill_id,
        "unavailable": reason.value,
        "time_limit_seconds": p.time_limit_seconds,
        "pass_rule": p.pass_rule.as_dict(),
    }
    return Unavailable(
        BLUEPRINT_ALGO_VERSION, fingerprint(payload), inp.primary_skill_id,
        f"{name} · role assessment not available yet", reason, p.time_limit_seconds, p.pass_rule,
    )  # fmt: skip


def build_blueprint(inp: BlueprintInput) -> Blueprint | Unavailable:
    p = inp.params
    names = inp.skill_names
    primary_name = names.get(inp.primary_skill_id, "")
    text = normalise_text(inp.text)
    related = related_skills(inp.primary_skill_id, inp.milestones, names)
    related_counts = dict(related)
    chosen = _select(_candidates(inp, related, text))
    while True:
        if len(chosen) < MIN_COMPETENCIES:
            return _unavailable(inp, UnavailableReason.INSUFFICIENT_COMPETENCIES)
        if sum(c.primary for c in chosen) < MIN_PRIMARY:
            return _unavailable(inp, UnavailableReason.INSUFFICIENT_PRIMARY_COMPETENCIES)
        weights = weights_bp(chosen)
        if weights is None:  # every weight capped: drop the lowest-ranked competency, retry
            chosen = chosen[:-1]
            continue
        order = sorted(weights, key=lambda k: (-weights[k], k))
        counts = allocate_questions(weights, p.question_count)
        by_code = {c.competency.code: c for c in chosen}
        pools = {
            k: {d: inp.bank_counts.get((by_code[k].competency.id, d), 0) for d in DIFFICULTIES}
            for k in order
        }
        assigned = assign_difficulties(order, counts, pools, p.difficulty_mix)
        if isinstance(assigned, str):  # this competency can't supply its share: remove, redo 8
            chosen = [c for c in chosen if c.competency.code != assigned]
            continue
        break
    comps = tuple(
        BlueprintCompetency(
            competency_id=by_code[k].competency.id,
            skill_id=by_code[k].competency.skill_id,
            code=k,
            name=by_code[k].competency.name,
            weight_bp=weights[k],
            question_count=counts[k],
            easy=assigned[k][1],
            medium=assigned[k][2],
            hard=assigned[k][3],
            reasons=_reasons(by_code[k], primary_name, related_counts, names),
        )
        for k in order
    )
    label = f"{primary_name} · " + ", ".join(c.name for c in comps[:3])
    payload = {
        "algo_version": BLUEPRINT_ALGO_VERSION,
        "primary_skill_id": inp.primary_skill_id,
        "competencies": [
            [c.code, c.weight_bp, c.question_count, {"easy": c.easy, "medium": c.medium, "hard": c.hard}]
            for c in sorted(comps, key=lambda c: c.code)
        ],
        "time_limit_seconds": p.time_limit_seconds,
        "pass_rule": p.pass_rule.as_dict(),
    }
    return Blueprint(
        algo_version=BLUEPRINT_ALGO_VERSION,
        fingerprint=fingerprint(payload),
        primary_skill_id=inp.primary_skill_id,
        label=label,
        competencies=comps,
        question_count=p.question_count,
        time_limit_seconds=p.time_limit_seconds,
        difficulty_mix=p.difficulty_mix,
        pass_rule=p.pass_rule,
    )
