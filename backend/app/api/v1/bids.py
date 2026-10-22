"""Sealed bids (spec §10 Bids). Developers bid; a project's client sees all its bids.

Sealed: a developer only ever reads their own bids; another developer's bid is 404 (enforced in
the service and by RLS). Bids may be placed or edited only while the project is BIDDING (409
INVALID_STATE otherwise). Every operation declares its error responses and an example (§10.4).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from app.api.deps import acting, rate_limit
from app.schemas.bids import (
    BidCreate,
    BidOut,
    BidUpdate,
    ClientBidsOut,
    EligibilityIn,
    EligibilityOut,
    TermsChange,
    TermsPreviewOut,
)
from app.schemas.common import error_responses
from app.services import bidding_terms
from app.services import bids as svc
from app.services.context import Ctx

router = APIRouter(tags=["bids"])

Bidder = Annotated[Ctx, Depends(acting("bid.create"))]
Writer = Annotated[Ctx, Depends(acting("bid.write"))]
Reader = Annotated[Ctx, Depends(acting("bid.read"))]
ClientViewer = Annotated[Ctx, Depends(acting("bid.view"))]
TermsWriter = Annotated[Ctx, Depends(acting("project.terms"))]
IfMatch = Annotated[int | None, Header(alias="If-Match", description="Project version")]
BID_LIMIT = [Depends(rate_limit("bid"))]

_BID_ID = "9c8b7a6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
_SLOT = "0b7d4c1e-2f3a-4b5c-8d9e-0f1a2b3c4d5e"

EX_BID = {
    "id": _BID_ID,
    "project_id": "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c",
    "project_title": "Online ordering system",
    "slot_id": _SLOT,
    "slot_label": "React developer",
    "status": "ACTIVE",
    "price_paisa": 1_800_000,
    "days_needed": 20,
    "proposal": "I'll build the React front end with tests.",
    "expected_contribution": "Front-end components and integration.",
    "portfolio_item_ids": [],
    "hours_per_week_committed": 20,
    "created_at": "2026-10-21T06:00:00Z",
    "updated_at": "2026-10-21T06:00:00Z",
}
EX_ELIGIBILITY = {
    "eligible": False,
    "reason": "TOO_SLOW",
    "message": "Would be filtered out: needs more days than the deadline allows.",
    "checks": [
        {
            "name": "days",
            "ok": False,
            "detail": "31 days (deadline 30 days)",
            "required": 30,
            "actual": 31,
        }
    ],
}
_COVERAGE = [{"slot_id": _SLOT, "slot_label": "React developer", "needed": 1, "eligible": 1}]
_COST = {"total_paisa": 1_800_000, "budget_after_fee_paisa": 11_400_000, "complete": True}
EX_CLIENT_BIDS = {
    "bids": [
        {
            "id": _BID_ID,
            "developer_id": "22222222-2222-4222-8222-222222222222",
            "developer_name": "Nadia Rahman",
            "slot_id": _SLOT,
            "slot_label": "React developer",
            "status": "ACTIVE",
            "price_paisa": 1_800_000,
            "days_needed": 20,
            "hours_per_week": 20,
            "competency": 0.31,
            "teamwork": 0.50,
            "performance": 0.55,
            "is_newcomer": True,
            "seeded": False,
            "eligible": True,
            "shortlisted": True,
            "reasons": [],
            "checks": [
                {
                    "name": "skill_evidence",
                    "ok": True,
                    "detail": "React test 85% (newcomers need 60%)",
                    "required": 0.6,
                    "actual": 0.85,
                }
            ],
            "newcomer_evidence": {"skill": "React", "score": 0.85},
            "proposal": "I'll build the React front end with tests.",
            "expected_contribution": "Front-end components and integration.",
            "portfolio": [],
            "submitted_at": "2026-10-21T06:00:00Z",
        }
    ],
    "coverage": _COVERAGE,
    "relaxations": [],
    "too_few": False,
    "evaluated_at": "2026-10-22T06:00:00Z",
    "thresholds": {
        "p0": 0.45,
        "c0": 0.40,
        "default_p0": 0.45,
        "default_c0": 0.40,
        "floor_p0": 0.30,
        "floor_c0": 0.25,
        "used_p0": 0.45,
        "used_c0": 0.40,
    },
    "team_cost": _COST,
    "budget_paisa": 12_000_000,
    "team_size": 1,
    "bidding": {
        "deadline": "2026-10-25T06:00:00Z",
        "closed": False,
        "extensions_used": 0,
        "max_extensions": 2,
        "extend_days": 3,
    },
}
EX_TERMS_PREVIEW = {
    "before": {"eligible": 9, "too_few": True, "coverage": _COVERAGE, "team_cost": _COST},
    "after": {"eligible": 11, "too_few": False, "coverage": _COVERAGE, "team_cost": _COST},
    "newly_eligible": 2,
    "message": "2 more bids would be eligible; every slot would be covered.",
}


def _ok(example: object) -> dict[str, object]:
    return {"content": {"application/json": {"example": example}}}


@router.post(
    "/projects/{project_id}/bids",
    status_code=status.HTTP_201_CREATED,
    summary="Place a sealed bid",
    response_model=BidOut,
    responses={201: _ok(EX_BID), **error_responses(401, 403, 404, 409, 422, 429)},
    dependencies=BID_LIMIT,
)
async def create_bid(ctx: Bidder, project_id: uuid.UUID, body: BidCreate) -> BidOut:
    return await svc.create_bid(ctx, project_id, body)


@router.post(
    "/projects/{project_id}/bids/eligibility",
    summary="Preview a draft bid's eligibility",
    response_model=EligibilityOut,
    responses={200: _ok(EX_ELIGIBILITY), **error_responses(401, 403, 404, 409, 422)},
)
async def preview_eligibility(
    ctx: Bidder, project_id: uuid.UUID, body: EligibilityIn
) -> EligibilityOut:
    return await svc.eligibility_preview(ctx, project_id, body)


@router.get(
    "/me/bids",
    summary="My bids",
    response_model=list[BidOut],
    responses={200: _ok([EX_BID]), **error_responses(401, 403, 404)},
)
async def my_bids(ctx: Reader) -> list[BidOut]:
    return await svc.my_bids(ctx)


@router.patch(
    "/bids/{bid_id}",
    summary="Edit my bid",
    response_model=BidOut,
    responses={200: _ok(EX_BID), **error_responses(401, 403, 404, 409, 422, 429)},
    dependencies=BID_LIMIT,
)
async def update_bid(ctx: Writer, bid_id: uuid.UUID, body: BidUpdate) -> BidOut:
    return await svc.update_bid(ctx, bid_id, body)


@router.delete(
    "/bids/{bid_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw my bid",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def withdraw_bid(ctx: Writer, bid_id: uuid.UUID) -> Response:
    await svc.withdraw_bid(ctx, bid_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects/{project_id}/bids",
    summary="All bids on my project, with eligibility",
    response_model=ClientBidsOut,
    responses={200: _ok(EX_CLIENT_BIDS), **error_responses(401, 403, 404, 422)},
)
async def client_bids(ctx: ClientViewer, project_id: uuid.UUID) -> ClientBidsOut:
    return await svc.client_bids(ctx, project_id)


@router.post(
    "/projects/{project_id}/bidding-terms/preview",
    summary="Preview a change to my project's bidding terms",
    response_model=TermsPreviewOut,
    responses={200: _ok(EX_TERMS_PREVIEW), **error_responses(401, 403, 404, 409, 422)},
)
async def preview_terms(
    ctx: TermsWriter, project_id: uuid.UUID, body: TermsChange
) -> TermsPreviewOut:
    """Re-run eligibility under lower standards, a higher budget or a smaller team, unsaved."""
    return await bidding_terms.preview(ctx, project_id, body)


@router.patch(
    "/projects/{project_id}/bidding-terms",
    summary="Change my project's bidding terms",
    response_model=ClientBidsOut,
    responses={200: _ok(EX_CLIENT_BIDS), **error_responses(401, 403, 404, 409, 422)},
)
async def change_terms(
    ctx: TermsWriter, project_id: uuid.UUID, body: TermsChange, if_match: IfMatch = None
) -> ClientBidsOut:
    """Lower the standards, raise the budget or reduce the team (spec §9.19); bidders are told."""
    return await bidding_terms.apply(ctx, project_id, body, if_match)
