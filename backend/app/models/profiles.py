"""Profiles, skills, files, portfolio, evidence and timed skill tests (spec §7.2, §7.7, §14.9).

Row-level security for these tables is created in migration 0004. `question_bank` is readable by
admins and SYSTEM only; web requests read questions through SECURITY DEFINER functions that never
return the correct answer.
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
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.assessment import (
    AttemptKind,
    QuestionSource,
    QuestionStatus,
    ReviewLevel,
    TerminatedReason,
)
from app.models.identity import _pg_enum


class SkillDomain(enum.StrEnum):
    """Skill domains (used for the expertise diversity ω, Eq. 1)."""

    FRONTEND = "FRONTEND"
    BACKEND = "BACKEND"
    DATABASE = "DATABASE"
    MOBILE = "MOBILE"
    DESIGN = "DESIGN"
    TESTING = "TESTING"
    DEVOPS = "DEVOPS"
    DATA = "DATA"


class ProfileVisibility(enum.StrEnum):
    """Who can see a developer's profile."""

    PUBLIC = "PUBLIC"
    CLIENTS_ONLY = "CLIENTS_ONLY"


class FileKind(enum.StrEnum):
    """What an uploaded file is for (decides the allowed types)."""

    PORTFOLIO_IMAGE = "PORTFOLIO_IMAGE"
    CERTIFICATE = "CERTIFICATE"
    EXTERNAL_REVIEW = "EXTERNAL_REVIEW"


class ScanStatus(enum.StrEnum):
    """Result of the optional malware scan hook (§14.9)."""

    SKIPPED = "SKIPPED"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"


class VerificationStatus(enum.StrEnum):
    """Admin verification of certificates and external reviews."""

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class EvidenceSource(enum.StrEnum):
    """Where verified skill evidence came from."""

    TEST = "TEST"  # a practice test (role assessment spec Decision 1)
    CODING = "CODING"
    ADMIN_PORTFOLIO = "ADMIN_PORTFOLIO"
    ROLE_ASSESSMENT = "ROLE_ASSESSMENT"  # one row per scored role attempt, passed or not


class Skill(UUIDPrimaryKey, Timestamps, Base):
    """Skill taxonomy entry (admin-managed; public)."""

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    domain: Mapped[SkillDomain] = mapped_column(
        _pg_enum(SkillDomain, "skill_domain"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="name_len"),)


class DeveloperProfile(UUIDPrimaryKey, Timestamps, Base):
    """A developer's public-facing profile."""

    __tablename__ = "developer_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    headline: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    bio: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    hours_per_week: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="20")
    github_username: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Dhaka")
    visibility: Mapped[ProfileVisibility] = mapped_column(
        _pg_enum(ProfileVisibility, "profile_visibility"),
        nullable=False,
        server_default=ProfileVisibility.PUBLIC.value,
    )
    # Optimistic concurrency (If-Match, spec §10.1); bumped on every saved change.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("char_length(headline) <= 120", name="headline_len"),
        CheckConstraint("char_length(bio) <= 2000", name="bio_len"),
        CheckConstraint("hours_per_week BETWEEN 1 AND 80", name="hours_range"),
        CheckConstraint(
            "github_username IS NULL OR "
            "github_username ~ '^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$'",
            name="github_username_format",
        ),
    )


class DeveloperSkill(UUIDPrimaryKey, Timestamps, Base):
    """A skill a developer claims, with a self-assessed level (verified scores are evidence)."""

    __tablename__ = "developer_skills"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), nullable=False, index=True)
    self_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_developer_skills_user_skill"),
        CheckConstraint("self_level BETWEEN 1 AND 5", name="level_range"),
    )


class ClientProfile(UUIDPrimaryKey, Timestamps, Base):
    """A client's organisation details."""

    __tablename__ = "client_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    organization: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    website: Mapped[str | None] = mapped_column(Text)
    # Optimistic concurrency (If-Match, spec §10.1); bumped on every saved change.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("char_length(organization) <= 120", name="organization_len"),
        CheckConstraint("char_length(description) <= 2000", name="description_len"),
        CheckConstraint(
            "website IS NULL OR (website ~ '^https://' AND char_length(website) <= 300)",
            name="website_https",
        ),
    )


