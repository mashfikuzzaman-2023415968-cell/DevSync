"""One payload schema per evidence event type (spec §9.1.6; DECISIONS D149).

All 22 catalogue types are here, including the ones Phases 10–13 emit, so every write is
validated from the start. Payloads carry ids, states and hours, never money, days or reasons
(every participant reads the activity feed, and D130 keeps prices sealed among members).
Which event carries which §9.1.4–9.1.5 input is listed in `docs/plans/phase-09.md`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.workspace_types import ACTIVITY_TYPES, EvidenceKind, TaskStatus

Hours = Annotated[Decimal, Field(gt=0, le=Decimal("999.9"), decimal_places=1)]


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CheckinPosted(_Event):
    checkin_id: uuid.UUID
    week_start: date
    on_time: bool
    has_blockers: bool


class CheckinMissed(_Event):
    week_start: date


class CommentPosted(_Event):
    comment_id: uuid.UUID
    target_type: Literal["TASK", "MILESTONE", "CHECKIN", "DISCUSSION_POST"]
    target_id: uuid.UUID
    mentions: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class CommentReplied(_Event):
    comment_id: uuid.UUID
    reply_to_id: uuid.UUID
    to_author_id: uuid.UUID
    response_seconds: int = Field(ge=0)


class _TaskFacts(_Event):
    """What §9.13 and §9.1.1 need: the task, its milestone, who it was credited to, its size."""

    task_id: uuid.UUID
    milestone_id: uuid.UUID
    assignee_id: uuid.UUID | None
    estimate_hours: Hours


class TaskMoved(_TaskFacts):
    from_status: TaskStatus
    to_status: TaskStatus


class TaskDone(_TaskFacts):
    pass


class TaskReopened(_TaskFacts):
    to_status: TaskStatus


class TaskEvidenceAdded(_Event):
    task_id: uuid.UUID
    evidence_id: uuid.UUID
    kind: EvidenceKind


class WorkStarted(_Event):
    task_id: uuid.UUID
    milestone_id: uuid.UUID


class MilestoneEvent(_Event):
    """submitted / approved / changes_requested / auto_approved (Phase 10)."""

    milestone_id: uuid.UUID
    round: int = Field(ge=1, le=100)


class BlockerReported(_Event):
    checkin_id: uuid.UUID


class BlockerAnswered(_Event):
    checkin_id: uuid.UUID
    comment_id: uuid.UUID
    reporter_id: uuid.UUID


class GithubEvent(_Event):
    """pr_merged / review_given (Phase 13)."""

    repo: str = Field(min_length=1, max_length=200)
    pr_number: int = Field(ge=1)


class SplitEvent(_Event):
    """proposed / agreed / objected (Phase 10): ids only, never the shares."""

    milestone_id: uuid.UUID
    split_id: uuid.UUID


class MemberLeft(_Event):
    member_id: uuid.UUID
    slot_label: str = Field(min_length=1, max_length=120)
    how: Literal["LEFT", "REMOVED"]


class MemberReplaced(_Event):
    member_id: uuid.UUID
    slot_label: str = Field(min_length=1, max_length=120)


SCHEMAS: dict[str, type[_Event]] = {
    "checkin.posted": CheckinPosted,
    "checkin.missed": CheckinMissed,
    "comment.posted": CommentPosted,
    "comment.replied": CommentReplied,
    "task.moved": TaskMoved,
    "task.done": TaskDone,
    "task.reopened": TaskReopened,
    "task.evidence_added": TaskEvidenceAdded,
    "milestone.submitted": MilestoneEvent,
    "milestone.approved": MilestoneEvent,
    "milestone.changes_requested": MilestoneEvent,
    "milestone.auto_approved": MilestoneEvent,
    "work.started": WorkStarted,
    "blocker.reported": BlockerReported,
    "blocker.answered": BlockerAnswered,
    "github.pr_merged": GithubEvent,
    "github.review_given": GithubEvent,
    "split.proposed": SplitEvent,
    "split.agreed": SplitEvent,
    "split.objected": SplitEvent,
    "member.left": MemberLeft,
    "member.replaced": MemberReplaced,
}

if set(SCHEMAS) != set(ACTIVITY_TYPES):  # import-time guard: the catalogue and schemas agree
    raise RuntimeError("activity schemas don't match the §9.1.6 catalogue")


class InvalidEventError(ValueError):
    """An unknown event type or a payload that doesn't match its schema."""


def validate_event_data(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """The payload as stored (JSON-ready), or InvalidEventError."""
    schema = SCHEMAS.get(event_type)
    if schema is None:
        raise InvalidEventError(f"unknown activity type {event_type!r}")
    try:
        return schema.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        raise InvalidEventError(
            f"invalid {event_type} payload: {exc.error_count()} error(s)"
        ) from exc
