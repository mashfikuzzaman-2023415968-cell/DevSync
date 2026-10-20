"""The single read path for reputation values (spec §17 Phase 5, DECISIONS D44).

Algorithm 1 (`algorithms/filtering.py`) needs each developer's competency `C` and performance `P`.
In Phase 5 those come from **fixed** snapshots loaded by the seed for experienced developers, and
from `newcomer_snapshot()` for newcomers. Filtering reads them **only** through this module, so
Phase 6 can replace the stored values with engine-computed ones without touching filtering.

A developer with no stored snapshot (a freshly registered account in tests or a live run) gets a
newcomer snapshot computed on the fly from their verified items and passing skill evidence — not
persisted here (writes are SYSTEM-only, §14.15; the Phase 6 job and the seed persist). `seeded` is
true for a stored snapshot without a `settings_version` (the Phase 5 fixtures); the bid table and
profile show the "seeded" marker only outside production (D48).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.reputation import NewcomerInputs, newcomer_snapshot
from app.models.identity import User
from app.models.profiles import DeveloperProfile, Skill, SkillEvidence
from app.models.reputation import ReputationSnapshot
from app.schemas.platform_settings import PlatformSettingsValues


@dataclass(frozen=True)
class ReputationView:
    """Reputation values as the filter and the UI need them (scores on 0–1)."""

    developer_id: uuid.UUID
    omega: float
    x: float
    xm: float
    beta: float
    mu: float
    t: float
    c: float
    p: float
    completed_projects: int
    distinct_clients: int
    is_newcomer: bool
    seeded: bool


def _view_from_snapshot(snap: ReputationSnapshot, newcomer_threshold: int) -> ReputationView:
    return ReputationView(
        developer_id=snap.developer_id,
        omega=float(snap.omega),
        x=float(snap.x),
        xm=float(snap.xm),
        beta=float(snap.beta),
        mu=float(snap.mu),
        t=float(snap.t),
        c=float(snap.c),
        p=float(snap.p),
        completed_projects=snap.completed_projects,
        distinct_clients=snap.distinct_clients,
        is_newcomer=snap.completed_projects < newcomer_threshold,
        seeded=snap.settings_version is None,
    )


async def _verified_items(db: AsyncSession, developer_id: uuid.UUID) -> int:
    """Count of {phone, email, complete profile, verified certificate} for Γ⁰ (§9.1.3)."""
    user = await db.get(User, developer_id)
    if user is None:
        return 0
    items = int(user.phone_verified_at is not None) + int(user.email_verified_at is not None)
    profile = await db.scalar(
        select(DeveloperProfile).where(DeveloperProfile.user_id == developer_id)
    )
    if profile is not None and (profile.headline or profile.bio):
        items += 1
    return items


async def _evidence_domains(db: AsyncSession, developer_id: uuid.UUID, pass_mark: Decimal) -> int:
    """Distinct skill domains with a passing skill-evidence score (for ω⁰)."""
    rows = await db.execute(
        select(Skill.domain)
        .join(SkillEvidence, SkillEvidence.skill_id == Skill.id)
        .where(SkillEvidence.user_id == developer_id, SkillEvidence.score >= pass_mark)
        .distinct()
    )
    return len(rows.all())


async def _computed_newcomer(
    db: AsyncSession, developer_id: uuid.UUID, settings: PlatformSettingsValues
) -> ReputationView:
    rep = settings.rep
    beta = rep.newcomer_review if rep.newcomer_review is not None else rep.newcomer_review_fallback
    snap = newcomer_snapshot(
        NewcomerInputs(
            verified_items=await _verified_items(db, developer_id),
            evidence_domains=await _evidence_domains(db, developer_id, settings.newcomer.pass_mark),
            newcomer_review_beta=beta,
        )
    )
    return ReputationView(
        developer_id=developer_id,
        omega=float(snap.omega),
        x=float(snap.x),
        xm=float(snap.xm),
        beta=float(snap.beta),
        mu=float(snap.mu),
        t=float(snap.t),
        c=float(snap.c),
        p=float(snap.p),
        completed_projects=0,
        distinct_clients=0,
        is_newcomer=True,
        seeded=False,
    )


async def read_many(
    db: AsyncSession, developer_ids: list[uuid.UUID], settings: PlatformSettingsValues
) -> dict[uuid.UUID, ReputationView]:
    """Reputation for several developers; missing snapshots are computed as newcomers."""
    out: dict[uuid.UUID, ReputationView] = {}
    if developer_ids:
        snapshots = await db.scalars(
            select(ReputationSnapshot).where(ReputationSnapshot.developer_id.in_(developer_ids))
        )
        for snap in snapshots:
            out[snap.developer_id] = _view_from_snapshot(snap, settings.newcomer.threshold)
    for dev_id in developer_ids:
        if dev_id not in out:
            out[dev_id] = await _computed_newcomer(db, dev_id, settings)
    return out


async def read_one(
    db: AsyncSession, developer_id: uuid.UUID, settings: PlatformSettingsValues
) -> ReputationView:
    return (await read_many(db, [developer_id], settings))[developer_id]
