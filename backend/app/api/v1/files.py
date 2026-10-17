"""File downloads (spec §10.2 Files, §14.9): authorize → 302 to a signed 5-minute URL → Nginx."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import RedirectResponse

from app.api.deps import DbSession, app_settings, now
from app.core.config import Settings
from app.schemas.common import error_responses
from app.services import files as svc

router = APIRouter(tags=["files"])
SettingsDep = Annotated[Settings, Depends(app_settings)]


def _disposition(name: str) -> str:
    """`attachment` with an ASCII fallback and the UTF-8 name (RFC 6266 / 5987)."""
    ascii_name = name.encode("ascii", "ignore").decode() or "file"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


@router.get(
    "/files/{file_id}/download",
    summary="Download a file",
    status_code=302,
    response_class=RedirectResponse,
    responses={
        302: {"description": "Redirect to a signed URL that is valid for 5 minutes."},
        **error_responses(404, 422),
    },
)
async def download(file_id: uuid.UUID, db: DbSession, settings: SettingsDep) -> RedirectResponse:
    """Owners and admins may download any of their files; anyone who may see a profile may
    download its portfolio images. Everything else is 'not found'."""
    url = await svc.download_url(db, settings, file_id, now())
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


@router.get(
    "/files/blob/{storage_key}",
    summary="Fetch a file through a signed URL",
    status_code=200,
    response_class=Response,
    responses={
        200: {"description": "The file, streamed by Nginx (attachment, nosniff, sandboxed)."},
        **error_responses(404, 422),
    },
)
async def blob(
    storage_key: uuid.UUID,
    settings: SettingsDep,
    *,
    t: Annotated[str, Query(max_length=64, description="Content type (signed).")],
    n: Annotated[str, Query(max_length=200, description="Download name (signed).")],
    e: Annotated[int, Query(ge=0, le=2**40, description="Expiry, Unix seconds (signed).")],
    s: Annotated[str, Query(min_length=20, max_length=100, description="Signature.")],
) -> Response:
    """Only the signature is checked: links are short-lived and bound to one file."""
    found = svc.resolve_blob(
        settings, storage_key=storage_key, mime_type=t, name=n, expires=e, signature=s, now=now()
    )
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": found.accel_path,
            "Content-Type": found.mime_type,
            "Content-Disposition": _disposition(found.name),
            "Cache-Control": "private, no-store",
        },
    )
