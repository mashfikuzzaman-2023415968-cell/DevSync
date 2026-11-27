"""Task, dependency and evidence contracts (spec §7.5, §8 Task, §10.2 Tasks; D143, D144, D148,
D168, D172). Requests forbid unknown fields, so `status` on create, `position`, `progress_pct`,
`project_id`, `created_by` and the like are refused with 422 (mass assignment, §14.5)."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from app.models.workspace import EvidenceKind, TaskDifficulty, TaskStatus
from app.schemas.common import StrictRequest

MAX_DEPENDENCIES = 20  # per task (D143, a D63-style cap)
MAX_EVIDENCE = 20  # per task
MAX_TASKS_PER_PROJECT = 1000

PR_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[0-9]+$")

Title = Annotated[str, Field(min_length=1, max_length=160)]
Description = Annotated[str, Field(max_length=5000)]
Estimate = Annotated[Decimal, Field(gt=0, le=Decimal("999.9"), decimal_places=1, max_digits=4)]


class PersonRef(BaseModel):
    """A participant shown on a card: their user id and display name only."""

    id: uuid.UUID
    name: str


class TaskRef(BaseModel):
    id: uuid.UUID
    title: str
    status: TaskStatus


class TaskCard(BaseModel):
    id: uuid.UUID
    milestone_id: uuid.UUID
    title: str
    status: TaskStatus
    assignee: PersonRef | None
    deadline: date | None
    estimate_hours: Decimal
    difficulty: TaskDifficulty
    position: str
    progress_pct: int = Field(ge=0, le=100)
    blocked_by: int = Field(ge=0, description="Dependencies that aren't done yet")
    evidence_count: int = Field(ge=0)
    comment_count: int = Field(ge=0)
    last_activity_at: datetime
    version: int


class EvidenceOut(BaseModel):
    id: uuid.UUID
    kind: EvidenceKind
    url: str | None
    file_id: uuid.UUID | None
    file_name: str | None
    note: str | None
    added_by: PersonRef
    created_at: datetime


class MoveOption(BaseModel):
    """Whether the caller may move the task to `status` now, and why not (§13.5 refused
    drop targets say why)."""

    status: TaskStatus
    allowed: bool
    reason: str | None = None


class TaskDetail(TaskCard):
    description: str
    created_by: PersonRef
    dependencies: list[TaskRef]
    dependents: list[TaskRef]
    evidence: list[EvidenceOut]
    can_move_to: list[MoveOption]
    can_edit: bool


class TaskCreate(StrictRequest):
    title: Title
    description: Description = ""
    assignee_id: uuid.UUID | None = None
    deadline: date | None = None
    estimate_hours: Estimate
    difficulty: TaskDifficulty
    depends_on_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_DEPENDENCIES)

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if len(set(self.depends_on_ids)) != len(self.depends_on_ids):
            raise ValueError("depends_on_ids lists a task twice")
        return self


class TaskPatch(StrictRequest):
    """Only the fields sent change; `assignee_id: null` unassigns, `deadline: null` clears."""

    title: Title | None = None
    description: Description | None = None
    assignee_id: uuid.UUID | None = None
    deadline: date | None = None
    estimate_hours: Estimate | None = None
    difficulty: TaskDifficulty | None = None
    milestone_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        for name in ("title", "description", "estimate_hours", "difficulty", "milestone_id"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} can't be empty")
        return self


class TaskMove(StrictRequest):
    """Move to `status` (one step, or the same column to reorder), between two cards of that
    column: `after_id` is the card above, `before_id` the card below (both optional)."""

    status: TaskStatus
    after_id: uuid.UUID | None = None
    before_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _different(self) -> Self:
        if self.after_id is not None and self.after_id == self.before_id:
            raise ValueError("after_id and before_id must be different cards")
        return self


class DependencyCreate(StrictRequest):
    depends_on_task_id: uuid.UUID


class TaskDependencyOut(BaseModel):
    task_id: uuid.UUID
    depends_on_task_id: uuid.UUID


class EvidenceCreate(StrictRequest):
    """FILE / SCREENSHOT name a project file; LINK / PR an https URL that is never fetched."""

    kind: EvidenceKind
    url: Annotated[str, Field(max_length=2048)] | None = None
    file_id: uuid.UUID | None = None
    note: Annotated[str, Field(max_length=500)] | None = None

    @model_validator(mode="after")
    def _shape(self) -> Self:
        needs_file = self.kind in (EvidenceKind.FILE, EvidenceKind.SCREENSHOT)
        if needs_file and (self.file_id is None or self.url is not None):
            raise ValueError("file and screenshot evidence name a project file (file_id) only")
        if not needs_file:
            if self.url is None or self.file_id is not None:
                raise ValueError("link and PR evidence give a url only")
            if not self.url.startswith("https://"):
                raise ValueError("links must start with https://")
            if self.kind == EvidenceKind.PR and not PR_URL.match(self.url):
                raise ValueError(
                    "a PR link looks like https://github.com/<owner>/<repo>/pull/<number>"
                )
        if self.note == "":
            self.note = None
        return self


EX_PERSON = {"id": "5f0c6c1e-2a43-4d9b-9a53-0a1f5a1b2c3d", "name": "Nusrat Jahan"}
EX_TASK_CARD = {
    "id": "9b2e7d4a-6c1f-4a8e-b3d2-1f0e9c8b7a65",
    "milestone_id": "2d4f6a8c-1b3d-4e5f-8a7b-9c0d1e2f3a4b",
    "title": "Stock list API",
    "status": "IN_PROGRESS",
    "assignee": EX_PERSON,
    "deadline": "2026-11-20",
    "estimate_hours": "8.0",
    "difficulty": "MEDIUM",
    "position": "V",
    "progress_pct": 50,
    "blocked_by": 0,
    "evidence_count": 1,
    "comment_count": 2,
    "last_activity_at": "2026-11-18T05:30:00Z",
    "version": 3,
}
EX_TASK_DETAIL = {
    **EX_TASK_CARD,
    "description": "List stock with filters by warehouse and low stock.",
    "created_by": {"id": "7a6b5c4d-3e2f-4a1b-9c8d-7e6f5a4b3c2d", "name": "Arif Hossain"},
    "dependencies": [],
    "dependents": [],
    "evidence": [
        {
            "id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
            "kind": "PR",
            "url": "https://github.com/acme/inventory/pull/12",
            "file_id": None,
            "file_name": None,
            "note": "Filters and paging",
            "added_by": EX_PERSON,
            "created_at": "2026-11-18T05:30:00Z",
        }
    ],
    "can_move_to": [
        {"status": "TODO", "allowed": True, "reason": None},
        {"status": "REVIEW", "allowed": True, "reason": None},
        {"status": "DONE", "allowed": False, "reason": "Move it to Review first."},
    ],
    "can_edit": False,
}
EX_TASK_PAGE = {"items": [EX_TASK_CARD], "next_cursor": None}
EX_DEPENDENCY = {
    "task_id": "9b2e7d4a-6c1f-4a8e-b3d2-1f0e9c8b7a65",
    "depends_on_task_id": "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
}
EX_EVIDENCE = EX_TASK_DETAIL["evidence"][0]  # type: ignore[index]
