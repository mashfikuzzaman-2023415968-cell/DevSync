"""Team lead recommendation (spec §1.6 rule 1; DECISIONS D131, D132). PURE.

The system recommends; the client chooses. Among the team's ACTIVE members who haven't declined
the lead role on this project (and aren't excluded, e.g. the outgoing lead of an approved change
request), the recommendation is the member with the highest teamwork capacity X_m, ties broken by
more completed projects, then higher competency C, then the earlier acceptance, then the developer
id (a final deterministic key). Values are read through `services/reputation_read.py`, so a
newcomer is ranked on the computed starting values like everyone else.

The reason reads "Highest teamwork capacity: 86; led 2 past teams" — values 0–100 (§13.8), the
"led" clause omitted while it is 0. When someone with a higher X_m was skipped (declined the role
or excluded), it says "of the members available".
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class LeadCandidate:
    member_id: str
    developer_id: str
    active: bool  # status ACTIVE (accepted)
    xm: float  # teamwork capacity X_m, 0–1
    completed_projects: int
    competency: float  # C, 0–1
    responded_at: datetime | None  # when they accepted (earlier wins a tie)
    declined_lead: bool = False  # declined the lead role on this project
    led_teams: int = 0  # completed teams where they were the active lead


@dataclass(frozen=True)
class LeadRecommendation:
    member_id: str
    developer_id: str
    reason: str
    ranking: tuple[str, ...]  # eligible member ids, best first


def score100(value: float) -> int:
    """0–1 → 0–100, half up (as the UI shows scores)."""
    clamped = min(1.0, max(0.0, value))
    return int(Decimal(repr(clamped * 100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _key(c: LeadCandidate) -> tuple[float, int, float, float, str]:
    # None (shouldn't happen for an ACTIVE member) sorts after every real acceptance time.
    when = c.responded_at.timestamp() if c.responded_at is not None else float("inf")
    return (-c.xm, -c.completed_projects, -c.competency, when, c.developer_id)


def rank(members: Iterable[LeadCandidate], exclude: Iterable[str] = ()) -> list[LeadCandidate]:
    """Eligible members (ACTIVE, not declined, not excluded), best first."""
    skip = set(exclude)
    eligible = [m for m in members if m.active and not m.declined_lead and m.member_id not in skip]
    return sorted(eligible, key=_key)


def reason(chosen: LeadCandidate, *, skipped_higher: bool = False) -> str:
    where = " of the members available" if skipped_higher else ""
    text = f"Highest teamwork capacity{where}: {score100(chosen.xm)}"
    if chosen.led_teams > 0:
        teams = "team" if chosen.led_teams == 1 else "teams"
        text += f"; led {chosen.led_teams} past {teams}"
    return text


def recommend_lead(
    members: Sequence[LeadCandidate], exclude: Iterable[str] = ()
) -> LeadRecommendation | None:
    """The recommended lead, or None when no ACTIVE member is eligible."""
    excluded = set(exclude)
    ranked = rank(members, excluded)
    if not ranked:
        return None
    best = ranked[0]
    skipped = any(
        m.active and (m.declined_lead or m.member_id in excluded) and m.xm > best.xm
        for m in members
    )
    return LeadRecommendation(
        member_id=best.member_id,
        developer_id=best.developer_id,
        reason=reason(best, skipped_higher=skipped),
        ranking=tuple(m.member_id for m in ranked),
    )
