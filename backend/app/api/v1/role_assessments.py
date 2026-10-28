"""Role assessments for newcomers (role assessment spec §6–§9).

The status drives the bid sheet; an attempt is started with consent, then answered one question
at a time with the window token from start/resume in `X-Attempt-Token`. The server decides the
deadline, the current question and the result; answers and per-question correctness are never
in a response.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.api.deps import acting, rate_limit
from app.core.errors import DomainError, ErrorCode
from app.schemas.common import error_responses
from app.schemas.role_assessments import (
    AnswerIn,
    AnswerOut,
    AssessmentResultOut,
    AssessmentStatusOut,
    AttemptStateOut,
    FocusEventIn,
    FocusEventOut,
    HeartbeatIn,
    HeartbeatOut,
    HistoryItemOut,
    StartedOut,
    StartIn,
)
from app.services import role_assessments as svc
from app.services.context import Ctx

MAX_BODY_BYTES = 2048  # every request body here is a few fields (role assessment spec §15)


async def small_body(request: Request) -> None:
    """Refuse a request body over 2 KB (the app-wide limit is 256 KB). A GET has no body to read
    (reading it anyway turns a client that went away into a logged error)."""
    if request.method in ("GET", "HEAD"):
        return
    if len(await request.body()) > MAX_BODY_BYTES:
        raise DomainError(code=ErrorCode.PAYLOAD_TOO_LARGE)


router = APIRouter(tags=["role-assessments"], dependencies=[Depends(small_body)])
Taker = Annotated[Ctx, Depends(acting("assessment.take"))]
AttemptToken = Annotated[
    str | None,
    Header(alias="X-Attempt-Token", max_length=100, description="Window token from start/resume"),
]
IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", description="UUID; a repeat resumes the attempt")
]

_P = "1c9f2e4a-7b3d-4e5f-8a6b-9c0d1e2f3a4b"
_S = "2d0a3f5b-8c4e-4f6a-9b7c-0d1e2f3a4b5c"
_A = "3e1b4a6c-9d5f-4a7b-8c8d-1e2f3a4b5c6d"
_Q = "4f2c5b7d-0e6a-4b8c-9d9e-2f3a4b5c6d7e"
EX_RESULT: dict[str, Any] = {
    "attempt_id": _A,
    "label": "FastAPI · Authentication and authorization, API design and HTTP, Databases and ORM",
    "outcome": "PASSED",
    "passed": True,
    "score": 78,
    "pass_overall": 60,
    "competencies": [
        {
            "code": "authn_authz",
            "name": "Authentication and authorization",
            "weight_bp": 3500,
            "score": 85,
        },
        {"code": "api_design", "name": "API design and HTTP", "weight_bp": 2000, "score": 72},
    ],
    "strongest": "Authentication and authorization",
    "weakest": "API design and HTTP",
    "submitted_at": "2026-10-28T09:14:00Z",
    "valid_until": "2027-04-26T09:14:00Z",
    "next_allowed_at": None,
}  # fmt: skip
EX_BLUEPRINT: dict[str, Any] = {
    "label": EX_RESULT["label"],
    "competencies": [
        {"code": "authn_authz", "name": "Authentication and authorization", "weight_bp": 3500,
         "question_count": 4,
         "reasons": ["Core skill of this role (FastAPI)",
                     "The requirements mention: sign in, roles, permissions"]},
        {"code": "api_design", "name": "API design and HTTP", "weight_bp": 2000,
         "question_count": 3, "reasons": ["Core skill of this role (FastAPI)"]},
    ],
    "question_count": 12,
    "time_limit_seconds": 900,
    "extra_time_seconds": 0,
    "pass_overall": 60,
    "floor": 40,
    "heavy_weight": 20,
}  # fmt: skip
EX_STATUS: dict[str, Any] = {
    "status": "REQUIRED",
    "reason": None,
    "message": "As a new developer on DevSync, you show your competency for this role with a "
    "short assessment.",
    "rules_version": 1,
    "blueprint": EX_BLUEPRINT,
    "attempt_id": None,
    "open_elsewhere": None,
    "result": None,
    "next_allowed_at": None,
    "fallback": None,
    "bidding_deadline": "2026-11-05T12:30:00Z",
    "bidding_closes_soon": False,
}
EX_QUESTION: dict[str, Any] = {
    "id": _Q,
    "index": 3,
    "total": 12,
    "text": "A login endpoint returns 200 for a wrong password. Which line causes it?",
    "code_snippet": "1  @app.post('/login')\n2  def login(body: Login):\n",
    "options": ["Line 1", "Line 2", "Line 3", "Line 4"],
    "competency": "Authentication and authorization",
}
EX_STATE: dict[str, Any] = {
    "id": _A,
    "label": EX_RESULT["label"],
    "state": "OPEN",
    "current_index": 3,
    "total": 12,
    "started_at": "2026-10-28T09:00:00Z",
    "deadline_at": "2026-10-28T09:15:00Z",
    "server_now": "2026-10-28T09:04:31Z",
    "focus_leaves": 0,
    "leave_limit": 2,
    "question": EX_QUESTION,
    "result": None,
}
EX_STARTED = {**EX_STATE, "attempt_token": "q3Wd8n1Zr0-example-window-token-Xf2k"}


def _ok(example: Any, *errors: int, code: int = 200) -> dict[int | str, dict[str, Any]]:
    return {
        code: {"content": {"application/json": {"example": example}}},
        **error_responses(401, 403, 404, *errors),
    }


@router.get(
    "/projects/{project_id}/slots/{slot_id}/assessment",
    summary="Role assessment status for a slot",
    response_model=AssessmentStatusOut,
    dependencies=[Depends(rate_limit("assessment_read"))],
    responses=_ok(EX_STATUS, 422, 429),
)
async def slot_status(project_id: uuid.UUID, slot_id: uuid.UUID, ctx: Taker) -> AssessmentStatusOut:
    """Whether you need a role assessment to bid for this role, what it covers and where you
    stand. Developers only: clients and admins get 403 ROLE_NOT_ALLOWED."""
    return await svc.slot_status(ctx, project_id, slot_id)


@router.post(
    "/projects/{project_id}/slots/{slot_id}/assessment/attempts",
    summary="Start a role assessment",
    status_code=status.HTTP_201_CREATED,
    response_model=StartedOut,
    dependencies=[Depends(rate_limit("assessment_start"))],
    responses={
        **_ok(EX_STARTED, 400, 409, 422, 429, code=201),
        200: {
            "description": "Your open attempt for this role, with a new window token",
            "content": {"application/json": {"example": EX_STARTED}},
        },
    },
)
async def start(
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    *,
    body: StartIn,
    ctx: Taker,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> StartedOut:
    """Starts the attempt after you accept the rules (`consent`, `rules_version`). An open attempt
    for the same role is resumed instead (200). The window token is returned once."""
    out, created = await svc.start(ctx, project_id, slot_id, body, idempotency_key)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return out


@router.post(
    "/assessment-attempts/{attempt_id}/resume",
    summary="Resume a role assessment",
    response_model=StartedOut,
    dependencies=[Depends(rate_limit("assessment_resume"))],
    responses=_ok(EX_STARTED, 409, 422, 429),
)
async def resume(attempt_id: uuid.UUID, ctx: Taker) -> StartedOut:
    """A new window token for your open attempt (after a reload or on another device); the old
    window's next request gets ATTEMPT_MOVED. The deadline doesn't change."""
    return await svc.resume(ctx, attempt_id)


@router.get(
    "/assessment-attempts/{attempt_id}",
    summary="A role assessment attempt",
    response_model=AttemptStateOut,
    dependencies=[Depends(rate_limit("assessment_read"))],
    responses=_ok(EX_STATE, 400, 409, 422, 429),
)
async def get_attempt(
    attempt_id: uuid.UUID, ctx: Taker, token: AttemptToken = None
) -> AttemptStateOut:
    """State, position, deadline and server time; the current question only with a valid window
    token. An attempt whose time ran out is scored first."""
    return await svc.get(ctx, attempt_id, token)


@router.post(
    "/assessment-attempts/{attempt_id}/answer",
    summary="Answer the current question",
    response_model=AnswerOut,
    dependencies=[Depends(rate_limit("assessment_answer"))],
    responses=_ok(
        {
            "status": "NEXT",
            "current_index": 4,
            "total": 12,
            "question": EX_QUESTION,
            "result": None,
        },
        400, 409, 422, 429,
    ),
)  # fmt: skip
async def answer(
    attempt_id: uuid.UUID, body: AnswerIn, ctx: Taker, token: AttemptToken = None
) -> AnswerOut:
    """Locks your answer (or a skip, `choice: null`) to the current question and moves on; there
    is no going back. After the last question the attempt is scored."""
    return await svc.answer(ctx, attempt_id, body, token)


@router.post(
    "/assessment-attempts/{attempt_id}/finish",
    summary="Finish a role assessment early",
    response_model=AssessmentResultOut,
    dependencies=[Depends(rate_limit("assessment_finish"))],
    responses=_ok(EX_RESULT, 400, 409, 422, 429),
)
async def finish(
    attempt_id: uuid.UUID, ctx: Taker, token: AttemptToken = None
) -> AssessmentResultOut:
    """Ends the attempt now; questions not answered count as wrong."""
    return await svc.finish(ctx, attempt_id, token)


@router.post(
    "/assessment-attempts/{attempt_id}/focus-events",
    summary="Report leaving the assessment",
    response_model=FocusEventOut,
    dependencies=[Depends(rate_limit("assessment_focus"))],
    responses=_ok(
        {"status": "WARNING", "focus_leaves": 1, "leave_limit": 2, "result": None},
        400, 409, 422, 429,
    ),
)  # fmt: skip
async def focus_event(
    attempt_id: uuid.UUID, body: FocusEventIn, ctx: Taker, token: AttemptToken = None
) -> FocusEventOut:
    """One leave (idempotent by `seq`): the first is a warning; reaching the limit ends the
    attempt, which is scored but can't count as a pass."""
    return await svc.focus_event(ctx, attempt_id, body, token)


