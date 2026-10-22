"""Request/response schemas for sealed bids and the eligibility preview (spec §7.4, §10 Bids).

Request bodies extend `StrictRequest` (unknown fields rejected, §14.5); the server sets
`developer_id`, `status` and `ineligible_reasons`. A developer's own `BidOut` includes their price
and proposal; the client's `ClientBidOut` adds the developer's reputation and the Algorithm 1
eligibility verdict. Other developers never receive either (sealed bids, §14.5). Money is paisa.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import StrictRequest

Price = Field(gt=0, le=10_000_000_000, description="Bid price in paisa")
Days = Field(ge=1, le=365)
Proposal = Field(default="", max_length=3000)
Contribution = Field(default="", max_length=500)
Hours = Field(default=None, ge=1, le=168)


class BidCreate(StrictRequest):
    """Place a sealed bid on one slot (spec §7.4). Allowed only while the project is BIDDING."""

    slot_id: uuid.UUID
    price_paisa: int = Price
    days_needed: int = Days
    proposal: str = Proposal
    expected_contribution: str = Contribution
    portfolio_item_ids: list[uuid.UUID] = Field(default_factory=list, max_length=3)
    # Defaults server-side to min(20, profile hours) when omitted (§9.17).
    hours_per_week_committed: int | None = Hours


class BidUpdate(StrictRequest):
    """Edit an ACTIVE bid (all fields optional); allowed only while the project is BIDDING."""

    slot_id: uuid.UUID | None = None
    price_paisa: int | None = Field(default=None, gt=0, le=10_000_000_000)
    days_needed: int | None = Field(default=None, ge=1, le=365)
    proposal: str | None = Field(default=None, max_length=3000)
    expected_contribution: str | None = Field(default=None, max_length=500)
    portfolio_item_ids: list[uuid.UUID] | None = Field(default=None, max_length=3)
    hours_per_week_committed: int | None = Field(default=None, ge=1, le=168)


class BidOut(BaseModel):
    """A developer's own bid."""

    id: uuid.UUID
    project_id: uuid.UUID
    slot_id: uuid.UUID
    status: str
    price_paisa: int
    days_needed: int
    proposal: str
    expected_contribution: str
    portfolio_item_ids: list[uuid.UUID]
    hours_per_week_committed: int
    created_at: datetime
    updated_at: datetime


class EligibilityIn(StrictRequest):
    """A draft bid to check against Algorithm 1 without saving (bid sheet preview, D45)."""

    slot_id: uuid.UUID
    price_paisa: int = Price
    days_needed: int = Days
    hours_per_week_committed: int | None = Hours


class ConstraintCheck(BaseModel):
    """One Algorithm 1 check and whether the bid meets it (§9.2), with the values compared.

    `required`/`actual` are on the check's own scale: scores 0–1 (shown ×100), days, or paisa;
    null for yes/no gates. `detail` is ready-to-show text.
    """

    name: str
    ok: bool
    detail: str
    required: float | None = None
    actual: float | None = None


class EligibilityOut(BaseModel):
    """The dry-run eligibility verdict for the bid sheet's live preview."""

    eligible: bool
    reason: str | None  # the first failing reason code, or null when eligible
    message: str  # human text, e.g. "Would be filtered out: needs 31 days (deadline 30)"
    checks: list[ConstraintCheck]


class PortfolioRef(BaseModel):
    """A portfolio item attached to a bid (title only)."""

    id: uuid.UUID
    title: str


class NewcomerEvidence(BaseModel):
    """The skill test that lets a newcomer through the newcomer rule (§9.2 step 2)."""

    skill: str
    score: float  # 0–1, shown as a percentage


class ClientBidOut(BaseModel):
    """A bid as its project's client sees it: reputation + the eligibility verdict (§9.2)."""

    id: uuid.UUID
    developer_id: uuid.UUID
    developer_name: str
    slot_id: uuid.UUID
    slot_label: str
    status: str
    price_paisa: int
    days_needed: int
    hours_per_week: int
    competency: float  # C ×100 is shown in the UI
    teamwork: float  # X_m (team quality), 0–1
    performance: float  # P
    is_newcomer: bool
    seeded: bool  # reputation value is seeded (dev-only marker)
    eligible: bool
    shortlisted: bool
    reasons: list[str]  # reason codes when not eligible or not shortlisted
    checks: list[ConstraintCheck]  # Algorithm 1 trace at the thresholds used
    newcomer_evidence: NewcomerEvidence | None
    proposal: str
    expected_contribution: str
    portfolio: list[PortfolioRef]
    submitted_at: datetime


class SlotCoverage(BaseModel):
    slot_id: uuid.UUID
    slot_label: str
    needed: int
    eligible: int


class RelaxationOut(BaseModel):
    step: int
    p0: float
    c0: float


class Thresholds(BaseModel):
    """Minimum standards: the project's own, the platform default, the floor and the values
    finally used after automatic relaxation (all 0–1)."""

    p0: float
    c0: float
    default_p0: float
    default_c0: float
    floor_p0: float
    floor_c0: float
    used_p0: float
    used_c0: float


class TeamCostOut(BaseModel):
    """Cheapest eligible way to fill every slot, against the budget after the platform fee."""

    total_paisa: int
    budget_after_fee_paisa: int
    complete: bool


class BiddingWindow(BaseModel):
    deadline: datetime | None
    closed: bool
    extensions_used: int
    max_extensions: int
    extend_days: int


class ClientBidsOut(BaseModel):
    """The client's bids view for a project: all bids + coverage + relaxations + too-few flag."""

    bids: list[ClientBidOut]
    coverage: list[SlotCoverage]
    relaxations: list[RelaxationOut]
    too_few: bool
    evaluated_at: datetime
    thresholds: Thresholds
    team_cost: TeamCostOut
    budget_paisa: int
    team_size: int
    bidding: BiddingWindow


# --------------------------------------------------------------------------- too-few-bids actions


class SlotCount(StrictRequest):
    slot_id: uuid.UUID
    count: int = Field(ge=1, le=10)


class TermsChange(StrictRequest):
    """Change a BIDDING project's terms (spec §9.19): lower the standards, raise the budget or
    reduce the team. Omitted fields stay as they are; at least one must change."""

    min_performance: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=2)
    min_competency: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=2)
    budget_paisa: int | None = Field(default=None, gt=0, le=10_000_000_000)
    slot_counts: list[SlotCount] | None = Field(default=None, min_length=1, max_length=10)


class TermsOutcome(BaseModel):
    eligible: int
    too_few: bool
    coverage: list[SlotCoverage]
    team_cost: TeamCostOut


class TermsPreviewOut(BaseModel):
    """What a terms change would do to the eligible set before the client confirms it."""

    before: TermsOutcome
    after: TermsOutcome
    newly_eligible: int
    message: str
