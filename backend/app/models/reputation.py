"""Reputation snapshots (spec §7.7).

Phase 5 creates the table and loads **fixed** values for experienced developers plus computed
newcomer starting values (§9.1.3); the reputation *engine* that computes these is Phase 6. Reads
go only through `services/reputation_read.py` so Phase 6 can replace the values without touching
filtering (DECISIONS D44). Row-level security (migration 0006): any authenticated user may read a
snapshot (it is a public value); only SYSTEM (the seed and the Phase 6 job) may write.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey

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

    __table_args__ = tuple(
        CheckConstraint(f"{col} BETWEEN 0 AND 1", name=f"{col}_range") for col in _SCORE_COLUMNS
    )
