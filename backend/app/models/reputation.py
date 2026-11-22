"""Reputation snapshots (spec §7.7).

Phase 5 creates the table and loads **fixed** values for experienced developers plus computed
newcomer starting values (§9.1.3); the reputation *engine* that computes these is Phase 6. Reads
go only through `services/reputation_read.py` so Phase 6 can replace the values without touching
filtering (DECISIONS D44). Row-level security (migration 0006): any authenticated user may read a
snapshot (it is a public value); only SYSTEM (the seed and the Phase 6 job) may write.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.identity import _pg_enum
from app.models.profiles import SkillDomain

_SCORE_COLUMNS = ("omega", "x", "xm", "beta", "mu", "t", "c", "p")


class ReputationSnapshot(UUIDPrimaryKey, Timestamps, Base):
    """Current reputation values for one developer (spec §7.7, Eq. 1–12 outputs)."""

    __tablename__ = "reputation_snapshots"

    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    omega: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # ω, domain diversity
    x: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # X, communication
    xm: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # X_m, teamwork
    beta: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # β, review quality
    mu: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # μ, client diversity
    t: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # T, timeliness
    c: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # C, competency (Eq. 4)
    p: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # P, performance (Eq. 12)
    completed_projects: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    distinct_clients: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    settings_version: Mapped[int | None] = mapped_column(Integer)
    # Phase 6 (D84): true when computed from simulated histories, so every view can label it.
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = tuple(
        CheckConstraint(f"{col} BETWEEN 0 AND 1", name=f"{col}_range") for col in _SCORE_COLUMNS
    )


# ------------------------------------------------------------------ Phase 6 (migration 0012)


class ReputationSource(enum.StrEnum):
    """Where a completed-project record comes from (DECISIONS D84)."""

    SIMULATED = "SIMULATED"  # market simulator (Phase 6 demo and experiments); labelled in the UI
    PLATFORM = "PLATFORM"  # real evidence and reviews (written from Phase 11)


class ReputationHistory(UUIDPrimaryKey, Timestamps, Base):
    """One completed project of one developer: the §9.1.1 inputs of the reputation engine.

    Developer and admins read it; only SYSTEM writes it (RLS, migration 0012). Values are the
    already-normalised 0–1 inputs, 4 decimal places."""

    __tablename__ = "reputation_history"

    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[ReputationSource] = mapped_column(
        _pg_enum(ReputationSource, "reputation_source"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    project_label: Mapped[str] = mapped_column(Text, nullable=False)
    client_key: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[SkillDomain] = mapped_column(
        _pg_enum(SkillDomain, "skill_domain"), nullable=False
    )
    t_days: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline_days: Mapped[int] = mapped_column(Integer, nullable=False)
    gamma_comm: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    gamma_team: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    internal_slots: Mapped[list[Decimal]] = mapped_column(
        ARRAY(Numeric(5, 4)), nullable=False, server_default="{}"
    )
    external_slots: Mapped[list[Decimal]] = mapped_column(
        ARRAY(Numeric(5, 4)), nullable=False, server_default="{}"
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sim_version: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("developer_id", "source", "project_label",
                         name="uq_reputation_history_project"),
        CheckConstraint("char_length(project_label) BETWEEN 1 AND 120", name="label_length"),
        CheckConstraint("char_length(client_key) BETWEEN 1 AND 80", name="client_key_length"),
        CheckConstraint("t_days >= 0", name="t_days_non_negative"),
        CheckConstraint("deadline_days >= 1", name="deadline_positive"),
        CheckConstraint("gamma_comm BETWEEN 0 AND 1", name="gamma_comm_range"),
        CheckConstraint("gamma_team BETWEEN 0 AND 1", name="gamma_team_range"),
        CheckConstraint(
            "0 <= ALL(internal_slots) AND 1 >= ALL(internal_slots)", name="internal_slots_range"
        ),
        CheckConstraint(
            "0 <= ALL(external_slots) AND 1 >= ALL(external_slots)", name="external_slots_range"
        ),
        CheckConstraint(
            "(source = 'SIMULATED') = (sim_version IS NOT NULL)", name="sim_version_iff_simulated"
        ),
        Index("ix_reputation_history_developer", "developer_id", "completed_at"),
    )  # fmt: skip


class ReputationSkill(UUIDPrimaryKey, Timestamps, Base):
    """Per-skill competency C_{i,s} (§9.1.7) for display and the optional fitness switch.
    Readable by any signed-in user like the snapshot; SYSTEM-only to write."""

    __tablename__ = "reputation_skill"

    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    competency: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("developer_id", "skill_id", name="uq_reputation_skill_developer_skill"),
        CheckConstraint("competency BETWEEN 0 AND 1", name="competency_range"),
        Index("ix_reputation_skill_skill", "skill_id"),
    )


LOG_PARAMETERS = ("omega", "x", "xm", "beta", "mu", "t", "c", "p")


class ReputationLog(UUIDPrimaryKey, Timestamps, Base):
    """Append-only explanation log (§7.7 **AO**): how each parameter changed after each project.

    A trigger refuses UPDATE and DELETE and the app roles hold no UPDATE/DELETE/TRUNCATE grant;
    developers read their own rows, admins all, and only SYSTEM inserts. Re-running the engine
    with the same history and settings inserts nothing new (unique key, ON CONFLICT DO NOTHING)."""

    __tablename__ = "reputation_log"

    developer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    history_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reputation_history.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    parameter: Mapped[str] = mapped_column(Text, nullable=False)
    old: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    new: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    raw_new: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    inputs: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, server_default="{}")
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("history_id", "parameter", "settings_version",
                         name="uq_reputation_log_entry"),
        CheckConstraint(
            "parameter IN ('omega', 'x', 'xm', 'beta', 'mu', 't', 'c', 'p')", name="parameter_known"
        ),
        CheckConstraint("char_length(reason_code) BETWEEN 1 AND 40", name="reason_code_length"),
        *(
            CheckConstraint(f"{col} BETWEEN 0 AND 1", name=f"{col}_range")
            for col in ("old", "new", "raw_new")
        ),
        Index("ix_reputation_log_developer", "developer_id", "created_at"),
    )  # fmt: skip