@router.post(
    "/assessment-attempts/{attempt_id}/heartbeat",
    summary="Assessment heartbeat",
    response_model=HeartbeatOut,
    dependencies=[Depends(rate_limit("assessment_heartbeat"))],
    responses=_ok(
        {"server_now": "2026-10-28T09:04:31Z", "deadline_at": "2026-10-28T09:15:00Z"},
        400, 409, 422, 429,
    ),
)  # fmt: skip
async def heartbeat(
    attempt_id: uuid.UUID, body: HeartbeatIn, ctx: Taker, token: AttemptToken = None
) -> HeartbeatOut:
    """Keeps the server's clock and yours in step; long gaps are recorded, never counted as a
    leave."""
    del body  # visibility and full screen are informational; the server measures the gaps
    return await svc.heartbeat(ctx, attempt_id, token)


@router.get(
    "/assessment-attempts/{attempt_id}/result",
    summary="Role assessment result",
    response_model=AssessmentResultOut,
    dependencies=[Depends(rate_limit("assessment_read"))],
    responses=_ok(EX_RESULT, 409, 422, 429),
)
async def get_result(attempt_id: uuid.UUID, ctx: Taker) -> AssessmentResultOut:
    """Your score per competency and overall; never the answers."""
    return await svc.result(ctx, attempt_id)


@router.get(
    "/me/role-assessments",
    summary="My role assessments",
    response_model=list[HistoryItemOut],
    dependencies=[Depends(rate_limit("assessment_history"))],
    responses=_ok(
        [{"attempt_id": _A, "label": EX_RESULT["label"], "outcome": "PASSED", "score": 78,
          "passed": True, "started_at": "2026-10-28T09:00:00Z",
          "submitted_at": "2026-10-28T09:14:00Z", "valid_until": "2027-04-26T09:14:00Z"}],
        429,
    ),
)  # fmt: skip
async def my_history(ctx: Taker) -> list[HistoryItemOut]:
    """Every scored role assessment of yours, newest first."""
    return await svc.history(ctx)
