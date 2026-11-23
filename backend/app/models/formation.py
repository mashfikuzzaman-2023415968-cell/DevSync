"""Team formation tables (spec §7.4; migration 0014).

- `formation_runs`: one optimisation run with its frozen inputs (parameters, seed, settings
  version, candidate snapshot) and its result. The inputs are immutable after insert (a trigger
  refuses changes), so a run can always be reproduced and audited (§14.13 row 7, FR-TEAM-6).
- `bid_explanations`: "why not selected" per bid per run — visible only to the bidder and admins.
- `teams`, `team_members`, `invitations`: created when the client confirms a run. In Phase 7 the
  invitations are recorded but not sent (D108); Phase 8 sends them and handles the answers.

The enums carry Phase 8's values too (D38's rule: create full enums up front, because
`ALTER TYPE … ADD VALUE` can't run inside a migration's transaction). Only SYSTEM writes these
tables; services authorise the caller first (D50 pattern).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.identity import _pg_enum


class RunStatus(enum.StrEnum):
    """Formation run lifecycle (spec §8)."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    INFEASIBLE = "INFEASIBLE"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"  # returns the best feasible team found, if any


class TeamStatus(enum.StrEnum):
    PENDING = "PENDING"  # confirmed, invitations outstanding (project TEAM_PENDING)
    ACTIVE = "ACTIVE"  # every slot accepted and a lead chosen (Phase 8)
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MemberStatus(enum.StrEnum):
    """Team member (spec §8: INVITED → ACTIVE → COMPLETED | LEFT | REMOVED; plus the answers)."""

    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"
    LEFT = "LEFT"
    REMOVED = "REMOVED"


class InvitationResponse(enum.StrEnum):
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


class FormationRun(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "formation_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[RunStatus] = mapped_column(
        _pg_enum(RunStatus, "run_status"), nullable=False, server_default=RunStatus.QUEUED.value
    )
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    candidate_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    runtime_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("seed >= 0", name="seed_non_negative"),
        CheckConstraint("runtime_ms IS NULL OR runtime_ms >= 0", name="runtime_non_negative"),
        CheckConstraint("char_length(error_code) <= 64", name="error_code_length"),
        Index("ix_formation_runs_project_created", "project_id", "created_at"),
        Index("ix_formation_runs_job", "job_id"),
    )


class BidExplanation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "bid_explanations"

    bid_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bids.id"), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("formation_runs.id"), nullable=False)
    reasons: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    price_counterfactual_paisa: Mapped[int | None] = mapped_column(BigInteger)
    main_gap: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("bid_id", "run_id", name="uq_bid_explanations_bid_run"),
        CheckConstraint(
            "price_counterfactual_paisa IS NULL OR price_counterfactual_paisa > 0",
            name="counterfactual_positive",
        ),
        CheckConstraint(
            "main_gap IS NULL OR main_gap IN ('comp', 'team', 'time', 'cost')",
            name="main_gap_known",
        ),
        Index("ix_bid_explanations_run", "run_id"),
    )


class Team(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "teams"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False, unique=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("formation_runs.id"), nullable=False)
    status: Mapped[TeamStatus] = mapped_column(
        _pg_enum(TeamStatus, "team_status"),
        nullable=False,
        server_default=TeamStatus.PENDING.value,
    )
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_teams_run", "run_id"),)


class TeamMember(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    developer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    bid_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bids.id"), nullable=False, unique=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_slots.id"), nullable=False)
    price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    days_needed: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[MemberStatus] = mapped_column(
        _pg_enum(MemberStatus, "member_status"),
        nullable=False,
        server_default=MemberStatus.INVITED.value,
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("team_id", "developer_id", name="uq_team_members_team_developer"),
        CheckConstraint("price_paisa >= 0", name="price_non_negative"),
        CheckConstraint("days_needed >= 1", name="days_positive"),
        CheckConstraint("char_length(left_reason) <= 500", name="left_reason_length"),
        Index("ix_team_members_developer", "developer_id"),
        Index("ix_team_members_slot", "slot_id"),
        # §7.9: one lead per team among active members.
        Index(
            "one_active_lead_per_team",
            "team_id",
            unique=True,
            postgresql_where=text(  # forbidden-ok: constant DDL predicate
                "is_lead AND status = 'ACTIVE'"
            ),
        ),
    )


class Invitation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "invitations"

    team_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id"), nullable=False, unique=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response: Mapped[InvitationResponse | None] = mapped_column(
        _pg_enum(InvitationResponse, "invitation_response")
    )
    is_replacement: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        # Not sent ⇔ no expiry (D108: Phase 8 sends and starts the 48 h clock).
        CheckConstraint("(sent_at IS NULL) = (expires_at IS NULL)", name="expiry_iff_sent"),
        CheckConstraint(
            "(responded_at IS NULL) = (response IS NULL)", name="response_iff_answered"
        ),
    )
