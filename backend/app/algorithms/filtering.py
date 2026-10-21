"""Worker filtering — Algorithm 1 ([PCS] §4.2) plus the DevSync newcomer rule (spec §9.2). PURE.

No database, web framework, network or clock access; deterministic. `services/bids.py` builds
`BidInput`s from the sealed bids and their developers' reputation snapshots (via
`services/reputation_read.py`) and calls `filter_bids`, which keeps the bids that satisfy the
paper constraints (P ≥ P0, C ≥ C0, t ≤ T^d, c ≤ C''_j), applies the newcomer rule and the
other gates, relaxes P0/C0 to find enough candidates (reporting each step), orders each slot's
survivors by the advancement choice and shortlists the top K_s, and returns every rejected bid
with a stable reason code.

Scores (P, C, P0, C0, evidence) are on 0–1. Comparisons use a tiny epsilon so a score **equal**
to the threshold passes (spec §9.2: "equal to the threshold passes"), and relaxed thresholds are
rounded to two decimals so repeated −0.05 steps stay exact (0.45 → 0.40 → 0.35 → 0.30).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

_EPS = 1e-9


def _ge(a: float, b: float) -> bool:
    """`a >= b` with an epsilon, so an exactly-equal score passes the threshold."""
    return a >= b - _EPS


class ReasonCode(enum.StrEnum):
    """Stable eligibility reason codes (spec §9.2); the service maps them to human text."""

    LOW_PERFORMANCE = "LOW_PERFORMANCE"
    LOW_COMPETENCY = "LOW_COMPETENCY"
    TOO_SLOW = "TOO_SLOW"
    OVER_BUDGET = "OVER_BUDGET"
    NO_SKILL_EVIDENCE = "NO_SKILL_EVIDENCE"
    SKILL_MISMATCH = "SKILL_MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"
    SUSPENDED = "SUSPENDED"
    SELF_DEALING = "SELF_DEALING"
    NOT_SHORTLISTED = "NOT_SHORTLISTED"


class Advancement(enum.StrEnum):
    """Advancement choice (paper line 6). Presets: Quality→P, Balanced→C, Fast→t, Budget→c."""

    P = "P"
    C = "C"
    T = "t"
    C_COST = "c"


class Mode(enum.StrEnum):
    DEVSYNC = "devsync"
    PCS_REPLICATION = "pcs_replication"


@dataclass(frozen=True)
class BidInput:
    """One bid with everything the filter needs; built by the service, never from the client."""

    bid_id: str
    slot_id: str
    skill_id: str
    developer_id: str
    is_newcomer: bool
    p: float  # performance P_i (0–1)
    c: float  # competency C_i (0–1)
    t_days: int  # days needed t_i
    c_paisa: int  # bid price c_i
    skill_evidence_score: float | None  # for the slot's skill; None if no passing evidence
    has_slot_skill: bool  # the slot's skill is in the developer's declared skills
    active: bool  # account active and not suspended
    available: bool  # availability reservation feasible (§9.17)
    self_dealing: bool  # open confirmed SELF_DEALING flag with this client


@dataclass(frozen=True)
class SlotSpec:
    skill_id: str
    count: int


@dataclass(frozen=True)
class ProjectInput:
    deadline_days: int  # T^d
    budget_after_fee_paisa: int  # C''_j
    slots: dict[str, SlotSpec]  # slot_id -> spec


@dataclass(frozen=True)
class FilterParams:
    p0: float = 0.45
    c0: float = 0.40
    advancement: Advancement = Advancement.C
    team_size: int = 2
    newcomer_pass_mark: float = 0.60
    newcomer_competency_check: bool = False
    relax_step: float = 0.05
    relax_max_steps: int = 3
    shortlist_factor: int = 3
    shortlist_min: int = 6
    mode: Mode = Mode.DEVSYNC


@dataclass(frozen=True)
class Relaxation:
    """One relaxation step, reported to the client (spec §9.2 step 4)."""

    step: int
    p0: float
    c0: float


@dataclass(frozen=True)
class FilterResult:
    eligible: tuple[str, ...]  # bid ids passing Algorithm 1
    shortlisted: dict[str, tuple[str, ...]]  # slot_id -> ordered top-K bid ids
    not_shortlisted: tuple[str, ...]  # eligible but beyond K_s (reason NOT_SHORTLISTED)
    rejected: tuple[tuple[str, ReasonCode], ...]  # (bid_id, reason) for ineligible bids
    relaxations: tuple[Relaxation, ...]
    too_few: bool  # still short after max relaxation (§9.19)
    shortfall: dict[str, int]  # slot_id -> missing eligible bids (0 when met)


# Reason precedence: a bid may fail several gates; report the first in this order so the client UI
# and the gate's documented reasons are deterministic. Account/structural gates first, then the
# newcomer/performance gate, then competency, then the project-fit limits.
_PRECEDENCE = (
    ReasonCode.SUSPENDED,
    ReasonCode.SKILL_MISMATCH,
    ReasonCode.SELF_DEALING,
    ReasonCode.UNAVAILABLE,
    ReasonCode.NO_SKILL_EVIDENCE,
    ReasonCode.LOW_PERFORMANCE,
    ReasonCode.LOW_COMPETENCY,
    ReasonCode.TOO_SLOW,
    ReasonCode.OVER_BUDGET,
)


def classify_bid(
    bid: BidInput, project: ProjectInput, params: FilterParams, p0: float, c0: float
) -> ReasonCode | None:
    """Return the first failing reason for a bid at thresholds (p0, c0), or None if eligible.

    Used by `filter_bids` and by the bid sheet's dry-run eligibility preview. The paper's P0/C0
    thresholds are the relaxable ones; everything else is a fixed gate.
    """
    newcomer = bid.is_newcomer and params.mode is Mode.DEVSYNC
    has_evidence = bid.skill_evidence_score is not None and _ge(
        bid.skill_evidence_score, params.newcomer_pass_mark
    )
    # Fixed gates, then the newcomer/performance and competency gates (the relaxable P0/C0 ones).
    # Newcomer rule (§9.2): the P0 check becomes "skill evidence ≥ pass_mark"; the C0 check applies
    # only when `newcomer_competency_check` is on (newcomer C is built from starting values).
    gates: list[tuple[bool, ReasonCode]] = [
        (not bid.active, ReasonCode.SUSPENDED),
        (not bid.has_slot_skill, ReasonCode.SKILL_MISMATCH),
        (bid.self_dealing, ReasonCode.SELF_DEALING),
        (not bid.available, ReasonCode.UNAVAILABLE),
        (newcomer and not has_evidence, ReasonCode.NO_SKILL_EVIDENCE),
        (not newcomer and not _ge(bid.p, p0), ReasonCode.LOW_PERFORMANCE),
        (
            (not newcomer or params.newcomer_competency_check) and not _ge(bid.c, c0),
            ReasonCode.LOW_COMPETENCY,
        ),
        (bid.t_days > project.deadline_days, ReasonCode.TOO_SLOW),
        (bid.c_paisa > project.budget_after_fee_paisa, ReasonCode.OVER_BUDGET),
    ]
    failures = {reason for failed, reason in gates if failed}
    return next((reason for reason in _PRECEDENCE if reason in failures), None)


def _sufficient(eligible: list[BidInput], project: ProjectInput, team_size: int) -> bool:
    if len(eligible) < team_size:
        return False
    per_slot: dict[str, int] = dict.fromkeys(project.slots, 0)
    for b in eligible:
        if b.slot_id in per_slot:
            per_slot[b.slot_id] += 1
    return all(per_slot[s] >= spec.count for s, spec in project.slots.items())


def _order_key(bid: BidInput, advancement: Advancement) -> float | int:
    """Sort key for the advancement choice: descending P/C (negated), ascending t/c. Prices stay
    integer paisa (never float, spec §0.2 rule 10)."""
    if advancement is Advancement.P:
        return -bid.p
    if advancement is Advancement.C:
        return -bid.c
    if advancement is Advancement.T:
        return bid.t_days
    return bid.c_paisa


def filter_bids(bids: list[BidInput], project: ProjectInput, params: FilterParams) -> FilterResult:
    """Run Algorithm 1 + the newcomer rule, relaxation, advancement ordering and shortlisting."""
    relax_steps = 0 if params.mode is Mode.PCS_REPLICATION else params.relax_max_steps
    relaxations: list[Relaxation] = []
    p0, c0 = params.p0, params.c0
    eligible: list[BidInput] = []

    for step in range(relax_steps + 1):
        p0 = max(0.0, round(params.p0 - step * params.relax_step, 2))
        c0 = max(0.0, round(params.c0 - step * params.relax_step, 2))
        if step > 0:
            relaxations.append(Relaxation(step=step, p0=p0, c0=c0))
        eligible = [b for b in bids if classify_bid(b, project, params, p0, c0) is None]
        if _sufficient(eligible, project, params.team_size):
            break

    # Final reasons at the thresholds we settled on.
    eligible_ids = {b.bid_id for b in eligible}
    rejected = tuple(
        (b.bid_id, reason)
        for b in bids
        if b.bid_id not in eligible_ids
        and (reason := classify_bid(b, project, params, p0, c0)) is not None
    )

    # Advancement ordering + shortlist K_s = max(3·count_s, 6) per slot (D46). Stable by bid_id.
    shortlisted: dict[str, tuple[str, ...]] = {}
    not_shortlisted: list[str] = []
    for slot_id, spec in project.slots.items():
        in_slot = sorted(
            (b for b in eligible if b.slot_id == slot_id),
            key=lambda b: (_order_key(b, params.advancement), b.bid_id),
        )
        k = max(params.shortlist_factor * spec.count, params.shortlist_min)
        shortlisted[slot_id] = tuple(b.bid_id for b in in_slot[:k])
        not_shortlisted.extend(b.bid_id for b in in_slot[k:])

    per_slot: dict[str, int] = dict.fromkeys(project.slots, 0)
    for b in eligible:
        if b.slot_id in per_slot:
            per_slot[b.slot_id] += 1
    shortfall = {s: max(0, spec.count - per_slot[s]) for s, spec in project.slots.items()}
    too_few = not _sufficient(eligible, project, params.team_size)

    return FilterResult(
        eligible=tuple(b.bid_id for b in eligible),
        shortlisted=shortlisted,
        not_shortlisted=tuple(not_shortlisted),
        rejected=rejected,
        relaxations=tuple(relaxations),
        too_few=too_few,
        shortfall=shortfall,
    )