class StoredFile(UUIDPrimaryKey, Timestamps, Base):
    """An uploaded file (§14.9). Stored under a random key outside the web root; the original
    name is sanitized metadata only. `attached_at` is set once something references it; files
    never attached are deleted after 24 h."""

    __tablename__ = "files"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[FileKind] = mapped_column(_pg_enum(FileKind, "file_kind"), nullable=False)
    storage_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    scan_status: Mapped[ScanStatus] = mapped_column(
        _pg_enum(ScanStatus, "scan_status"), nullable=False, server_default=ScanStatus.SKIPPED.value
    )
    attached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("char_length(original_name) BETWEEN 1 AND 200", name="name_len"),
    )


class PortfolioItem(UUIDPrimaryKey, Timestamps, Base):
    """A piece of work a developer shows (≤ 20 per developer)."""

    __tablename__ = "portfolio_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    url: Mapped[str | None] = mapped_column(Text)
    skill_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 120", name="title_len"),
        CheckConstraint("char_length(description) <= 2000", name="description_len"),
        CheckConstraint(
            "url IS NULL OR (url ~ '^https://' AND char_length(url) <= 300)", name="url_https"
        ),
        CheckConstraint("position BETWEEN 0 AND 19", name="position_range"),
        CheckConstraint("cardinality(skill_ids) <= 8", name="skills_max"),
    )


class PortfolioImage(UUIDPrimaryKey, Timestamps, Base):
    """An image of a portfolio item (≤ 5 per item)."""

    __tablename__ = "portfolio_images"

    portfolio_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"), unique=True, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    __table_args__ = (CheckConstraint("position BETWEEN 0 AND 4", name="position_range"),)


class Certificate(UUIDPrimaryKey, Timestamps, Base):
    """A certificate a developer uploads for admin verification."""

    __tablename__ = "certificates"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"), unique=True, nullable=False)
    status: Mapped[VerificationStatus] = mapped_column(
        _pg_enum(VerificationStatus, "verification_status"),
        nullable=False,
        server_default=VerificationStatus.PENDING.value,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 120", name="title_len"),
        CheckConstraint("char_length(issuer) BETWEEN 1 AND 120", name="issuer_len"),
    )


class ExternalReview(UUIDPrimaryKey, Timestamps, Base):
    """A review from another platform with evidence; only verified ones feed reputation (A8)."""

    __tablename__ = "external_reviews"

    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    rating_norm: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    project_date: Mapped[date] = mapped_column(Date, nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id"), unique=True, nullable=False
    )
    status: Mapped[VerificationStatus] = mapped_column(
        _pg_enum(
            VerificationStatus,
            "verification_status",
        ),
        nullable=False,
        server_default=VerificationStatus.PENDING.value,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("char_length(source) BETWEEN 1 AND 80", name="source_len"),
        CheckConstraint("rating_norm BETWEEN 0 AND 1", name="rating_range"),
    )


class Question(UUIDPrimaryKey, Timestamps, Base):
    """A multiple-choice question. The correct answer never leaves the database (§14.13 row 3)."""

    __tablename__ = "question_bank"

    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    correct_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="2")
    # Practice-test flag; role assessments use `status = APPROVED` instead (Decision 15).
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Role assessment (spec §4.2). Content of an APPROVED question is immutable (trigger): a
    # correction retires the row and inserts a new version.
    slug: Mapped[str | None] = mapped_column(Text, unique=True)  # stable YAML id (bank build)
    competency_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competencies.id"))
    status: Mapped[QuestionStatus] = mapped_column(
        _pg_enum(QuestionStatus, "question_status"), nullable=False, server_default="DRAFT"
    )
    source: Mapped[QuestionSource] = mapped_column(
        _pg_enum(QuestionSource, "question_source"), nullable=False, server_default="HUMAN"
    )
    code_snippet: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    review_level: Mapped[ReviewLevel] = mapped_column(
        _pg_enum(ReviewLevel, "review_level"), nullable=False, server_default="NONE"
    )
    reviewed_by_name: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    times_served: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(options) = 'array' AND jsonb_array_length(options) = 4",
            name="four_options",
        ),
        CheckConstraint("correct_index BETWEEN 0 AND 3", name="correct_range"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty_range"),
        CheckConstraint("char_length(text) BETWEEN 5 AND 1000", name="text_len"),
        CheckConstraint("char_length(code_snippet) <= 1500", name="snippet_len"),
        CheckConstraint("char_length(explanation) <= 600", name="explanation_len"),
        CheckConstraint(
            "status <> 'APPROVED' OR (competency_id IS NOT NULL "
            "AND review_level IN ('SELF_VERIFIED', 'HUMAN_APPROVED'))",
            name="approved_is_reviewed",
        ),
        CheckConstraint(
            "review_level <> 'HUMAN_APPROVED' OR reviewed_by_name IS NOT NULL",
            name="human_approval_named",
        ),
        CheckConstraint("times_served >= 0 AND version >= 1", name="counters_valid"),
        Index("ix_question_bank_competency_status", "competency_id", "status", "difficulty"),
    )


