"""Monitoring endpoints (spec §10.2 Monitoring; D151, D156): the dashboard, risks, the activity
feed and the Evidence tab's per-member summary. Participants and admins read; everything is
role-shaped (members never see budget figures or the client-only risks); 404 for anyone else."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import acting, only_query
from app.schemas.common import Page, error_responses
from app.schemas.monitoring import (
    EX_ACTIVITY,
    EX_DASHBOARD,
    EX_EVIDENCE,
    EX_MY_PROJECT,
    EX_RISKS,
    ActivityItem,
    DashboardForClient,
    DashboardForMember,
    EvidenceSummary,
    MyProject,
    RiskList,
)
from app.services import monitoring as svc
from app.services import my_projects as my_projects_svc
from app.services.context import Ctx

router = APIRouter(tags=["monitoring"])

Reader = Annotated[Ctx, Depends(acting("workspace.read"))]


def _ok(example: object, *errors: int) -> dict[int | str, dict[str, object]]:
    return {
        200: {"content": {"application/json": {"example": example}}},
        **error_responses(*errors),
    }


@router.get(
    "/projects/{project_id}/dashboard",
    summary="Progress, schedule, forecast, health and top risks",
    response_model=DashboardForClient | DashboardForMember,
    responses=_ok(EX_DASHBOARD, 401, 403, 404, 409, 422, 429),
)
async def dashboard(project_id: uuid.UUID, ctx: Reader) -> DashboardForClient | DashboardForMember:
    """The client and admins also get the budget; members don't (D151). 409 before the start."""
    return await svc.dashboard(ctx, project_id)


@router.get(
    "/projects/{project_id}/risks",
    summary="The project's risks, worst first",
    response_model=RiskList,
    responses=_ok(EX_RISKS, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("status"))],
)
async def risks(
    project_id: uuid.UUID, ctx: Reader, status: Literal["OPEN", "RESOLVED"] = "OPEN"
) -> RiskList:
    return await svc.risks(ctx, project_id, status=status)


@router.get(
    "/projects/{project_id}/activity",
    summary="The project's activity (evidence events), newest first",
    response_model=Page[ActivityItem],
    responses=_ok(EX_ACTIVITY, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("cursor", "limit"))],
)
async def activity(
    project_id: uuid.UUID,
    ctx: Reader,
    cursor: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ActivityItem]:
    return await svc.activity(ctx, project_id, cursor=cursor, limit=limit)


@router.get(
    "/projects/{project_id}/evidence",
    summary="Per-member activity summary (Evidence tab)",
    response_model=EvidenceSummary,
    responses=_ok(EX_EVIDENCE, 401, 403, 404, 422, 429),
)
async def evidence(project_id: uuid.UUID, ctx: Reader) -> EvidenceSummary:
    return await svc.evidence_summary(ctx, project_id)


@router.get(
    "/me/projects",
    summary="My projects (developers)",
    response_model=Page[MyProject],
    responses=_ok({"items": [EX_MY_PROJECT], "next_cursor": None}, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("state", "cursor", "limit"))],
)
async def my_projects(
    ctx: Annotated[Ctx, Depends(acting("workspace.my_projects"))],
    state: Literal["active", "completed"] = "active",
    cursor: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[MyProject]:
    """The teams you're in (`active`) or finished (`completed`), newest first, with progress,
    the next deadline and the overall risk while the project is in progress."""
    return await my_projects_svc.my_projects(ctx, state=state, cursor=cursor, limit=limit)
