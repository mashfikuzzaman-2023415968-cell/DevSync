"""Admin tools for role assessments (role assessment spec §12). Everyone but a TOTP-verified
admin gets 404 (§14.17). Void and accommodations need a step-up (TOTP re-confirmed)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import acting, rate_limit
from app.schemas.assessment_admin import (
    AccommodationIn,
    AccommodationOut,
    AttemptDetailOut,
    FlaggedItemOut,
    QuestionAdminOut,
    QuestionPatch,
    VoidIn,
    VoidOut,
)
from app.schemas.common import error_responses
from app.services import assessment_admin as svc
from app.services.context import Ctx

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Annotated[Ctx, Depends(acting("admin.access"))]

_A = "3e1b4a6c-9d5f-4a7b-8c8d-1e2f3a4b5c6d"
_U = "5a3d6c8e-1f7b-4c9d-8e0f-3a4b5c6d7e8f"
_Q = "4f2c5b7d-0e6a-4b8c-9d9e-2f3a4b5c6d7e"
EX_ITEM: dict[str, Any] = {
    "attempt_id": _A,
    "candidate_id": _U,
    "candidate_name": "Rafsan Haque",
    "label": "React · State and hooks, Components and props, Effects and data fetching",
    "started_at": "2026-10-28T09:00:00Z",
    "submitted_at": "2026-10-28T09:03:12Z",
    "score": 25,
    "passed": False,
    "terminated_reason": "FOCUS_LIMIT",
    "flagged": True,
    "focus_leaves": 2,
    "connection_gaps": 0,
    "reviewed_at": None,
    "voided": False,
}
EX_DETAIL: dict[str, Any] = {
    **EX_ITEM,
    "deadline_at": "2026-10-28T09:15:00Z",
    "extra_time_seconds": 0,
    "reused_seen": False,
    "focus_events": [
        {"seq": 1, "type": "VISIBILITY_HIDDEN", "server_at": "2026-10-28T09:01:40Z"},
        {"seq": 2, "type": "FULLSCREEN_EXIT", "server_at": "2026-10-28T09:03:12Z"},
    ],
    "last_heartbeat_at": "2026-10-28T09:03:00Z",
    "breakdown": [{"code": "state_hooks", "name": "State and hooks", "weight_bp": 3500,
                   "earned_w": 3, "possible_w": 12, "score_bp": 2500}],
    "answers": [{"index": 0, "question_id": _Q, "slug": "react-state-hooks-04",
                 "competency": "State and hooks", "difficulty": 2, "choice": 1, "correct": True,
                 "answered_at": "2026-10-28T09:00:41Z", "seconds": 41}],
    "void_reason": None,
}  # fmt: skip
EX_QUESTION: dict[str, Any] = {
    "id": _Q,
    "slug": "react-state-hooks-04",
    "skill": "React",
    "competency_id": "6b4e7d9f-2a8c-4d0e-9f1a-4b5c6d7e8f90",
    "competency": "State and hooks",
    "difficulty": 2,
    "text": "A counter increments twice in one click handler but shows +1. Why?",
    "code_snippet": None,
    "options": ["Stale state in both calls", "React batches renders", "StrictMode", "A bug"],
    "correct_index": 0,
    "explanation": "Both calls read the same `count`; use the updater form.",
    "status": "APPROVED",
    "source": "CLAUDE_GENERATED",
    "review_level": "SELF_VERIFIED",
    "reviewed_by_name": None,
    "reviewed_at": "2026-10-28T06:00:00Z",
    "verification": {"method": "execution", "checks_passed": True, "solver_agreement": True},
    "active": False,
    "times_served": 7,
    "version": 1,
}


def _ok(example: Any, *errors: int) -> dict[int | str, dict[str, Any]]:
    return {
        200: {"content": {"application/json": {"example": example}}},
        **error_responses(401, 403, 404, *errors),
    }


@router.get(
    "/assessments",
    summary="Role assessment attempts (review queue)",
    response_model=list[FlaggedItemOut],
    dependencies=[Depends(rate_limit("admin"))],
    responses=_ok([EX_ITEM], 422, 429),
)
async def list_attempts(
    ctx: Admin,
    *,
    flagged: Annotated[bool | None, Query(description="Only flagged (or unflagged)")] = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
    skill_id: uuid.UUID | None = None,
) -> list[FlaggedItemOut]:
    """Newest first, at most 200; filter by flag, start date and skill."""
    return await svc.list_attempts(
        ctx, flagged=flagged, since=since, until=until, skill_id=skill_id
    )


@router.get(
    "/assessments/{attempt_id}",
    summary="A role assessment attempt in full",
    response_model=AttemptDetailOut,
    dependencies=[Depends(rate_limit("admin"))],
    responses=_ok(EX_DETAIL, 422, 429),
)
async def attempt_detail(attempt_id: uuid.UUID, ctx: Admin) -> AttemptDetailOut:
    """Focus events, gaps, per-question correctness and response times, and the result."""
    return await svc.attempt_detail(ctx, attempt_id)


@router.post(
    "/assessments/{attempt_id}/void",
    summary="Void a role assessment",
    response_model=VoidOut,
    dependencies=[Depends(rate_limit("admin_assessment_action"))],
    responses=_ok(
        {"attempt_id": _A, "voided_at": "2026-10-28T10:00:00Z", "bids_affected": 1}, 409, 422, 429
    ),
)
async def void_attempt(attempt_id: uuid.UUID, body: VoidIn, ctx: Admin) -> VoidOut:
    """Needs a step-up. The result stops counting, bids relying on it are re-evaluated and their
    bidders told, and the developer may retake at once."""
    return await svc.void_attempt(ctx, attempt_id, body)


@router.post(
    "/assessments/{attempt_id}/review",
    summary="Mark a role assessment reviewed",
    response_model=FlaggedItemOut,
    dependencies=[Depends(rate_limit("admin"))],
    responses=_ok(EX_ITEM, 422, 429),
)
async def mark_reviewed(attempt_id: uuid.UUID, ctx: Admin) -> FlaggedItemOut:
    """Takes a flagged attempt out of the queue without voiding it."""
    return await svc.mark_reviewed(ctx, attempt_id)


@router.post(
    "/users/{user_id}/accommodation",
    summary="Grant assessment extra time",
    response_model=AccommodationOut,
    dependencies=[Depends(rate_limit("admin_assessment_action"))],
    responses=_ok(
        {"user_id": _U, "extra_time_pct": 25, "note": "", "granted_at": "2026-10-28T10:00:00Z"},
        409, 422, 429,
    ),
)  # fmt: skip
async def set_accommodation(
    user_id: uuid.UUID, body: AccommodationIn, ctx: Admin
) -> AccommodationOut:
    """25 % or 50 % extra time (0 removes it) for assessments started from now on. Step-up."""
    return await svc.set_accommodation(ctx, user_id, body)


@router.get(
    "/question-bank",
    summary="Question bank",
    response_model=list[QuestionAdminOut],
    dependencies=[Depends(rate_limit("admin"))],
    responses=_ok([EX_QUESTION], 422, 429),
)
async def list_questions(
    ctx: Admin,
    *,
    skill_id: uuid.UUID | None = None,
    competency_id: uuid.UUID | None = None,
    difficulty: Annotated[int | None, Query(ge=1, le=3)] = None,
    status: Literal["DRAFT", "APPROVED", "RETIRED"] | None = None,
    source: Literal["HUMAN", "CLAUDE_GENERATED"] | None = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[QuestionAdminOut]:
    """With answers, explanations and verification records (admins only)."""
    return await svc.list_questions(
        ctx, skill_id=skill_id, competency_id=competency_id, difficulty=difficulty,
        status=status, source=source, offset=offset, limit=limit,
    )  # fmt: skip


@router.patch(
    "/question-bank/{question_id}",
    summary="Edit a draft question",
    response_model=QuestionAdminOut,
    dependencies=[Depends(rate_limit("admin"))],
    responses=_ok(EX_QUESTION, 409, 422, 429),
)
async def edit_question(
    question_id: uuid.UUID, body: QuestionPatch, ctx: Admin
) -> QuestionAdminOut:
    """Drafts only: an approved question is retired and replaced by a new version."""
    return await svc.edit_question(ctx, question_id, body)


@router.post(
    "/question-bank/{question_id}/approve",
    summary="Approve a question",
    response_model=QuestionAdminOut,
    dependencies=[Depends(rate_limit("admin"))],
    responses=_ok(EX_QUESTION, 409, 422, 429),
)
async def approve_question(question_id: uuid.UUID, ctx: Admin) -> QuestionAdminOut:
    """Human approval (HUMAN_APPROVED, named after you)."""
    return await svc.approve_question(ctx, question_id)


@router.post(
    "/question-bank/{question_id}/retire",
    summary="Retire a question",
    response_model=QuestionAdminOut,
    dependencies=[Depends(rate_limit("admin"))],
    responses=_ok(EX_QUESTION, 409, 422, 429),
)
async def retire_question(question_id: uuid.UUID, ctx: Admin) -> QuestionAdminOut:
    """Never below a practice test's question count."""
    return await svc.retire_question(ctx, question_id)
