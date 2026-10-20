"""Queries for bids, availability reservations and a developer's skills (spec §7.4)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bidding import AvailabilityReservation, Bid, BidStatus, ReservationStatus
from app.models.profiles import DeveloperSkill


async def get_bid(db: AsyncSession, bid_id: uuid.UUID) -> Bid | None:
    return await db.get(Bid, bid_id)


async def active_bid(
    db: AsyncSession, project_id: uuid.UUID, developer_id: uuid.UUID
) -> Bid | None:
    return await db.scalar(
        select(Bid).where(
            Bid.project_id == project_id,
            Bid.developer_id == developer_id,
            Bid.status == BidStatus.ACTIVE,
        )
    )


async def list_for_developer(db: AsyncSession, developer_id: uuid.UUID) -> Sequence[Bid]:
    return (
        await db.scalars(
            select(Bid).where(Bid.developer_id == developer_id).order_by(Bid.created_at.desc())
        )
    ).all()


async def list_active_for_project(db: AsyncSession, project_id: uuid.UUID) -> Sequence[Bid]:
    return (
        await db.scalars(
            select(Bid).where(Bid.project_id == project_id, Bid.status == BidStatus.ACTIVE)
        )
    ).all()


async def developer_skill_ids(db: AsyncSession, developer_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await db.scalars(
        select(DeveloperSkill.skill_id).where(DeveloperSkill.user_id == developer_id)
    )
    return set(rows.all())


async def confirmed_reservations(
    db: AsyncSession, developer_id: uuid.UUID
) -> Sequence[AvailabilityReservation]:
    return (
        await db.scalars(
            select(AvailabilityReservation).where(
                AvailabilityReservation.developer_id == developer_id,
                AvailabilityReservation.status == ReservationStatus.CONFIRMED,
            )
        )
    ).all()
