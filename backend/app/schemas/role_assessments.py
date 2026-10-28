"""Role assessment API (role assessment spec §6, §8.1, §9).

No response model has a field for a correct answer or per-question correctness: answers never
leave the database, and a candidate sees only scores per competency (§6.5; asserted by a schema
test). Values the server decides — user, blueprint, score, pass, deadline, position, focus
count, evidence — are never accepted from the client (`extra="forbid"`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import StrictRequest

AssessmentStatus = Literal[
    "NOT_REQUIRED",
    "REQUIRED",
    "IN_PROGRESS",
    "OPEN_ELSEWHERE",
    "PASSED",
    "RETAKE_LOCKED",
    "FALLBACK_PRACTICE",
    "CLOSED",
    "BLOCKED",
]
BlockedReason = Literal["ACCOUNT_NOT_VERIFIED", "SKILL_NOT_ON_PROFILE"]
FocusEventType = Literal["VISIBILITY_HIDDEN", "FULLSCREEN_EXIT", "WINDOW_BLUR", "PAGE_UNLOAD"]
ResultOutcome = Literal["PASSED", "NOT_PASSED", "ENDED_EARLY", "VOIDED"]


class BlueprintCompetencyOut(BaseModel):
    code: str
    name: str
    weight_bp: int = Field(description="Weight in basis points (10,000 = 100 %).")
    question_count: int
    reasons: list[str] = Field(description="Why this competency is part of the role.")


class BlueprintOut(BaseModel):
    """What the assessment for this role covers (the same for every newcomer)."""

    label: str
    competencies: list[BlueprintCompetencyOut]
    question_count: int
    time_limit_seconds: int = Field(description="Base time; extra time granted to you is separate.")
    extra_time_seconds: int = 0
    pass_overall: int = Field(description="Overall pass mark, 0–100.")
    floor: int = Field(description="Minimum for every competency weighing at least `heavy_weight`.")
    heavy_weight: int = Field(description="Weight (0–100) from which the floor applies.")


class CompetencyScoreOut(BaseModel):
    code: str
    name: str
    weight_bp: int
    score: int = Field(description="0–100, rounded down.")


class AssessmentResultOut(BaseModel):
    """A scored attempt as its candidate sees it: no answers, no per-question correctness."""

    attempt_id: uuid.UUID
    label: str
    outcome: ResultOutcome
    passed: bool
    score: int = Field(description="Overall score 0–100, rounded down.")
    pass_overall: int
    competencies: list[CompetencyScoreOut]
    strongest: str | None
    weakest: str | None
    submitted_at: datetime
    valid_until: datetime | None = Field(description="Until when a pass counts (passed only).")
    next_allowed_at: datetime | None = Field(description="When a new attempt may start.")


class FallbackOut(BaseModel):
    """The slot's newcomer evidence while no role assessment is available (Decision 10)."""

    skill_name: str
    practice_score: int | None = Field(description="Best practice-test result 0–100, if any.")
    passes: bool = Field(description="Whether that result meets the newcomer pass mark.")
    pass_mark: int


class AssessmentStatusOut(BaseModel):
    """Drives the bid sheet's assessment card (§8.1)."""

    status: AssessmentStatus
    reason: BlockedReason | None = None
    message: str
    rules_version: int
    blueprint: BlueprintOut | None = None
    attempt_id: uuid.UUID | None = Field(None, description="Your open attempt (IN_PROGRESS).")
    open_elsewhere: uuid.UUID | None = Field(None, description="Your other open attempt.")
    result: AssessmentResultOut | None = Field(None, description="Your latest result here.")
    next_allowed_at: datetime | None = None
    fallback: FallbackOut | None = None
    bidding_deadline: datetime | None = None
    bidding_closes_soon: bool = Field(
        False, description="Bidding closes before an attempt started now would end (+5 min)."
    )


class StartIn(StrictRequest):
    consent: bool = Field(
        description="The candidate accepted the rules shown on the consent screen."
    )
    rules_version: int = Field(ge=1, le=100)


class QuestionOut(BaseModel):
    """The current question only (one-way navigation, §6.4)."""

    id: uuid.UUID
    index: int = Field(description="0-based position of this question.")
    total: int
    text: str
    code_snippet: str | None = Field(description="Plain text, shown in a monospace block.")
    options: list[str]
    competency: str | None


class AttemptStateOut(BaseModel):
    """An attempt's state; `question` only with a valid window token while open."""

    id: uuid.UUID
    label: str
    state: Literal["OPEN", "SCORED"]
    current_index: int
    total: int
    started_at: datetime
    deadline_at: datetime
    server_now: datetime
    focus_leaves: int
    leave_limit: int
    question: QuestionOut | None = None
    result: AssessmentResultOut | None = None


class StartedOut(AttemptStateOut):
    """A started or resumed attempt with its window token (returned once; send it as
    `X-Attempt-Token` with every answer, focus event and heartbeat)."""

    attempt_token: str


class AnswerIn(StrictRequest):
    question_id: uuid.UUID
    choice: int | None = Field(ge=0, le=3, description="0–3, or null to skip.")


class AnswerOut(BaseModel):
    status: Literal["NEXT", "SCORED"]
    current_index: int
    total: int
    question: QuestionOut | None = None
    result: AssessmentResultOut | None = None


class FocusEventIn(StrictRequest):
    seq: int = Field(ge=1, le=100)
    type: FocusEventType
    client_at: datetime | None = None
    fullscreen_supported: bool | None = None


class FocusEventOut(BaseModel):
    status: Literal["WARNING", "TERMINATED", "CLOSED"]
    focus_leaves: int
    leave_limit: int
    result: AssessmentResultOut | None = None


class HeartbeatIn(StrictRequest):
    visible: bool
    fullscreen: bool


class HeartbeatOut(BaseModel):
    server_now: datetime
    deadline_at: datetime


class HistoryItemOut(BaseModel):
    attempt_id: uuid.UUID
    label: str
    outcome: ResultOutcome
    score: int
    passed: bool
    started_at: datetime
    submitted_at: datetime
    valid_until: datetime | None
