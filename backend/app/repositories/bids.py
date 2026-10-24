"""Queries for bids, availability reservations and a developer's skills (spec §7.4)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bidding import AvailabilityReservation, Bid, BidStatus, ReservationStatus
from app.models.profiles import DeveloperProfile, DeveloperSkill, PortfolioItem, SkillEvidence


async def get_bid(db: AsyncSession, bid_id: uuid.UUID, *, for_update: bool = False) -> Bid | None:
    """A bid visible to the caller (RLS); `for_update` locks it so two edits can't interleave
    between the version check and the write."""
    if not for_update:
        return await db.get(Bid, bid_id)
    return await db.scalar(
        select(Bid)
        .where(Bid.id == bid_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


# A *standing* bid takes part in eligibility: ACTIVE, or INELIGIBLE after bidding closed (it can
# become ACTIVE again when the client changes the terms or extends bidding, §8). One per developer
# and project (index `one_standing_bid_per_developer`).
STANDING = (BidStatus.ACTIVE, BidStatus.INELIGIBLE)


async def standing_bid(
    db: AsyncSession, project_id: uuid.UUID, developer_id: uuid.UUID
) -> Bid | None:
    return await db.scalar(
        select(Bid).where(
            Bid.project_id == project_id,
            Bid.developer_id == developer_id,
            Bid.status.in_(STANDING),
        )
    )


async def count_active_for_developer(db: AsyncSession, developer_id: uuid.UUID) -> int:
    """Open (ACTIVE) bids of one developer, for the 30-open-bids cap (§14.8)."""
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Bid)
            .where(Bid.developer_id == developer_id, Bid.status == BidStatus.ACTIVE)
        )
        or 0
    )


async def page_for_developer(
    db: AsyncSession,
    developer_id: uuid.UUID,
    *,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
    project_id: uuid.UUID | None = None,
    status: BidStatus | None = None,
) -> Sequence[Bid]:
    """Newest first, keyset on (created_at, id) so pages never skip or repeat a bid. Reads one
    row more than `limit` so the caller knows whether another page exists."""
    stmt = select(Bid).where(Bid.developer_id == developer_id)
    if project_id is not None:
        stmt = stmt.where(Bid.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Bid.status == status)
    if after is not None:
        stmt = stmt.where(tuple_(Bid.created_at, Bid.id) < tuple_(*after))
    stmt = stmt.order_by(Bid.created_at.desc(), Bid.id.desc()).limit(limit + 1)
    return (await db.scalars(stmt)).all()


async def list_standing_for_project(db: AsyncSession, project_id: uuid.UUID) -> Sequence[Bid]:
    return (
        await db.scalars(select(Bid).where(Bid.project_id == project_id, Bid.status.in_(STANDING)))
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


# --------------------------------------------------------------------------- batched reads
# Algorithm 1 needs these per bidder; reading them for all bidders at once keeps the client's
# bids view at a fixed number of queries however many bids a project has (§16 perf).


async def skills_by_developer(
    db: AsyncSession, developer_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, set[uuid.UUID]]:
    out: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    if developer_ids:
        rows = await db.execute(
            select(DeveloperSkill.user_id, DeveloperSkill.skill_id).where(
                DeveloperSkill.user_id.in_(developer_ids)
            )
        )
        for user_id, skill_id in rows:
            out[user_id].add(skill_id)
    return out


async def best_evidence_by_developer(
    db: AsyncSession, developer_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[uuid.UUID, float]]:
    """Best skill-evidence score per (developer, skill) — the newcomer rule's input."""
    out: dict[uuid.UUID, dict[uuid.UUID, float]] = defaultdict(dict)
    if developer_ids:
        rows = await db.execute(
            select(SkillEvidence.user_id, SkillEvidence.skill_id, func.max(SkillEvidence.score))
            .where(SkillEvidence.user_id.in_(developer_ids))
            .group_by(SkillEvidence.user_id, SkillEvidence.skill_id)
        )
        for user_id, skill_id, score in rows:
            out[user_id][skill_id] = float(score)
    return out


async def profile_hours_by_developer(
    db: AsyncSession, developer_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not developer_ids:
        return {}
    rows = await db.execute(
        select(DeveloperProfile.user_id, DeveloperProfile.hours_per_week).where(
            DeveloperProfile.user_id.in_(developer_ids)
        )
    )
    return dict(rows.tuples().all())


async def confirmed_reservations_by_developer(
    db: AsyncSession, developer_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[AvailabilityReservation]]:
    out: dict[uuid.UUID, list[AvailabilityReservation]] = defaultdict(list)
    if developer_ids:
        rows = await db.scalars(
            select(AvailabilityReservation).where(
                AvailabilityReservation.developer_id.in_(developer_ids),
                AvailabilityReservation.status == ReservationStatus.CONFIRMED,
            )
        )
        for r in rows:
            out[r.developer_id].append(r)
    return out


async def owned_portfolio_ids(
    db: AsyncSession, developer_id: uuid.UUID, item_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """The subset of `item_ids` that belongs to `developer_id`."""
    if not item_ids:
        return set()
    rows = await db.scalars(
        select(PortfolioItem.id).where(
            PortfolioItem.id.in_(item_ids), PortfolioItem.user_id == developer_id
        )
    )
    return set(rows.all())


async def portfolio_titles(
    db: AsyncSession, item_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, uuid.UUID]]:
    """(title, owner) per portfolio item, so callers can keep only the bidder's own items."""
    if not item_ids:
        return {}
    rows = await db.execute(
        select(PortfolioItem.id, PortfolioItem.title, PortfolioItem.user_id).where(
            PortfolioItem.id.in_(item_ids)
        )
    )
    return {item_id: (title, owner) for item_id, title, owner in rows}


async def active_bidder_ids(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Developers with a standing bid (ACTIVE or INELIGIBLE): everyone a change affects."""
    rows = await db.scalars(
        select(Bid.developer_id).where(Bid.project_id == project_id, Bid.status.in_(STANDING))
    )
    return list(rows.all())
