"""Timed skill tests (spec §7.2, §10.2 Tests).

No response model has a field for the correct answer or per-question correctness: the bank's
answers never leave the database (§14.13 row 3; asserted by a schema test).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import StrictRequest


class SkillTestOut(BaseModel):
    """A test with the caller's history for it."""

    id: uuid.UUID
    skill_id: uuid.UUID
    skill_name: str
    title: str
    question_count: int
    time_limit_seconds: int
    last_score: Decimal | None = Field(description="Latest scored result, 0–1.")
    last_attempt_at: datetime | None
    next_attempt_at: datetime | None = Field(description="When a new scored attempt is allowed.")
    open_attempt_id: uuid.UUID | None = Field(description="An attempt still running, if any.")


class AttemptQuestion(BaseModel):
    """One question as shown to the candidate: text and four options only."""

    id: uuid.UUID
    ordinal: int
    text: str
    options: list[str]


class AttemptOut(BaseModel):
    """An attempt in progress or finished. `server_now` lets the client correct its clock."""

    id: uuid.UUID
    test_id: uuid.UUID
    title: str
    started_at: datetime
    deadline_at: datetime
    server_now: datetime
    submitted_at: datetime | None
    score: Decimal | None
    questions: list[AttemptQuestion]
    answers: dict[str, int] = Field(description="The caller's chosen option per question id.")


class AnswerIn(StrictRequest):
    """Choose an option (0–3) for one question of the attempt."""

    question_id: uuid.UUID
    choice: int = Field(ge=0, le=3)


class AnswerAccepted(BaseModel):
    """The answer was recorded."""

    question_id: uuid.UUID
    choice: int
    answered: int = Field(description="How many questions have an answer now.")


class AttemptResult(BaseModel):
    """The score of a submitted attempt (no per-question breakdown)."""

    id: uuid.UUID
    score: Decimal
    correct: int
    total: int
    submitted_at: datetime
    added_to_profile: bool
