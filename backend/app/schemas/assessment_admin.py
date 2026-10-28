"""Admin tools for role assessments (role assessment spec §12): flagged attempts, voiding,
extra-time accommodations and the question bank review. Admin-only, so — unlike every candidate
or client response — the detail views include correctness, answers and focus events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import StrictRequest

QuestionStatusName = Literal["DRAFT", "APPROVED", "RETIRED"]
QuestionSourceName = Literal["HUMAN", "CLAUDE_GENERATED"]
ReviewLevelName = Literal["NONE", "SELF_VERIFIED", "HUMAN_APPROVED"]


class FlaggedItemOut(BaseModel):
    attempt_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_name: str
    label: str
    started_at: datetime
    submitted_at: datetime | None
    score: int | None = Field(description="0–100 once scored.")
    passed: bool | None
    terminated_reason: str | None
    flagged: bool
    focus_leaves: int
    connection_gaps: int
    reviewed_at: datetime | None
    voided: bool


class AnswerTraceOut(BaseModel):
    index: int
    question_id: uuid.UUID
    slug: str | None
    competency: str | None
    difficulty: int
    choice: int | None = Field(description="0–3, or null when skipped or not reached.")
    correct: bool
    answered_at: datetime | None
    seconds: int | None = Field(description="Time since the previous answer (or the start).")


class AttemptDetailOut(FlaggedItemOut):
    deadline_at: datetime
    extra_time_seconds: int
    reused_seen: bool
    focus_events: list[dict[str, Any]]
    last_heartbeat_at: datetime | None
    breakdown: list[dict[str, Any]]
    answers: list[AnswerTraceOut]
    void_reason: str | None


class VoidIn(StrictRequest):
    reason: str = Field(min_length=20, max_length=500)


class VoidOut(BaseModel):
    attempt_id: uuid.UUID
    voided_at: datetime
    bids_affected: int


class AccommodationIn(StrictRequest):
    extra_time_pct: Literal[0, 25, 50]
    note: str = Field("", max_length=300)


class AccommodationOut(BaseModel):
    user_id: uuid.UUID
    extra_time_pct: int
    note: str
    granted_at: datetime


class QuestionAdminOut(BaseModel):
    id: uuid.UUID
    slug: str | None
    skill: str
    competency_id: uuid.UUID | None
    competency: str | None
    difficulty: int
    text: str
    code_snippet: str | None
    options: list[str]
    correct_index: int
    explanation: str | None
    status: QuestionStatusName
    source: QuestionSourceName
    review_level: ReviewLevelName
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    verification: dict[str, Any] | None
    active: bool
    times_served: int
    version: int


class QuestionPatch(StrictRequest):
    """Edits to a DRAFT question (an approved one is retired and replaced instead)."""

    text: str | None = Field(None, min_length=5, max_length=1000)
    code_snippet: str | None = Field(None, max_length=1500)
    options: list[str] | None = Field(None, min_length=4, max_length=4)
    correct_index: int | None = Field(None, ge=0, le=3)
    explanation: str | None = Field(None, max_length=600)
    difficulty: int | None = Field(None, ge=1, le=3)
    competency_id: uuid.UUID | None = None

    @field_validator("options")
    @classmethod
    def _distinct(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            cleaned = [o.strip() for o in value]
            if any(not o or len(o) > 300 for o in cleaned) or len(set(cleaned)) != 4:  # noqa: PLR2004
                raise ValueError("four distinct, non-empty options of at most 300 characters")
            return cleaned
        return value