class SkillTest(UUIDPrimaryKey, Timestamps, Base):
    """A timed multiple-choice test for one skill (public listing)."""

    __tablename__ = "skill_tests"

    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    question_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="10")
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="600")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        CheckConstraint("question_count BETWEEN 1 AND 50", name="count_range"),
        CheckConstraint("time_limit_seconds BETWEEN 60 AND 7200", name="time_range"),
    )


class TestAttempt(UUIDPrimaryKey, Timestamps, Base):
    """One attempt at a test. The deadline is set by the server at start."""

    __tablename__ = "test_attempts"
    __test__ = False  # not a pytest test class despite the name

    # A practice test (kind PRACTICE) or a role assessment (kind ROLE, role assessment spec §4.5).
    kind: Mapped[AttemptKind] = mapped_column(
        _pg_enum(AttemptKind, "attempt_kind"), nullable=False, server_default="PRACTICE"
    )
    test_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skill_tests.id"))
    blueprint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_blueprints.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    scored: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Role attempts only (role assessment spec §4.5–§7). Written only by the definer functions.
    context_project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    context_slot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    current_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    answers_locked: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    attempt_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    retired_token_hashes: Mapped[list[bytes]] = mapped_column(
        ARRAY(LargeBinary), nullable=False, server_default="{}"
    )
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rules_version: Mapped[int | None] = mapped_column(SmallInteger)
    leave_limit: Mapped[int | None] = mapped_column(SmallInteger)
    validity_days: Mapped[int | None] = mapped_column(SmallInteger)
    focus_leaves: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    focus_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    last_focus_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connection_gaps: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    terminated_reason: Mapped[TerminatedReason | None] = mapped_column(
        _pg_enum(TerminatedReason, "terminated_reason")
    )
    breakdown: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    overall_bp: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    extra_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reused_seen: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    admin_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        Index("ix_test_attempts_user_test_started", "user_id", "test_id", "started_at"),
        Index(
            "ix_test_attempts_open_by_user",
            "user_id",
            postgresql_where=text("submitted_at IS NULL"),  # forbidden-ok: constant DDL predicate
        ),
        Index("ix_test_attempts_blueprint_user", "blueprint_id", "user_id", "submitted_at"),
        Index(
            "ix_test_attempts_flagged",
            "submitted_at",
            postgresql_where=text("flagged"),  # forbidden-ok: constant DDL predicate
        ),
        CheckConstraint("deadline_at > started_at", name="deadline_after_start"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
        CheckConstraint(
            "(kind = 'PRACTICE' AND test_id IS NOT NULL AND blueprint_id IS NULL) OR "
            "(kind = 'ROLE' AND blueprint_id IS NOT NULL AND test_id IS NULL "
            "AND consent_at IS NOT NULL)",
            name="kind_target",
        ),
        CheckConstraint("overall_bp IS NULL OR overall_bp BETWEEN 0 AND 10000", name="overall_range"),
        CheckConstraint("focus_leaves >= 0 AND connection_gaps >= 0", name="counters_valid"),
        CheckConstraint("jsonb_array_length(focus_events) <= 30", name="focus_events_bounded"),
        CheckConstraint("extra_time_seconds BETWEEN 0 AND 3600", name="extra_time_range"),
    )


class SkillEvidence(UUIDPrimaryKey, Timestamps, Base):
    """Verified evidence of a skill (feeds the newcomer values and filtering in later phases)."""

    __tablename__ = "skill_evidence"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), nullable=False)
    source: Mapped[EvidenceSource] = mapped_column(
        _pg_enum(EvidenceSource, "evidence_source"), nullable=False
    )
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_attempts.id"), unique=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Role assessment results (role assessment spec §4.6): a row for every scored role attempt;
    # only passed, unvoided, unexpired ones satisfy the newcomer rule.
    blueprint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_blueprints.id"))
    passed: Mapped[bool | None] = mapped_column(Boolean)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_skill_evidence_user_skill", "user_id", "skill_id"),
        Index("ix_skill_evidence_user_blueprint", "user_id", "blueprint_id"),
        CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
        CheckConstraint(
            "source::text <> 'ROLE_ASSESSMENT' OR (blueprint_id IS NOT NULL AND passed IS NOT NULL)",
            name="role_evidence_complete",
        ),
        CheckConstraint("char_length(void_reason) <= 500", name="void_reason_len"),
    )
