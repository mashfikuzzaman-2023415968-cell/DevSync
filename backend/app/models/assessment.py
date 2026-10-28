"""Role assessment for newcomers (role assessment spec §4): competencies, blueprints, the link
from a project slot to its blueprint, and admin-granted extra time.

Row-level security and the SECURITY DEFINER functions that start, answer and score attempts are
created in migration 0011. Blueprints are immutable once created (trigger), and only the
publish transaction (`create_slot_assessment`) inserts them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.identity import _pg_enum


class QuestionStatus(enum.StrEnum):
    """Role-assessment use of a question; `active` stays the practice-test flag (Decision 15)."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class QuestionSource(enum.StrEnum):
    HUMAN = "HUMAN"
    CLAUDE_GENERATED = "CLAUDE_GENERATED"


class ReviewLevel(enum.StrEnum):
    """Ordered: NONE < SELF_VERIFIED < HUMAN_APPROVED (the enum order in PostgreSQL)."""

    NONE = "NONE"
    SELF_VERIFIED = "SELF_VERIFIED"
    HUMAN_APPROVED = "HUMAN_APPROVED"


class AttemptKind(enum.StrEnum):
    PRACTICE = "PRACTICE"
    ROLE = "ROLE"


class TerminatedReason(enum.StrEnum):
    FOCUS_LIMIT = "FOCUS_LIMIT"  # the two-leave rule ended it: scored, never a pass, flagged
    EXPIRED = "EXPIRED"  # time ran out with no answer at all (reporting only)
    ADMIN_VOID = "ADMIN_VOID"  # an admin voided it while it was still open


class BlueprintStatus(enum.StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class Competency(UUIDPrimaryKey, Timestamps, Base):
    """A competency of a skill (e.g. FastAPI · authentication and authorization)."""

    __tablename__ = "competencies"

    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_core: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        UniqueConstraint("skill_id", "code"),
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{2,40}$'", name="code_format"),
        CheckConstraint("char_length(name) BETWEEN 3 AND 60", name="name_len"),
        CheckConstraint("char_length(description) <= 300", name="description_len"),
        CheckConstraint("cardinality(keywords) BETWEEN 1 AND 40", name="keywords_count"),
    )


class AssessmentBlueprint(UUIDPrimaryKey, Base):
    """What a role assessment covers; shared by every slot with the same fingerprint."""

    __tablename__ = "assessment_blueprints"

    algo_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    primary_skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # [{competency_id, code, name, weight_bp, question_count, easy, medium, hard, reasons}]
    competencies: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    question_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty_mix: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    pass_rule: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    status: Mapped[BlueprintStatus] = mapped_column(
        _pg_enum(BlueprintStatus, "blueprint_status"), nullable=False
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint_format"),
        CheckConstraint("question_count BETWEEN 1 AND 50", name="count_range"),
        CheckConstraint("time_limit_seconds BETWEEN 60 AND 7200", name="time_range"),
        CheckConstraint(
            "(status = 'UNAVAILABLE') = (unavailable_reason IS NOT NULL)",
            name="reason_iff_unavailable",
        ),
    )


class SlotAssessment(Base):
    """The blueprint of one project slot, fixed when the project is published."""

    __tablename__ = "slot_assessments"

    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_slots.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blueprint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_blueprints.id"), nullable=False
    )
    requirements_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserAccommodation(Base):
    """Extra assessment time granted by an admin (role assessment spec §12.3)."""

    __tablename__ = "user_accommodations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    extra_time_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("extra_time_pct IN (0, 25, 50)", name="extra_time_values"),
        CheckConstraint("char_length(note) <= 300", name="note_len"),
    )
