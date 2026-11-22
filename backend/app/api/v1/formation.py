"""Team formation endpoints (spec §10.2 Formation, §13.5 #24, §14.13 row 7; D106–D110).

Starting a run is asynchronous: 202 with the run and job ids; progress streams from
`/jobs/{job_id}/events` and the result is read from `/formation-runs/{id}`. Only the project's
client starts and confirms; admins read every run and may re-run one to verify it (step-up). A
bidder reads why their own bid was not selected, never anything about other bids.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import acting, rate_limit
from app.schemas.common import Page, error_responses
from app.schemas.formation import (
    EX_ACCEPTED,
    EX_ADMIN_PAGE,
    EX_CONFIRM,
    EX_EXPLANATION,
    EX_RUN,
    EX_SUMMARY,
    AdminRunOut,
    BidExplanationOut,
    ConfirmOut,
    FormationRunAccepted,
    FormationRunCreate,
    FormationRunOut,
    FormationRunSummary,
)
from app.services import formation as svc
from app.services.context import Ctx

router = APIRouter(tags=["formation"])

Runner = Annotated[Ctx, Depends(acting("formation.run"))]
Reader = Annotated[Ctx, Depends(acting("formation.read"))]
Confirmer = Annotated[Ctx, Depends(acting("formation.confirm"))]
Admin = Annotated[Ctx, Depends(acting("admin.access"))]
Bidder = Annotated[Ctx, Depends(acting("bid.explanation"))]
IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", description="UUID; a repeat returns the same run")
]


def _ok(example: object, *errors: int) -> dict[int | str, dict[str, object]]:
    return {
        200: {"content": {"application/json": {"example": example}}},
        **error_responses(*errors),
    }


@router.post(
    "/projects/{project_id}/formation-runs",
    summary="Start team formation",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FormationRunAccepted,
    dependencies=[Depends(rate_limit("formation_run"))],
    responses={
        202: {"content": {"application/json": {"example": EX_ACCEPTED}}},
        **error_responses(401, 403, 404, 409, 422, 429, 503),
    },
)
async def start_run(
    project_id: uuid.UUID,
    body: FormationRunCreate,
    ctx: Runner,
    idempotency_key: IdempotencyKey = None,
) -> FormationRunAccepted:
    """Queues a run on your FORMING project with a preset (or your own weights), the fairness
    dial (0–2 newcomers) and, optionally, different minimum standards. The seed is chosen by the
    server. One run at a time per project."""
    return await svc.start_run(ctx, project_id, body, idempotency_key)


@router.get(
    "/projects/{project_id}/formation-runs",
    summary="A project's formation runs",
    response_model=list[FormationRunSummary],
    responses=_ok([EX_SUMMARY], 401, 403, 404, 422, 429),
)
async def list_runs(project_id: uuid.UUID, ctx: Reader) -> list[FormationRunSummary]:
    """Saved runs, newest first (up to 50)."""
    return await svc.list_runs(ctx, project_id)


@router.get(
    "/formation-runs/{run_id}",
    summary="A formation run and its result",
    response_model=FormationRunOut,
    responses=_ok(EX_RUN, 401, 403, 404, 422, 429),
)
async def get_run(run_id: uuid.UUID, ctx: Reader) -> FormationRunOut:
    """The recommended team with each member's contribution, why it was chosen, its risks, the
    comparison with the next best teams, the cost of fairness, the convergence and whether the
    exact solver confirmed it optimal."""
    return await svc.get_run(ctx, run_id)


@router.post(
    "/formation-runs/{run_id}/confirm",
    summary="Confirm the recommended team",
    response_model=ConfirmOut,
    responses=_ok(EX_CONFIRM, 401, 403, 404, 409, 422, 429),
)
async def confirm(run_id: uuid.UUID, ctx: Confirmer) -> ConfirmOut:
    """Creates the team (the project becomes TEAM_PENDING); the chosen bids are SELECTED and
    the others NOT_SELECTED. Invitations are recorded now and sent in Phase 8."""
    return await svc.confirm(ctx, run_id)


@router.post(
    "/formation-runs/{run_id}/verify",
    summary="Re-run a formation run to verify it (admin)",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FormationRunAccepted,
    responses={
        202: {"content": {"application/json": {"example": EX_ACCEPTED}}},
        **error_responses(401, 403, 404, 409, 422, 429, 503),
    },
)
async def verify(run_id: uuid.UUID, ctx: Admin) -> FormationRunAccepted:
    """Re-runs the run from its frozen inputs and records whether it reproduced the same team
    and fitness. Needs a recent authenticator confirmation (step-up)."""
    return await svc.verify(ctx, run_id)


@router.get(
    "/admin/formation-runs",
    summary="Every formation run (admin)",
    response_model=Page[AdminRunOut],
    responses=_ok(EX_ADMIN_PAGE, 401, 403, 404, 422, 429),
)
async def admin_runs(
    ctx: Admin,
    *,
    cursor: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdminRunOut]:
    """Newest first, cursor-paged."""
    items, next_cursor = await svc.admin_runs(ctx, cursor=cursor, limit=limit)
    return Page[AdminRunOut](items=items, next_cursor=next_cursor)


@router.get(
    "/bids/{bid_id}/explanation",
    summary="Why my bid was not selected",
    response_model=BidExplanationOut,
    responses=_ok(EX_EXPLANATION, 401, 403, 404, 422, 429),
)
async def bid_explanation(bid_id: uuid.UUID, ctx: Bidder) -> BidExplanationOut:
    """For your own bid once a team was confirmed without it: the main gap, a hint, and the
    highest price at which it would have been chosen. Nothing about the other bids is shown."""
    return await svc.bid_explanation(ctx, bid_id)
