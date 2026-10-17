"""Timed skill tests (spec §10.2 Tests): server-side timer, questions without answers."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import acting, rate_limit
from app.schemas.common import error_responses
from app.schemas.skill_tests import (
    AnswerAccepted,
    AnswerIn,
    AttemptOut,
    AttemptResult,
    SkillTestOut,
)
from app.services import skill_tests as svc
from app.services.context import Ctx

router = APIRouter(tags=["skill-tests"])
Taker = Annotated[Ctx, Depends(acting("test.take"))]

_TEST = "5b0c9e7a-1d2e-4f3a-9b8c-7d6e5f4a3b2c"
_ATTEMPT = "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b"
_Q = "3c2b1a0f-9e8d-4c7b-8a6f-5e4d3c2b1a0f"
EX_TEST = {
    "id": _TEST,
    "skill_id": "0b7d4c1e-2f3a-4b5c-8d9e-0f1a2b3c4d5e",
    "skill_name": "React",
    "title": "React fundamentals",
    "question_count": 10,
    "time_limit_seconds": 600,
    "last_score": "0.800",
    "last_attempt_at": "2026-10-10T05:10:00Z",
    "next_attempt_at": "2026-11-09T05:00:00Z",
    "open_attempt_id": None,
}
EX_ATTEMPT = {
    "id": _ATTEMPT,
    "test_id": _TEST,
    "title": "React fundamentals",
    "started_at": "2026-10-18T05:00:00Z",
    "deadline_at": "2026-10-18T05:10:00Z",
    "server_now": "2026-10-18T05:02:13Z",
    "submitted_at": None,
    "score": None,
    "questions": [
        {
            "id": _Q,
            "ordinal": 0,
            "text": "Which hook runs a side effect after render?",
            "options": ["useMemo", "useEffect", "useRef", "useId"],
        }
    ],
    "answers": {_Q: 1},
}


def _ok(example: Any, *errors: int, status: int = 200) -> dict[int | str, dict[str, Any]]:
    return {
        status: {"content": {"application/json": {"example": example}}},
        **error_responses(401, 403, 404, *errors),
    }


@router.get(
    "/skill-tests",
    summary="Skill tests",
    response_model=list[SkillTestOut],
    responses=_ok([EX_TEST]),
)
async def list_tests(ctx: Taker) -> list[SkillTestOut]:
    """Every active test with your last score and when you may take it again."""
    return await svc.list_tests(ctx)


@router.post(
    "/skill-tests/{test_id}/attempts",
    summary="Start a test",
    status_code=201,
    response_model=AttemptOut,
    dependencies=[Depends(rate_limit("test_start"))],
    responses=_ok(EX_ATTEMPT, 409, 422, 429, status=201),
)
async def start(test_id: uuid.UUID, ctx: Taker) -> AttemptOut:
    """Ten random questions; the deadline is set by the server. One scored attempt per test
    every 30 days, one open attempt at a time."""
    return await svc.start_attempt(ctx, test_id)


@router.get(
    "/attempts/{attempt_id}",
    summary="An attempt",
    response_model=AttemptOut,
    responses=_ok(EX_ATTEMPT, 422),
)
async def get_attempt(attempt_id: uuid.UUID, ctx: Taker) -> AttemptOut:
    """Questions (never the answers), your choices and the server time. An attempt whose time
    ran out is scored as it stands."""
    return await svc.get_attempt(ctx, attempt_id)


@router.post(
    "/attempts/{attempt_id}/answer",
    summary="Answer a question",
    response_model=AnswerAccepted,
    responses=_ok({"question_id": _Q, "choice": 1, "answered": 4}, 409, 422),
)
async def answer(attempt_id: uuid.UUID, body: AnswerIn, ctx: Taker) -> AnswerAccepted:
    """Accepted only before the deadline; answering again replaces the choice."""
    return await svc.answer(ctx, attempt_id, body)


@router.post(
    "/attempts/{attempt_id}/submit",
    summary="Submit a test",
    response_model=AttemptResult,
    responses=_ok(
        {
            "id": _ATTEMPT,
            "score": "0.800",
            "correct": 8,
            "total": 10,
            "submitted_at": "2026-10-18T05:08:00Z",
            "added_to_profile": True,
        },
        409,
        422,
    ),
)
async def submit(attempt_id: uuid.UUID, ctx: Taker) -> AttemptResult:
    """Scores the attempt and adds the result to your profile as verified evidence."""
    return await svc.submit(ctx, attempt_id)
