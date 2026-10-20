"""Sealed bids and availability reservations (spec §7.4).

Row-level security is created in migration 0006: a bid and a reservation are visible only to the
bidding developer, the project's client and admins — **never** to other developers (sealed bids,
§2.2, §14.5). Writes are limited to the bidder while the project is `BIDDING`. The full
`bid_status` enum from spec §8 is defined now, though Phase 5 only drives
`ACTIVE → WITHDRAWN` (edits) and the re-evaluation to `INELIGIBLE`; selection/acceptance arrive in
Phases 7–8 (DECISIONS D38 precedent).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.identity import _pg_enum


class BidStatus(enum.StrEnum):
    """Bid lifecycle (spec §8). Phase 5 uses ACTIVE, WITHDRAWN and INELIGIBLE."""

    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"
    INELIGIBLE = "INELIGIBLE"
    SELECTED = "SELECTED"
    NOT_SELECTED = "NOT_SELECTED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


class ReservationStatus(enum.StrEnum):
    """Availability reservation lifecycle (spec §9.17)."""

    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"


class Bid(UUIDPrimaryKey, Timestamps, Base):
    """A sealed bid by a developer on one slot of a project (spec §7.4)."""

    __tablename__ = "bids"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_slots.id", ondelete="RESTRICT"), nullable=False
    )
    price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    days_needed: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    proposal: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    expected_contribution: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    portfolio_item_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    hours_per_week_committed: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[BidStatus] = mapped_column(
        _pg_enum(BidStatus, "bid_status"), nullable=False, server_default="ACTIVE"
    )
    # Reasons from the last eligibility evaluation (Algorithm 1, §9.2); shown to the client.
    ineligible_reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    __table_args__ = (
        # One ACTIVE bid per developer per project; a WITHDRAWN row is kept (sealed-bid history
        # and the B2 churn check, §9.15) and a fresh ACTIVE bid may be placed (DECISIONS D49).
        Index(
            "one_active_bid_per_developer",
            "project_id",
            "developer_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        CheckConstraint("price_paisa > 0", name="price_positive"),
        CheckConstraint("days_needed BETWEEN 1 AND 365", name="days_range"),
        CheckConstraint("hours_per_week_committed BETWEEN 1 AND 168", name="hours_committed_range"),
        Index("ix_bids_project_status", "project_id", "status"),
        Index("ix_bids_developer_status", "developer_id", "status"),
    )


class AvailabilityReservation(UUIDPrimaryKey, Timestamps, Base):
    """A developer's committed hours over a project period; prevents double booking (§9.17)."""

    __tablename__ = "availability_reservations"

    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    hours_per_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        _pg_enum(ReservationStatus, "reservation_status"),
        nullable=False,
        server_default="TENTATIVE",
    )

    __table_args__ = (
        CheckConstraint("to_date >= from_date", name="reservation_dates"),
        CheckConstraint("hours_per_week BETWEEN 1 AND 168", name="reservation_hours_range"),
        Index("ix_reservations_developer_status", "developer_id", "status"),
        Index("ix_reservations_project", "project_id"),
    )
