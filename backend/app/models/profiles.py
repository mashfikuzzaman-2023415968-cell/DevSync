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
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
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

    TEST = "TEST"
    CODING = "CODING"
    ADMIN_PORTFOLIO = "ADMIN_PORTFOLIO"


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

    __table_args__ = (
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

    __table_args__ = (
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
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(options) = 'array' AND jsonb_array_length(options) = 4",
            name="four_options",
        ),
        CheckConstraint("correct_index BETWEEN 0 AND 3", name="correct_range"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty_range"),
        CheckConstraint("char_length(text) BETWEEN 5 AND 1000", name="text_len"),
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

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skill_tests.id"), nullable=False)
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

    __table_args__ = (
        Index("ix_test_attempts_user_test_started", "user_id", "test_id", "started_at"),
        CheckConstraint("deadline_at > started_at", name="deadline_after_start"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
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

    __table_args__ = (
        Index("ix_skill_evidence_user_skill", "user_id", "skill_id"),
        CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
    )
