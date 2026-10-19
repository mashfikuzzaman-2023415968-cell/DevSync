"""Projects and the CPM planner (spec §10.2 Projects). Client-owned; object checks in the service.

Every operation declares its error responses and a success example (contract-first, §10.4).
Optimistic concurrency uses the `If-Match` header carrying the project `version`; a mismatch is a
409 `VERSION_CONFLICT`. Money fields are integer paisa.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from app.api.deps import acting, rate_limit
from app.schemas.common import error_responses
from app.schemas.projects import CancelIn as CancelBody
from app.schemas.projects import (
    CpmNodeOut,
    CpmPreviewOut,
    DependenciesReplace,
    MilestoneOut,
    MilestonesReplace,
    PlanOut,
    PlanPreviewIn,
    ProjectCreate,
    ProjectListItem,
    ProjectOut,
    ProjectUpdate,
    PublishIn,
    SlotOut,
    SlotsReplace,
)
from app.services import projects as svc
from app.services.context import Ctx

router = APIRouter(tags=["projects"])

Creator = Annotated[Ctx, Depends(acting("project.create"))]
Writer = Annotated[Ctx, Depends(acting("project.write"))]
Reader = Annotated[Ctx, Depends(acting("project.read"))]
Canceller = Annotated[Ctx, Depends(acting("project.cancel"))]
Payer = Annotated[Ctx, Depends(acting("payment.verify"))]
IfMatch = Annotated[int | None, Header(alias="If-Match", description="Project version")]
CREATE_LIMIT = [Depends(rate_limit("project_create"))]

_PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c"
_SKILL = "0b7d4c1e-2f3a-4b5c-8d9e-0f1a2b3c4d5e"
_MID = "3c2b1a09-8f7e-4d6c-b5a4-1e2d3c4b5a60"

EX_PROJECT = {
    "id": _PID,
    "client_id": "11111111-1111-4111-8111-111111111111",
    "title": "Online ordering system",
    "summary": "A web app for a restaurant to take and track orders.",
    "description": "Menu, cart, checkout and an admin dashboard.",
    "requirements": "React front end, FastAPI back end, PostgreSQL.",
    "budget_paisa": 12_000_000,
    "bonus_pool_paisa": 1_200_000,
    "deadline_days": 30,
    "team_size": 4,
    "start_date": "2026-11-02",
    "bidding_deadline": "2026-11-05T12:00:00Z",
    "status": "DRAFT",
    "cancel_reason": None,
    "bidding_extensions": 0,
    "current_baseline_id": None,
    "version": 1,
    "created_at": "2026-10-19T06:00:00Z",
    "updated_at": "2026-10-19T06:00:00Z",
}
EX_LIST = [
    {
        "id": _PID,
        "title": "Online ordering system",
        "status": "BIDDING",
        "budget_paisa": 12_000_000,
        "team_size": 4,
        "deadline_days": 30,
        "bidding_deadline": "2026-11-05T12:00:00Z",
        "updated_at": "2026-10-19T06:00:00Z",
    }
]
EX_SLOTS = [{"id": _PID, "skill_id": _SKILL, "label": "React developer", "count": 1}]
EX_MILESTONES = [
    {
        "id": _MID,
        "name": "Requirements & design",
        "description": "Scope, wireframes and the data model.",
        "duration_days": 4,
        "share_bp": 1500,
        "position": 0,
        "status": "PLANNED",
        "skill_ids": [_SKILL],
    }
]
EX_NODES = [
    {"key": "m1", "name": "Requirements & design", "es": 0, "ef": 4, "ls": 0, "lf": 4,
     "slack": 0, "critical": True}
]  # fmt: skip
EX_PREVIEW = {
    "feasible": True,
    "duration": 24,
    "nodes": EX_NODES,
    "critical_paths": [["Requirements & design", "Database", "Backend API", "Integration",
                        "Testing & launch"]],
    "cycle": None,
    "total_share_bp": 10000,
    "warnings": [],
}  # fmt: skip
EX_PLAN = {
    "baseline_version": 1,
    "duration": 24,
    "nodes": EX_NODES,
    "edges": [{"predecessor": "m1", "successor": "m2"}],
    "critical_paths": [["Requirements & design", "Database"]],
    "deadline_days": 30,
    "exceeds_deadline": False,
}


def _ok(model: object) -> dict[str, object]:
    return {"content": {"application/json": {"example": model}}}


@router.post(
    "/projects",
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft project",
    response_model=ProjectOut,
    responses={201: _ok(EX_PROJECT), **error_responses(401, 403, 404, 422, 429)},
    dependencies=CREATE_LIMIT,
)
async def create_project(ctx: Creator, body: ProjectCreate) -> ProjectOut:
    return await svc.create_draft(ctx, body)


@router.get(
    "/projects",
    summary="List my projects",
    response_model=list[ProjectListItem],
    responses={200: _ok(EX_LIST), **error_responses(401, 403, 404)},
)
async def list_projects(ctx: Reader) -> list[ProjectListItem]:
    return await svc.list_mine(ctx)


@router.get(
    "/projects/{project_id}",
    summary="Get a project",
    response_model=ProjectOut,
    responses={200: _ok(EX_PROJECT), **error_responses(401, 403, 404, 422)},
)
async def get_project(ctx: Reader, project_id: uuid.UUID) -> ProjectOut:
    return await svc.get_project(ctx, project_id)


@router.patch(
    "/projects/{project_id}",
    summary="Update a draft project",
    response_model=ProjectOut,
    responses={200: _ok(EX_PROJECT), **error_responses(401, 403, 404, 409, 422)},
)
async def update_project(
    ctx: Writer, project_id: uuid.UUID, body: ProjectUpdate, if_match: IfMatch = None
) -> ProjectOut:
    return await svc.update_draft(ctx, project_id, body, if_match)


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft project",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def delete_project(ctx: Writer, project_id: uuid.UUID) -> Response:
    await svc.delete_draft(ctx, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/projects/{project_id}/slots",
    summary="Replace the project's skill slots",
    response_model=list[SlotOut],
    responses={200: _ok(EX_SLOTS), **error_responses(401, 403, 404, 409, 422)},
)
async def replace_slots(ctx: Writer, project_id: uuid.UUID, body: SlotsReplace) -> list[SlotOut]:
    return await svc.replace_slots(ctx, project_id, body)


@router.put(
    "/projects/{project_id}/milestones",
    summary="Replace the project's milestones",
    response_model=list[MilestoneOut],
    responses={200: _ok(EX_MILESTONES), **error_responses(401, 403, 404, 409, 422)},
)
async def replace_milestones(
    ctx: Writer, project_id: uuid.UUID, body: MilestonesReplace
) -> list[MilestoneOut]:
    return await svc.replace_milestones(ctx, project_id, body)


@router.put(
    "/projects/{project_id}/dependencies",
    summary="Replace the project's milestone dependencies",
    response_model=list[CpmNodeOut],
    responses={200: _ok(EX_NODES), **error_responses(401, 403, 404, 409, 422)},
)
async def replace_dependencies(
    ctx: Writer, project_id: uuid.UUID, body: DependenciesReplace
) -> list[CpmNodeOut]:
    return await svc.replace_dependencies(ctx, project_id, body)


@router.post(
    "/projects/{project_id}/plan/preview",
    summary="Preview the CPM timeline of an unsaved plan",
    response_model=CpmPreviewOut,
    responses={200: _ok(EX_PREVIEW), **error_responses(401, 403, 404, 422)},
)
async def preview_plan(ctx: Reader, project_id: uuid.UUID, body: PlanPreviewIn) -> CpmPreviewOut:
    return await svc.plan_preview(ctx, project_id, body)


@router.get(
    "/projects/{project_id}/plan",
    summary="The saved baseline plan and critical paths",
    response_model=PlanOut,
    responses={200: _ok(EX_PLAN), **error_responses(401, 403, 404, 422)},
)
async def get_plan(ctx: Reader, project_id: uuid.UUID) -> PlanOut:
    return await svc.get_plan(ctx, project_id)


@router.post(
    "/projects/{project_id}/publish",
    summary="Publish a draft project for bidding",
    response_model=ProjectOut,
    responses={
        200: _ok({**EX_PROJECT, "status": "BIDDING"}),
        **error_responses(401, 403, 404, 409, 422),
    },
)
async def publish_project(
    ctx: Writer, project_id: uuid.UUID, body: PublishIn, if_match: IfMatch = None
) -> ProjectOut:
    return await svc.publish(ctx, project_id, body.acknowledge_schedule_risk, if_match)


@router.post(
    "/projects/{project_id}/extend-bidding",
    summary="Extend the bidding deadline",
    response_model=ProjectOut,
    responses={200: _ok({**EX_PROJECT, "status": "BIDDING", "bidding_extensions": 1}),
               **error_responses(401, 403, 404, 409, 422)},
)  # fmt: skip
async def extend_bidding(ctx: Writer, project_id: uuid.UUID) -> ProjectOut:
    return await svc.extend_bidding(ctx, project_id)


@router.post(
    "/projects/{project_id}/cancel",
    summary="Cancel a project",
    response_model=ProjectOut,
    responses={200: _ok({**EX_PROJECT, "status": "CANCELLED", "cancel_reason": "Budget changed."}),
               **error_responses(401, 403, 404, 409, 422)},
)  # fmt: skip
async def cancel_project(ctx: Canceller, project_id: uuid.UUID, body: CancelBody) -> ProjectOut:
    return await svc.cancel(ctx, project_id, body.reason)


@router.post(
    "/me/payment-method/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verify a (simulated) payment method",
    responses=error_responses(401, 403, 404),
)
async def verify_payment_method(ctx: Payer) -> Response:
    await svc.verify_payment_method(ctx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
