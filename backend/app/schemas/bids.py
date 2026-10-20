"""Request/response schemas for sealed bids and the eligibility preview (spec §7.4, §10 Bids).

Request bodies extend `StrictRequest` (unknown fields rejected, §14.5); the server sets
`developer_id`, `status` and `ineligible_reasons`. A developer's own `BidOut` includes their price
and proposal; the client's `ClientBidOut` adds the developer's reputation and the Algorithm 1
eligibility verdict. Other developers never receive either (sealed bids, §14.5). Money is paisa.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
    """One Algorithm 1 constraint and whether the draft bid meets it."""

    name: str
    ok: bool
    detail: str


class EligibilityOut(BaseModel):
    """The dry-run eligibility verdict for the bid sheet's live preview."""

    eligible: bool
    reason: str | None  # the first failing reason code, or null when eligible
    message: str  # human text, e.g. "Would be filtered out: needs 31 days (deadline 30)"
    checks: list[ConstraintCheck]


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
    competency: float  # C ×100 is shown in the UI
    performance: float  # P
    is_newcomer: bool
    seeded: bool  # reputation value is seeded (dev-only marker)
    eligible: bool
    reasons: list[str]  # reason codes when not eligible or not shortlisted


class SlotCoverage(BaseModel):
    slot_id: uuid.UUID
    slot_label: str
    needed: int
    eligible: int


class RelaxationOut(BaseModel):
    step: int
    p0: float
    c0: float


class ClientBidsOut(BaseModel):
    """The client's bids view for a project: all bids + coverage + relaxations + too-few flag."""

    bids: list[ClientBidOut]
    coverage: list[SlotCoverage]
    relaxations: list[RelaxationOut]
    too_few: bool
