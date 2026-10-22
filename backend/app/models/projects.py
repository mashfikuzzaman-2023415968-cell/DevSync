"""Projects, slots, milestones, dependencies and plan baselines (spec §7.3).

Row-level security for these tables is created in migration 0005: a draft project and its plan
are visible only to its client and admins; once it leaves DRAFT the project and plan rows are
visible to everyone (the public marketplace reads a limited-column view). The full
`project_status`/`milestone_status` enums from spec §8 are defined now, though Phase 4 only drives
the planning transitions (DRAFT ↔ edit, DRAFT → BIDDING, BIDDING → BIDDING, → CANCELLED); later
phases add the rest (DECISIONS D38).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.identity import _pg_enum


class ProjectStatus(enum.StrEnum):
    """Project lifecycle (spec §8). Phase 4 uses DRAFT, BIDDING and CANCELLED."""

    DRAFT = "DRAFT"
    BIDDING = "BIDDING"
    FORMING = "FORMING"
    TEAM_PENDING = "TEAM_PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    REVIEW_WINDOW = "REVIEW_WINDOW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MilestoneStatus(enum.StrEnum):
    """Milestone lifecycle (spec §8). Phase 4 creates milestones as PLANNED."""

    PLANNED = "PLANNED"
    FUNDED = "FUNDED"
    ACTIVE = "ACTIVE"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    AUTO_APPROVED = "AUTO_APPROVED"
    PAID = "PAID"
    DISPUTED = "DISPUTED"
    REFUNDED = "REFUNDED"


class PlanChangeStatus(enum.StrEnum):
    """State of a proposed plan change after a team is confirmed."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Project(UUIDPrimaryKey, Timestamps, Base):
    """A client's software project and its budget, deadline and team shape (spec §7.3)."""

    __tablename__ = "projects"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    requirements: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    budget_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bonus_pool_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    deadline_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    bidding_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    team_size: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        _pg_enum(ProjectStatus, "project_status"),
        nullable=False,
        server_default=ProjectStatus.DRAFT.value,
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repo_url: Mapped[str | None] = mapped_column(Text)
    settings_version: Mapped[int | None] = mapped_column(Integer)
    # App-managed pointer to the active baseline; no DB foreign key (it would be circular with
    # plan_baselines.project_id and complicate migration ordering).
    current_baseline_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    bidding_extensions: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # Minimum standards for this project's Algorithm 1 filter when the client lowered them
    # through the too-few-bids actions (§9.19); NULL = platform `filter.P0` / `filter.C0`.
    min_performance: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    min_competency: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    # Full-text search over title + summary (Phase 5 marketplace, migration 0006); skills are a
    # structured filter joined at query time. Generated/persisted so it can't drift from the text.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(summary, ''))",
            persisted=True,
        ),
    )

    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 5 AND 120", name="title_len"),
        CheckConstraint("char_length(summary) <= 300", name="summary_len"),
        CheckConstraint("char_length(description) <= 10000", name="description_len"),
        CheckConstraint("char_length(requirements) <= 5000", name="requirements_len"),
        CheckConstraint("budget_paisa >= 0", name="budget_nonneg"),
        CheckConstraint("bonus_pool_paisa >= 0", name="bonus_pool_nonneg"),
        CheckConstraint("deadline_days BETWEEN 1 AND 365", name="deadline_range"),
        CheckConstraint("team_size BETWEEN 2 AND 10", name="team_size_range"),
        CheckConstraint("bidding_extensions >= 0", name="extensions_nonneg"),
        CheckConstraint(
            "min_performance IS NULL OR (min_performance >= 0 AND min_performance <= 1)",
            name="min_performance_range",
        ),
        CheckConstraint(
            "min_competency IS NULL OR (min_competency >= 0 AND min_competency <= 1)",
            name="min_competency_range",
        ),
        Index("ix_projects_status_bidding_deadline", "status", "bidding_deadline"),
        Index("ix_projects_client_id", "client_id"),
        Index("ix_projects_search", "search_vector", postgresql_using="gin"),
    )


class ProjectSlot(UUIDPrimaryKey, Timestamps, Base):
    """A required skill position in the team; Σ count = team_size (enforced in the service)."""

    __tablename__ = "project_slots"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("count >= 1", name="count_positive"),
        Index("ix_project_slots_project_id", "project_id"),
        Index("ix_project_slots_skill_id", "skill_id"),
    )


class Milestone(UUIDPrimaryKey, Timestamps, Base):
    """A planned unit of work with a duration, payment share and skills (spec §7.3)."""

    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    duration_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    share_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[MilestoneStatus] = mapped_column(
        _pg_enum(MilestoneStatus, "milestone_status"),
        nullable=False,
        server_default=MilestoneStatus.PLANNED.value,
    )
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_finish: Mapped[date | None] = mapped_column(Date)
    revision_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_approve_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="name_len"),
        CheckConstraint("duration_days >= 1", name="duration_positive"),
        CheckConstraint("share_bp BETWEEN 0 AND 10000", name="share_range"),
        CheckConstraint("revision_count >= 0", name="revision_nonneg"),
        Index("ix_milestones_project_id_position", "project_id", "position"),
    )


class MilestoneSkill(UUIDPrimaryKey, Timestamps, Base):
    """A skill a milestone needs (used by CPM slot coverage and the risk engine)."""

    __tablename__ = "milestone_skills"

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("milestone_id", "skill_id", name="milestone_skill"),
        Index("ix_milestone_skills_milestone_id", "milestone_id"),
        Index("ix_milestone_skills_skill_id", "skill_id"),
    )


class MilestoneDependency(UUIDPrimaryKey, Timestamps, Base):
    """A finish-to-start edge: `successor` cannot start until `predecessor` finishes.

    Acyclicity is enforced in the service via CPM validation (spec §9.10); the database guards
    against self-loops and duplicate edges.
    """

    __tablename__ = "milestone_dependencies"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    predecessor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False
    )
    successor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("predecessor_id", "successor_id", name="edge"),
        CheckConstraint("predecessor_id <> successor_id", name="no_self_loop"),
        Index("ix_milestone_dependencies_project_id", "project_id"),
        Index("ix_milestone_dependencies_predecessor_id", "predecessor_id"),
        Index("ix_milestone_dependencies_successor_id", "successor_id"),
    )


class PlanBaseline(UUIDPrimaryKey, Timestamps, Base):
    """Immutable snapshot of the approved CPM plan (spec §7.3); v1 written at publish."""

    __tablename__ = "plan_baselines"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    cpm: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_client: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    approved_by_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("project_id", "version", name="project_version"),
        Index("ix_plan_baselines_project_id", "project_id"),
    )


class PlanChangeRequest(UUIDPrimaryKey, Timestamps, Base):
    """A proposed change to the plan after the team is confirmed (needs client + lead approval)."""

    __tablename__ = "plan_change_requests"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[PlanChangeStatus] = mapped_column(
        _pg_enum(PlanChangeStatus, "plan_change_status"),
        nullable=False,
        server_default=PlanChangeStatus.PENDING.value,
    )

    __table_args__ = (Index("ix_plan_change_requests_project_id", "project_id"),)
