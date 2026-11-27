"""Task endpoints (spec §10.2 Tasks; DECISIONS D143, D144, D148, D156, D168, D172).

Who may do what is decided per project in `services/tasks.py` (404 for projects the caller
isn't in); `If-Match: <task version>` is required on edits, moves and deletes, and a stale one is
409 `VERSION_CONFLICT`. List endpoints accept only their documented query parameters (400).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import acting, only_query
from app.models.workspace import TaskStatus
from app.schemas.common import Page, error_responses
from app.schemas.tasks import (
    EX_DEPENDENCY,
    EX_EVIDENCE,
    EX_TASK_CARD,
    EX_TASK_DETAIL,
    EX_TASK_PAGE,
    DependencyCreate,
    EvidenceCreate,
    EvidenceOut,
    TaskCard,
    TaskCreate,
    TaskDependencyOut,
    TaskDetail,
    TaskMove,
    TaskPatch,
)
from app.services import tasks as svc
from app.services.context import Ctx

router = APIRouter(tags=["tasks"])

Reader = Annotated[Ctx, Depends(acting("workspace.read"))]
Lead = Annotated[Ctx, Depends(acting("workspace.task.lead"))]
Worker = Annotated[Ctx, Depends(acting("workspace.task.work"))]
IfMatch = Annotated[
    int | None, Header(alias="If-Match", ge=0, le=2_147_483_647, description="Task version")
]
Cursor = Annotated[str | None, Query(min_length=1, max_length=300)]
Limit = Annotated[int, Query(ge=1, le=100)]


def _ok(example: object, *errors: int, code: int = 200) -> dict[int | str, dict[str, object]]:
    ok: dict[int | str, dict[str, object]] = {
        code: {"content": {"application/json": {"example": example}}}
    }
    return {**ok, **error_responses(*errors)}


@router.get(
    "/milestones/{milestone_id}/tasks",
    summary="A milestone's tasks",
    response_model=Page[TaskCard],
    responses=_ok(EX_TASK_PAGE, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("status", "assignee_id", "cursor", "limit"))],
)
async def milestone_tasks(
    milestone_id: uuid.UUID,
    ctx: Reader,
    *,
    status_: Annotated[TaskStatus | None, Query(alias="status")] = None,
    assignee_id: uuid.UUID | None = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> Page[TaskCard]:
    """Cards in column order (To do, In progress, Review, Done), then position."""
    return await svc.list_milestone_tasks(
        ctx, milestone_id, status=status_, assignee_id=assignee_id, cursor=cursor, limit=limit
    )


@router.post(
    "/milestones/{milestone_id}/tasks",
    summary="Create a task (team lead)",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskDetail,
    responses=_ok(EX_TASK_DETAIL, 401, 403, 404, 409, 422, 429, code=201),
)
async def create_task(milestone_id: uuid.UUID, body: TaskCreate, ctx: Lead) -> TaskDetail:
    """Added to the bottom of To do. 409 `MILESTONE_FINISHED`, `LIMIT_REACHED` (1,000 per
    project); 422 for an assignee who isn't an active member or dependencies elsewhere."""
    return await svc.create_task(ctx, milestone_id, body)


@router.get(
    "/projects/{project_id}/tasks",
    summary="The project's board",
    response_model=Page[TaskCard],
    responses=_ok(EX_TASK_PAGE, 400, 401, 403, 404, 422, 429),
    dependencies=[
        Depends(only_query("milestone_id", "assignee_id", "mine", "status", "cursor", "limit"))
    ],
)
async def project_tasks(
    project_id: uuid.UUID,
    ctx: Reader,
    *,
    milestone_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    mine: bool = False,
    status_: Annotated[TaskStatus | None, Query(alias="status")] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> Page[TaskCard]:
    """All milestones or one, everyone's or only mine; each column pages 50 at a time (D158)."""
    return await svc.list_tasks(
        ctx,
        project_id,
        milestone_id=milestone_id,
        assignee_id=assignee_id,
        mine=mine,
        status=status_,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/tasks/{task_id}",
    summary="A task with its dependencies, evidence and allowed moves",
    response_model=TaskDetail,
    responses=_ok(EX_TASK_DETAIL, 401, 403, 404, 422, 429),
)
async def get_task(task_id: uuid.UUID, ctx: Reader) -> TaskDetail:
    return await svc.get_task(ctx, task_id)


@router.patch(
    "/tasks/{task_id}",
    summary="Edit a task (team lead)",
    response_model=TaskDetail,
    responses=_ok(EX_TASK_DETAIL, 401, 403, 404, 409, 422, 429),
)
async def patch_task(
    task_id: uuid.UUID, body: TaskPatch, ctx: Lead, if_match: IfMatch = None
) -> TaskDetail:
    """A task changes milestone only while in To do and without dependencies (409
    `DEPENDENCIES_BLOCK_MOVE`)."""
    return await svc.patch_task(ctx, task_id, body, if_match)


@router.post(
    "/tasks/{task_id}/move",
    summary="Move a task (assignee or team lead)",
    response_model=TaskCard,
    responses=_ok(EX_TASK_CARD, 401, 403, 404, 409, 422, 429),
)
async def move_task(
    task_id: uuid.UUID, body: TaskMove, ctx: Worker, if_match: IfMatch = None
) -> TaskCard:
    """One column at a time (409 `ONE_STEP_ONLY`), only in an active milestone (409
    `MILESTONE_NOT_ACTIVE`), Done only when its dependencies are (409 `DEPENDENCIES_NOT_DONE`),
    out of Done only when no finished task depends on it (409 `DEPENDENTS_DONE`)."""
    return await svc.move_task(ctx, task_id, body, if_match)


@router.delete(
    "/tasks/{task_id}",
    summary="Delete a task (team lead; not Done, no evidence)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
async def delete_task(task_id: uuid.UUID, ctx: Lead, if_match: IfMatch = None) -> Response:
    await svc.delete_task(ctx, task_id, if_match)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tasks/{task_id}/dependencies",
    summary="Make a task wait for another (team lead)",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskDependencyOut,
    responses=_ok(EX_DEPENDENCY, 401, 403, 404, 409, 422, 429, code=201),
)
async def add_dependency(
    task_id: uuid.UUID, body: DependencyCreate, ctx: Lead
) -> TaskDependencyOut:
    """Same milestone only (422); 409 `DEPENDENCY_CYCLE` names the cycle in order;
    `LIMIT_REACHED` at 20."""
    return await svc.add_dependency(ctx, task_id, body)


@router.delete(
    "/tasks/{task_id}/dependencies/{depends_on_task_id}",
    summary="Remove a dependency (team lead)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
async def remove_dependency(
    task_id: uuid.UUID, depends_on_task_id: uuid.UUID, ctx: Lead
) -> Response:
    await svc.remove_dependency(ctx, task_id, depends_on_task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tasks/{task_id}/evidence",
    summary="Attach evidence (assignee or team lead)",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceOut,
    responses=_ok(EX_EVIDENCE, 401, 403, 404, 409, 422, 429, code=201),
)
async def add_evidence(task_id: uuid.UUID, body: EvidenceCreate, ctx: Worker) -> EvidenceOut:
    """Links are https only and never fetched; a PR link must look like a GitHub pull request;
    files must be this project's (D148, D168). `LIMIT_REACHED` at 20."""
    return await svc.add_evidence(ctx, task_id, body)
