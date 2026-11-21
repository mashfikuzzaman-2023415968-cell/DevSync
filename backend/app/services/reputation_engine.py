"""The reputation engine: compute and store developers' reputations (spec §9.1, §17 Phase 6).

Reads each developer's completed-project history and newcomer evidence (`reputation_inputs`),
runs the pure engine (`algorithms/reputation.compute_snapshot`) and stores, in one transaction
per developer:

- the snapshot (`reputation_snapshots`, upserted with the settings version it used, which also
  turns off the D48 "seeded" marker);
- per-skill competency (`reputation_skill`, every active skill of each domain the engine scored);
- one append-only `reputation_log` row per parameter per project. The log's unique key
  (history, parameter, settings version) makes a re-run with the same inputs and settings insert
  nothing new (ON CONFLICT DO NOTHING), so the job is idempotent.

Everything runs in a SYSTEM session on the worker's connection (`is_system()` in the RLS
policies); web requests never write reputation (§14.13 row 6). Developers without any history
keep the on-the-fly newcomer values of `reputation_read`, so a new role-assessment pass shows up
at once instead of waiting for a recalculation.

**Platform mean β (D98).** With `rep.newcomer_review` unset, `recalculate_all` computes it
deterministically from the histories alone: pass 1 scores the experienced developers starting
from the fallback (0.6), their mean β becomes the newcomer β, and pass 2 scores everyone with it.
The result depends only on histories and settings, never on what was stored before.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.reputation import (
    FORMULA_VERSION,
    SnapshotResult,
    compute_snapshot,
    platform_mean_beta,
)
from app.core.audit import write_audit
from app.models.profiles import Skill
from app.models.reputation import (
    ReputationHistory,
    ReputationLog,
    ReputationSkill,
    ReputationSnapshot,
)
from app.schemas.platform_settings import PlatformSettingsValues
from app.services import reputation_inputs

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Outcome:
    """What one developer's recalculation stored."""

    developer_id: uuid.UUID
    result: SnapshotResult
    log_rows_added: int


@dataclass(frozen=True)
class Summary:
    """What a full recalculation did (returned by the job and written to the audit log)."""

    developers: int
    log_rows_added: int
    newcomer_review: Decimal
    settings_version: int


async def _compute(
    db: AsyncSession,
    developer_id: uuid.UUID,
    settings: PlatformSettingsValues,
    newcomer_review: Decimal,
) -> tuple[list[ReputationHistory], SnapshotResult] | None:
    rows = await reputation_inputs.load_history(db, developer_id)
    if not rows:
        return None
    params = reputation_inputs.params_from_settings(settings, newcomer_review)
    ev = await reputation_inputs.evidence(db, developer_id, settings)
    records = [reputation_inputs.to_record(r) for r in rows]
    return rows, compute_snapshot(records, params, ev)


async def _store(
    db: AsyncSession,
    developer_id: uuid.UUID,
    rows: list[ReputationHistory],
    result: SnapshotResult,
    settings_version: int,
) -> int:
    snap = result.snapshot
    values = {
        "omega": snap.omega, "x": snap.x, "xm": snap.xm, "beta": snap.beta, "mu": snap.mu,
        "t": snap.t, "c": snap.c, "p": snap.p, "completed_projects": snap.completed_projects,
        "distinct_clients": snap.distinct_clients, "settings_version": settings_version,
    }  # fmt: skip
    await db.execute(
        insert(ReputationSnapshot)
        .values(developer_id=developer_id, **values)
        .on_conflict_do_update(index_elements=["developer_id"], set_=values)
    )

    # Per-skill competency: replaced as a whole (it is derived, not a log).
    await db.execute(delete(ReputationSkill).where(ReputationSkill.developer_id == developer_id))
    if result.skill_competency:
        skills = await db.execute(
            select(Skill.id, Skill.domain).where(
                Skill.active.is_(True),
                Skill.domain.in_(list(result.skill_competency)),
            )
        )
        skill_rows = [
            {"developer_id": developer_id, "skill_id": skill_id,
             "competency": result.skill_competency[domain.value],
             "settings_version": settings_version}
            for skill_id, domain in skills.all()
        ]  # fmt: skip
        if skill_rows:
            await db.execute(insert(ReputationSkill).values(skill_rows))

    by_id = {str(r.id): r for r in rows}
    log_rows = [
        {
            "developer_id": developer_id,
            "history_id": by_id[e.history_id].id,
            "project_id": by_id[e.history_id].project_id,
            "parameter": e.parameter,
            "old": e.old,
            "new": e.new,
            "raw_new": e.raw,
            "inputs": dict(e.inputs),
            "reason_code": e.reason_code,
            "formula_version": FORMULA_VERSION,
            "settings_version": settings_version,
        }
        for e in result.trace
    ]
    if not log_rows:
        return 0
    inserted = await db.execute(
        insert(ReputationLog)
        .values(log_rows)
        .on_conflict_do_nothing(constraint="uq_reputation_log_entry")
        .returning(ReputationLog.id)
    )
    return len(inserted.all())


