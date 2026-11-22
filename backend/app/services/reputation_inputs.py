"""Builds the reputation engine's inputs from the database (spec §9.1.1, §17 Phase 6).

Everything here is **server-side evidence** (§14.13 row 6): verified contact details, a complete
profile, admin-verified certificates, passing skill evidence, and the completed-project history in
`reputation_history`. In Phase 6 that history is written by the market simulator (SIMULATED,
DECISIONS D84); from Phase 11 the same table receives PLATFORM rows built from real reviews and
work evidence, so the engine and this module don't change. Nothing a client sends reaches here.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.filtering import Mode
from app.algorithms.reputation import (
    Evidence,
    NewcomerParams,
    ProjectRecord,
    ReputationParams,
    platform_mean_beta,
)
from app.models.identity import User
from app.models.profiles import (
    Certificate,
    DeveloperProfile,
    EvidenceSource,
    Skill,
    SkillEvidence,
    VerificationStatus,
)
from app.models.reputation import ReputationHistory, ReputationSnapshot
from app.schemas.platform_settings import PlatformSettingsValues


async def verified_items(db: AsyncSession, developer_id: uuid.UUID) -> int:
    """§9.1.3 verified items for Γ⁰: phone, email, complete profile, verified certificate (0–4).

    "Complete profile" means a headline or a bio (Phase 5's rule). A certificate counts once an
    admin verified it (D94: Phase 5 left this item out although §9.1.3 lists it)."""
    user = await db.get(User, developer_id)
    if user is None:
        return 0
    items = int(user.phone_verified_at is not None) + int(user.email_verified_at is not None)
    profile = await db.scalar(
        select(DeveloperProfile).where(DeveloperProfile.user_id == developer_id)
    )
    if profile is not None and (profile.headline or profile.bio):
        items += 1
    certificate = await db.scalar(
        select(Certificate.id)
        .where(
            Certificate.user_id == developer_id,
            Certificate.status == VerificationStatus.VERIFIED,
        )
        .limit(1)
    )
    if certificate is not None:
        items += 1
    return items


async def evidence_domains(
    db: AsyncSession, developer_id: uuid.UUID, pass_mark: Decimal
) -> frozenset[str]:
    """Distinct skill domains with a passing skill-evidence score (for ω⁰ and per-skill
    competency). A role assessment counts only while it is a valid pass (passed, not voided, not
    expired; role assessment spec §8.4); practice tests count as before."""
    role = SkillEvidence.source == EvidenceSource.ROLE_ASSESSMENT
    valid_role_pass = and_(
        SkillEvidence.passed.is_(True),
        SkillEvidence.voided_at.is_(None),
        SkillEvidence.valid_until > func.now(),
    )
    rows = await db.scalars(
        select(Skill.domain)
        .join(SkillEvidence, SkillEvidence.skill_id == Skill.id)
        .where(
            SkillEvidence.user_id == developer_id,
            SkillEvidence.score >= pass_mark,
            or_(~role, valid_role_pass),
        )
        .distinct()
    )
    return frozenset(str(d.value) for d in rows.all())


async def evidence(
    db: AsyncSession, developer_id: uuid.UUID, settings: PlatformSettingsValues
) -> Evidence:
    """The newcomer evidence the engine uses in devsync mode."""
    return Evidence(
        verified_items=await verified_items(db, developer_id),
        evidence_domains=await evidence_domains(db, developer_id, settings.newcomer.pass_mark),
    )


def to_record(row: ReputationHistory) -> ProjectRecord:
    """One stored history row as the pure engine's input."""
    return ProjectRecord(
        history_id=str(row.id),
        domain=row.domain.value,
        client_key=row.client_key,
        t_days=row.t_days,
        deadline_days=row.deadline_days,
        gamma_comm=row.gamma_comm,
        gamma_team=row.gamma_team,
        internal_slots=tuple(row.internal_slots),
        external_slots=tuple(row.external_slots),
    )


async def load_history(db: AsyncSession, developer_id: uuid.UUID) -> list[ReputationHistory]:
    """The developer's completed projects, oldest first (ties by id, so the order is stable)."""
    rows = await db.scalars(
        select(ReputationHistory)
        .where(ReputationHistory.developer_id == developer_id)
        .order_by(ReputationHistory.completed_at, ReputationHistory.id)
    )
    return list(rows.all())


def newcomer_params(settings: PlatformSettingsValues) -> NewcomerParams:
    """The active `rep.*` values the starting values use (never hard-coded, §6.2)."""
    rep = settings.rep
    return NewcomerParams(
        f=rep.f_default,
        g=rep.g,
        gamma0_base=rep.gamma0_base,
        gamma0_per_verification=rep.gamma0_per_verification,
        gamma0_max=rep.gamma0_max,
        neutral=rep.neutral,
    )


def params_from_settings(
    settings: PlatformSettingsValues, newcomer_review: Decimal
) -> ReputationParams:
    """Every engine parameter from the active settings; `newcomer_review` is resolved by the
    caller (the setting, or the platform mean β when the setting is empty)."""
    rep = settings.rep
    return ReputationParams(
        alpha_comm=rep.alpha_comm,
        alpha_team=rep.alpha_team,
        kappa_ext=rep.kappa_ext,
        kappa_int=rep.kappa_int,
        alpha_x=rep.alpha_x,
        alpha_e=rep.alpha_e,
        w_internal=rep.w_internal,
        w_external=rep.w_external,
        newcomer=newcomer_params(settings),
        newcomer_review=newcomer_review,
        max_change=rep.max_change_per_project,
        newcomer_threshold=settings.newcomer.threshold,
        mode=Mode(settings.algorithm.mode),
    )


async def newcomer_review(db: AsyncSession, settings: PlatformSettingsValues) -> Decimal:
    """β for a developer with no internal reviews yet (§9.1.2, D8):

    `rep.newcomer_review` when an admin set it; otherwise the platform mean β of developers with
    at least `newcomer.threshold` completed projects, over **engine-computed** snapshots only
    (`settings_version` set — Phase 5's hand-set stage-1 values are not engine output, D98);
    otherwise `rep.newcomer_review_fallback` (0.6). Snapshots are a public value, so this works
    in every signed-in and SYSTEM session."""
    rep = settings.rep
    if rep.newcomer_review is not None:
        return rep.newcomer_review
    betas = await db.scalars(
        select(ReputationSnapshot.beta).where(
            ReputationSnapshot.settings_version.is_not(None),
            ReputationSnapshot.completed_projects >= settings.newcomer.threshold,
        )
    )
    return platform_mean_beta(list(betas.all()), rep.newcomer_review_fallback)
