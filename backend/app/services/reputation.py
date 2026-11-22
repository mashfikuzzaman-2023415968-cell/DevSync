"""Reputation views: a developer's reputation and the developer's own change history
(spec §10.2 Reputation, §13.5 #16).

Reads only. Values come from the stored snapshot (engine-computed, or the Phase 5 fixed demo
values) through `reputation_read`, in the caller's own session, so row-level security decides
what is visible: a snapshot and per-skill competency are a public value for signed-in users; the
history and its log are the developer's own (and admins'). A profile the caller may not see is
404, exactly like `GET /developers/{id}`. A newcomer without a stored snapshot shows their
starting values to themselves (computed from their own evidence) and nothing to anyone else,
because computing them would need another user's private data (D58).
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, or_, select

from app.algorithms.reputation import TraceEntry
from app.algorithms.reputation_explain import explain_change
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.settings_cache import active_settings
from app.models.profiles import Skill
from app.models.reputation import (
    ReputationHistory,
    ReputationLog,
    ReputationSkill,
    ReputationSnapshot,
    ReputationSource,
)
from app.repositories import profiles as profile_repo
from app.schemas.common import Page
from app.schemas.reputation import (
    DeveloperReputation,
    NewcomerBasis,
    ReputationChange,
    ReputationHistoryItem,
    ReputationParameters,
    SkillCompetency,
)
from app.services import reputation_inputs, reputation_read
from app.services.context import Ctx

PLACES = Decimal("0.001")
_ORDER = ("omega", "x", "xm", "beta", "mu", "t", "c", "p")


def _q(value: Decimal | float) -> Decimal:
    return Decimal(str(value)).quantize(PLACES, rounding=ROUND_HALF_UP)


async def developer_reputation(
    ctx: Ctx, developer_id: uuid.UUID, *, production: bool
) -> DeveloperReputation:
    """The reputation of a developer whose profile the caller may see (404 otherwise)."""
    if await profile_repo.public_developer_profile(ctx.db, developer_id) is None:
        raise NotFoundError
    settings = await active_settings(ctx.db)
    snap = await ctx.db.scalar(
        select(ReputationSnapshot).where(ReputationSnapshot.developer_id == developer_id)
    )
    is_self = ctx.uid == developer_id
    newcomer: NewcomerBasis | None = None
    competency: Decimal | None
    performance: Decimal | None
    if snap is not None:
        params = ReputationParameters(
            omega=snap.omega, x=snap.x, xm=snap.xm, beta=snap.beta, mu=snap.mu, t=snap.t
        )
        competency, performance = snap.c, snap.p
        completed, clients = snap.completed_projects, snap.distinct_clients
        is_newcomer = snap.completed_projects < settings.newcomer.threshold
        seeded = snap.settings_version is None and not production
        simulated, updated = snap.simulated, snap.updated_at
    elif is_self:
        view = await reputation_read.read_one(ctx.db, developer_id, settings)
        params = ReputationParameters(
            omega=_q(view.omega), x=_q(view.x), xm=_q(view.xm), beta=_q(view.beta),
            mu=_q(view.mu), t=_q(view.t),
        )  # fmt: skip
        competency, performance = _q(view.c), _q(view.p)
        completed, clients, is_newcomer = 0, 0, True
        seeded, simulated, updated = False, False, None
    else:
        params = ReputationParameters(omega=None, x=None, xm=None, beta=None, mu=None, t=None)
        competency = performance = None
        completed, clients, is_newcomer = 0, 0, True
        seeded, simulated, updated = False, False, None
    if is_self and is_newcomer:
        domains = await reputation_inputs.evidence_domains(
            ctx.db, developer_id, settings.newcomer.pass_mark
        )
        newcomer = NewcomerBasis(
            verified_items=await reputation_inputs.verified_items(ctx.db, developer_id),
            evidence_domains=len(domains),
            review_default=_q(await reputation_inputs.newcomer_review(ctx.db, settings)),
            threshold=settings.newcomer.threshold,
        )
    skills = await ctx.db.execute(
        select(ReputationSkill.skill_id, Skill.name, ReputationSkill.competency)
        .join(Skill, Skill.id == ReputationSkill.skill_id)
        .where(ReputationSkill.developer_id == developer_id)
        .order_by(ReputationSkill.competency.desc(), Skill.name)
    )
    return DeveloperReputation(
        developer_id=developer_id,
        parameters=params,
        competency=competency,
        performance=performance,
        completed_projects=completed,
        distinct_clients=clients,
        is_newcomer=is_newcomer,
        seeded=seeded,
        simulated=simulated,
        skills=[SkillCompetency(skill_id=s, name=n, competency=c) for s, n, c in skills.all()],
        newcomer=newcomer,
        updated_at=updated,
    )


def _encode_cursor(row: ReputationHistory) -> str:
    return base64.urlsafe_b64encode(f"{row.completed_at.isoformat()}|{row.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at_text, row_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        at = datetime.fromisoformat(at_text)
        if at.tzinfo is None:
            raise ValueError("naive time")
        return at, uuid.UUID(row_id)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise DomainError(
            "That page cursor is invalid.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"cursor": "invalid"},
        ) from exc


def _change(row: ReputationLog) -> ReputationChange | None:
    entry = TraceEntry(
        history_id=str(row.history_id), parameter=row.parameter, old=row.old, raw=row.raw_new,
        new=row.new, reason_code=row.reason_code, inputs=row.inputs,
    )  # fmt: skip
    # When capped, the limit that applied is exactly the size of the change.
    explained = explain_change(entry, abs(row.new - row.old))
    if explained is None:
        return None
    return ReputationChange(
        parameter=row.parameter,  # a CHECK constraint keeps it one of the eight
        old=row.old,
        new=row.new,
        raw_new=row.raw_new,
        capped=entry.capped,
        reason=explained.sentence,
    )


async def my_history(
    ctx: Ctx, *, cursor: str | None = None, limit: int = 20
) -> Page[ReputationHistoryItem]:
    """The caller's completed projects, newest first, each with what it changed (§13.5 #16
    "Why did this change?"). Uses each project's latest log entries (the newest settings
    version that scored it); a reason the server doesn't recognise is left out (D65)."""
    stmt = select(ReputationHistory).where(ReputationHistory.developer_id == ctx.uid)
    if cursor is not None:
        at, row_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                ReputationHistory.completed_at < at,
                and_(ReputationHistory.completed_at == at, ReputationHistory.id < row_id),
            )
        )
    rows = list(
        (
            await ctx.db.scalars(
                stmt.order_by(ReputationHistory.completed_at.desc(), ReputationHistory.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )  # fmt: skip
    page, more = rows[:limit], len(rows) > limit
    ids = [r.id for r in page]
    latest = (
        select(ReputationLog.history_id, func.max(ReputationLog.settings_version).label("v"))
        .where(ReputationLog.history_id.in_(ids))
        .group_by(ReputationLog.history_id)
        .subquery()
    )
    logs = await ctx.db.scalars(
        select(ReputationLog).join(
            latest,
            and_(
                ReputationLog.history_id == latest.c.history_id,
                ReputationLog.settings_version == latest.c.v,
            ),
        )
    )
    by_history: dict[uuid.UUID, list[ReputationLog]] = {}
    for log_row in logs.all():
        by_history.setdefault(log_row.history_id, []).append(log_row)
    items = []
    for r in page:
        entries = sorted(by_history.get(r.id, []), key=lambda e: _ORDER.index(e.parameter))
        changes = [c for c in (_change(e) for e in entries) if c is not None]
        items.append(
            ReputationHistoryItem(
                history_id=r.id,
                project_label=r.project_label,
                domain=r.domain.value,
                completed_at=r.completed_at,
                simulated=r.source is ReputationSource.SIMULATED,
                changes=changes,
            )
        )
    return Page[ReputationHistoryItem](
        items=items, next_cursor=_encode_cursor(page[-1]) if more and page else None
    )