async def recalculate(
    db: AsyncSession,
    developer_id: uuid.UUID,
    settings: PlatformSettingsValues,
    settings_version: int,
    newcomer_review: Decimal | None = None,
) -> Outcome | None:
    """Recalculate one developer in the caller's SYSTEM transaction (the caller commits).

    `newcomer_review` defaults to `reputation_inputs.newcomer_review()` (the setting or the
    stored platform mean). Returns None for a developer with no history: nothing is stored."""
    beta0 = newcomer_review
    if beta0 is None:
        beta0 = await reputation_inputs.newcomer_review(db, settings)
    computed = await _compute(db, developer_id, settings, beta0)
    if computed is None:
        return None
    rows, result = computed
    added = await _store(db, developer_id, rows, result, settings_version)
    return Outcome(developer_id, result, added)


async def developers_with_history(db: AsyncSession) -> list[uuid.UUID]:
    ids = await db.scalars(
        select(ReputationHistory.developer_id).distinct().order_by(ReputationHistory.developer_id)
    )
    return list(ids.all())


async def resolve_newcomer_review(
    db: AsyncSession, developer_ids: list[uuid.UUID], settings: PlatformSettingsValues
) -> Decimal:
    """D98: the setting if set; else the mean β of experienced developers scored from the
    fallback (pass 1 of `recalculate_all`), so the value depends only on the histories."""
    rep = settings.rep
    if rep.newcomer_review is not None:
        return rep.newcomer_review
    betas = []
    for dev in developer_ids:
        computed = await _compute(db, dev, settings, rep.newcomer_review_fallback)
        if computed is None:
            continue
        snap = computed[1].snapshot
        if snap.completed_projects >= settings.newcomer.threshold:
            betas.append(snap.beta)
    return platform_mean_beta(betas, rep.newcomer_review_fallback)


async def recalculate_all(
    db: AsyncSession, settings: PlatformSettingsValues, settings_version: int
) -> Summary:
    """Recalculate every developer with a history (`reputation.recalculate_all`, §11), in the
    caller's SYSTEM transaction; audited once with the counts."""
    developer_ids = await developers_with_history(db)
    beta0 = await resolve_newcomer_review(db, developer_ids, settings)
    added = 0
    for dev in developer_ids:
        outcome = await recalculate(db, dev, settings, settings_version, beta0)
        if outcome is not None:
            added += outcome.log_rows_added
    summary = Summary(len(developer_ids), added, beta0, settings_version)
    await write_audit(
        db,
        action="reputation.recalculate_all",
        entity_type="reputation",
        entity_id=None,
        actor_role="SYSTEM",
        after={
            "developers": summary.developers,
            "log_rows_added": summary.log_rows_added,
            "newcomer_review": str(summary.newcomer_review),
            "settings_version": settings_version,
        },
    )
    log.info("reputation_recalculated", developers=summary.developers, log_rows=added)
    return summary
