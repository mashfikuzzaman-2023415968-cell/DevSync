"""Project file endpoints (spec §10.2 Files; D147, D175): upload and list in a project, delete
by id. Downloads use the existing `GET /files/{id}/download` (signed 5-minute URL)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile, status

from app.api.deps import acting, only_query, rate_limit
from app.schemas.common import Page, error_responses
from app.schemas.project_files import EX_PROJECT_FILE, EX_PROJECT_FILE_PAGE, ProjectFile
from app.services import project_files as svc
from app.services.context import Ctx

router = APIRouter(tags=["files"])

Reader = Annotated[Ctx, Depends(acting("workspace.read"))]
Writer = Annotated[Ctx, Depends(acting("workspace.write"))]
Upload = Annotated[UploadFile, File(description="The file (type checked by its content).")]
ContentLength = Annotated[int | None, Header(alias="Content-Length", ge=0, le=2**40)]


def _ok(example: object, *errors: int, code: int = 200) -> dict[int | str, dict[str, object]]:
    return {
        code: {"content": {"application/json": {"example": example}}},
        **error_responses(*errors),
    }


@router.post(
    "/projects/{project_id}/files",
    summary="Upload a project file (participants)",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectFile,
    responses=_ok(EX_PROJECT_FILE, 401, 403, 404, 409, 413, 422, 429, 503, code=201),
    dependencies=[Depends(rate_limit("upload"))],
)
async def upload_file(
    project_id: uuid.UUID,
    file: Upload,
    ctx: Writer,
    content_length: ContentLength = None,
) -> ProjectFile:
    """PDF (≤ 10 MB), plain text or Markdown (≤ 1 MB), or a PNG, JPEG or WebP image
    (re-encoded); anything else is refused by its content. 20 uploads an hour and 500 MB a day
    per person (429 with `Retry-After`)."""
    return await svc.upload(ctx, project_id, file, file.filename, content_length=content_length)


@router.get(
    "/projects/{project_id}/files",
    summary="The project's files",
    response_model=Page[ProjectFile],
    responses=_ok(EX_PROJECT_FILE_PAGE, 400, 401, 403, 404, 422, 429),
    dependencies=[Depends(only_query("cursor", "limit"))],
)
async def list_files(
    project_id: uuid.UUID,
    ctx: Reader,
    cursor: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ProjectFile]:
    """Newest first, with the tasks that use each file as evidence."""
    return await svc.list_files(ctx, project_id, cursor=cursor, limit=limit)


@router.delete(
    "/files/{file_id}",
    summary="Delete a project file (uploader or lead)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
async def delete_file(file_id: uuid.UUID, ctx: Writer) -> Response:
    """Hidden and never served again; kept for disputes. Only project files can be deleted
    here (anything else is 404)."""
    await svc.delete_file(ctx, file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
