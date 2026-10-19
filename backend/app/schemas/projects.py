"""Request and response schemas for projects and the CPM planner (spec §7.3, §10.2 Projects).

Request bodies extend `StrictRequest` (unknown fields rejected, §14.5) and mirror the database
bounds so most invalid input is a 422 before it reaches a service. Money fields are integer paisa.
The plan-preview schemas use client-supplied milestone `key`s so the wizard can run CPM on an
unsaved plan; the persisted plan (PUT milestones/dependencies) references database ids.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import StrictRequest

# Shared field annotations (kept in sync with the DB CHECK constraints in migration 0005).
Title = Field(min_length=5, max_length=120)
Summary = Field(default="", max_length=300)
Description = Field(default="", max_length=10000)
Requirements = Field(default="", max_length=5000)
BudgetPaisa = Field(ge=0, le=10_000_000_000)
BonusPoolPaisa = Field(default=0, ge=0, le=10_000_000_000)
DeadlineDays = Field(ge=1, le=365)
TeamSize = Field(ge=2, le=10)
MilestoneName = Field(min_length=1, max_length=160)
MilestoneDesc = Field(default="", max_length=5000)
DurationDays = Field(ge=1, le=365)
ShareBp = Field(ge=0, le=10_000)
Count = Field(default=1, ge=1)
MAX_MILESTONES = 300
MAX_SLOTS = 20


# --------------------------------------------------------------------------- projects


class ProjectCreate(StrictRequest):
    """Create a DRAFT project (spec §10.2 POST /projects)."""

    title: str = Title
    summary: str = Summary
    description: str = Description
    requirements: str = Requirements
    budget_paisa: int = BudgetPaisa
    bonus_pool_paisa: int = BonusPoolPaisa
    deadline_days: int = DeadlineDays
    team_size: int = TeamSize
    start_date: date | None = None
    bidding_deadline: datetime | None = None


class ProjectUpdate(StrictRequest):
    """Patch a DRAFT project's fields (all optional)."""

    title: str | None = Field(default=None, min_length=5, max_length=120)
    summary: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    requirements: str | None = Field(default=None, max_length=5000)
    budget_paisa: int | None = Field(default=None, ge=0, le=10_000_000_000)
    bonus_pool_paisa: int | None = Field(default=None, ge=0, le=10_000_000_000)
    deadline_days: int | None = Field(default=None, ge=1, le=365)
    team_size: int | None = Field(default=None, ge=2, le=10)
    start_date: date | None = None
    bidding_deadline: datetime | None = None


class ProjectOut(BaseModel):
    """A project as returned to its client (spec §7.3)."""

    id: uuid.UUID
    client_id: uuid.UUID
    title: str
    summary: str
    description: str
    requirements: str
    budget_paisa: int
    bonus_pool_paisa: int
    deadline_days: int
    team_size: int
    start_date: date | None
    bidding_deadline: datetime | None
    status: str
    cancel_reason: str | None
    bidding_extensions: int
    current_baseline_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectListItem(BaseModel):
    """A row in the client's project list."""

    id: uuid.UUID
    title: str
    status: str
    budget_paisa: int
    team_size: int
    deadline_days: int
    bidding_deadline: datetime | None
    updated_at: datetime


# --------------------------------------------------------------------------- slots


class SlotIn(StrictRequest):
    """One required skill position in the team."""

    skill_id: uuid.UUID
    label: str = Field(default="", max_length=120)
    count: int = Count


class SlotsReplace(StrictRequest):
    """Whole-set replace of a project's slots (Σ count must equal team_size)."""

    slots: list[SlotIn] = Field(max_length=MAX_SLOTS)


class SlotOut(BaseModel):
    """A stored slot."""

    id: uuid.UUID
    skill_id: uuid.UUID
    label: str
    count: int


# --------------------------------------------------------------------------- milestones


class MilestoneIn(StrictRequest):
    """A milestone in a whole-set replace; `id` is present for an existing milestone."""

    id: uuid.UUID | None = None
    name: str = MilestoneName
    description: str = MilestoneDesc
    duration_days: int = DurationDays
    share_bp: int = ShareBp
    skill_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)


class MilestonesReplace(StrictRequest):
    """Whole-set replace of a project's milestones (Σ share_bp must equal 10000)."""

    milestones: list[MilestoneIn] = Field(max_length=MAX_MILESTONES)


class MilestoneOut(BaseModel):
    """A stored milestone."""

    id: uuid.UUID
    name: str
    description: str
    duration_days: int
    share_bp: int
    position: int
    status: str
    skill_ids: list[uuid.UUID]


# --------------------------------------------------------------------------- dependencies


class DependencyIn(StrictRequest):
    """A finish-to-start edge between two of the project's milestones (by id)."""

    predecessor_id: uuid.UUID
    successor_id: uuid.UUID


class DependenciesReplace(StrictRequest):
    """Whole-set replace of a project's milestone dependencies (acyclic; checked by CPM)."""

    dependencies: list[DependencyIn] = Field(max_length=MAX_MILESTONES * 4)


class DependencyOut(BaseModel):
    """A stored dependency edge."""

    id: uuid.UUID
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID


# --------------------------------------------------------------------------- plan preview / CPM


class PreviewMilestone(StrictRequest):
    """A milestone in an unsaved plan, identified by a client `key` for dependency references."""

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=160)
    duration_days: int = DurationDays
    share_bp: int = ShareBp
    predecessor_keys: list[str] = Field(default_factory=list, max_length=MAX_MILESTONES)


class PlanPreviewIn(StrictRequest):
    """Run CPM on an unsaved plan to preview the timeline and warnings (no persistence)."""

    milestones: list[PreviewMilestone] = Field(max_length=MAX_MILESTONES)
    team_size: int | None = Field(default=None, ge=2, le=10)
    slot_count: int | None = Field(default=None, ge=0)


class CpmNodeOut(BaseModel):
    """Schedule of one milestone (day offsets from project start)."""

    key: str
    name: str
    es: int
    ef: int
    ls: int
    lf: int
    slack: int
    critical: bool


class CpmPreviewOut(BaseModel):
    """CPM result for a plan: schedule, duration, all critical paths and plan warnings."""

    feasible: bool
    duration: int
    nodes: list[CpmNodeOut]
    critical_paths: list[list[str]]
    cycle: list[str] | None = None
    total_share_bp: int
    warnings: list[str]


class PlanEdge(BaseModel):
    """A finish-to-start dependency between two plan nodes (by node key)."""

    predecessor: str
    successor: str


class PlanOut(BaseModel):
    """The saved baseline plan: CPM schedule and critical paths (GET /projects/{id}/plan)."""

    baseline_version: int | None
    duration: int
    nodes: list[CpmNodeOut]
    edges: list[PlanEdge]
    critical_paths: list[list[str]]
    deadline_days: int
    exceeds_deadline: bool


# --------------------------------------------------------------------------- transitions


class PublishIn(StrictRequest):
    """Publish a DRAFT for bidding; acknowledge schedule risk if CPM > deadline (D40)."""

    acknowledge_schedule_risk: bool = False


class CancelIn(StrictRequest):
    """Cancel a project with a reason (spec §8 cancellation rules)."""

    reason: str = Field(min_length=1, max_length=500)


class ExtendBiddingIn(StrictRequest):
    """Extend the bidding deadline (max 2 times, spec §8)."""

    days: int | None = Field(default=None, ge=1, le=30)
