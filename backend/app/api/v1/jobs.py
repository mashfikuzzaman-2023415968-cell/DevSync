"""Background job status and live progress (spec §10.3, D107).

`GET /jobs/{id}` is the job's state; `GET /jobs/{id}/events` streams it as Server-Sent Events:
the current state first, then each progress event the worker publishes, a heartbeat comment
every 20 s, and the stream ends when the job finishes or after 30 minutes (the browser's
EventSource reconnects with `Last-Event-ID` and resumes where it left off).

The stream needs the session cookie (EventSource sends it on same-origin requests), refuses a
foreign `Origin` or a cross-site `Sec-Fetch-Site` (403) and a user's fourth concurrent stream
(429). It holds no database connection while open: the job is checked in short sessions.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, app_settings, require
from app.core.authz import Principal
from app.core.csrf import origin_allowed
from app.core.errors import ErrorCode, ForbiddenError
from app.core.job_events import TERMINAL, acquire_stream, read_from, release_stream
from app.core.ratelimit import RateLimited
from app.core.redis import get_redis
from app.db.context import DbContext
from app.db.session import open_session
from app.schemas.common import error_responses
from app.schemas.jobs import EX_JOB, JobOut
from app.services import jobs_api as svc

router = APIRouter(tags=["jobs"])
Reader = Annotated[Principal, Depends(require("job.read"))]

POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 20.0
MAX_STREAM_SECONDS = 30 * 60
RETRY_MS = 3000
SAME_SITE = frozenset({"same-origin", "none"})


@router.get(
    "/jobs/{job_id}",
    summary="A background job's status",
    response_model=JobOut,
    responses={
        200: {"content": {"application/json": {"example": EX_JOB}}},
        **error_responses(401, 403, 404, 422, 429),
    },
)
async def get_job(principal: Reader, db: DbSession, job_id: uuid.UUID) -> JobOut:
    """Status and progress of a job you started (admins: any job). Others' jobs are 404."""
    return await svc.get_job(db, principal, job_id)


def _event(data: dict[str, object], event_id: int | None = None, name: str = "progress") -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def _current(principal: Principal, job_id: uuid.UUID) -> JobOut:
    async with open_session(DbContext(user_id=principal.user_id, role=principal.role)) as db:
        return await svc.get_job(db, principal, job_id)


def _resume_index(last_event_id: str | None) -> int:
    if last_event_id is None or not last_event_id.isdigit() or len(last_event_id) > 6:  # noqa: PLR2004
        return 0
    return int(last_event_id) + 1


async def _stream(
    request: Request, principal: Principal, job: JobOut, start: int
) -> AsyncIterator[str]:
    redis = get_redis()
    try:
        yield f"retry: {RETRY_MS}\n\n"
        yield _event(job.model_dump(mode="json", include={"status", "progress"}), name="status")
        if job.status in TERMINAL:
            return
        index, began = start, time.monotonic()
        last_beat = began
        while time.monotonic() - began < MAX_STREAM_SECONDS:
            if await request.is_disconnected():
                return
            for event in await read_from(redis, job.id, index):
                yield _event(event, index)
                index += 1
                if str(event.get("status", "")) in TERMINAL:
                    return
            if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                last_beat = time.monotonic()
                yield ": heartbeat\n\n"
                # The worker may have died without a final event: the row is the truth.
                latest = await _current(principal, job.id)
                if latest.status in TERMINAL:
                    yield _event(latest.model_dump(mode="json", include={"status", "progress"}),
                                 name="status")  # fmt: skip
                    return
            await asyncio.sleep(POLL_SECONDS)
    finally:
        await release_stream(redis, principal.user_id)


@router.get(
    "/jobs/{job_id}/events",
    summary="Live progress of a background job (Server-Sent Events)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "An event stream: `status` first, then `progress` events.",
            "content": {"text/event-stream": {"example": 'event: progress\ndata: {"progress":40}'}},
        },
        **error_responses(401, 403, 404, 422, 429),
    },
)  # fmt: skip
async def job_events(
    request: Request,
    principal: Reader,
    job_id: uuid.UUID,
    last_event_id: Annotated[str | None, Header(max_length=12)] = None,
    sec_fetch_site: Annotated[str | None, Header(max_length=32)] = None,
) -> StreamingResponse:
    """Stream a job you started. Same-origin only; at most 3 open streams per user."""
    origin = request.headers.get("origin")
    public = app_settings(request).PUBLIC_ORIGIN
    if (origin is not None and not origin_allowed(origin, None, public)) or (
        sec_fetch_site is not None and sec_fetch_site not in SAME_SITE
    ):
        raise ForbiddenError("Open this page from DevSync.", code=ErrorCode.CSRF_FAILED)
    job = await _current(principal, job_id)  # 404 before taking a stream slot
    if not await acquire_stream(get_redis(), principal.user_id):
        raise RateLimited(30)
    return StreamingResponse(
        _stream(request, principal, job, _resume_index(last_event_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
