"""Marketplace search and recommendations (spec §10 Marketplace, §9.16). Read-only.

Search is full-text over the project title, summary **and the slots' skill names** (via
`plainto_tsquery`, §14.7) with whitelisted filters and keyset (cursor) pagination for every sort
order. It only lists projects still taking bids — `BIDDING` and before the bidding deadline — and
never exposes any bid data (§14.5).

Recommendations (§9.16) are open projects needing at least one of the developer's skills, whose
deadline is at least the developer's typical days for that skill (median of their past bids on
it; any deadline when they have none), and whose period fits their free hours; ranked by
skill-match count then newest, excluding projects already bid on. Cached 5 minutes per developer
(fails open without Redis) and forgotten when the developer bids or withdraws.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import statistics
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import availability as avail
from app.core.clock import get_clock
from app.core.errors import DomainError, ErrorCode, NotFoundError
from app.core.redis import get_redis
from app.models.bidding import Bid, BidStatus
from app.models.profiles import Skill
from app.models.projects import Project, ProjectSlot, ProjectStatus
from app.repositories import bids as bidrepo
from app.schemas.common import Page
from app.schemas.marketplace import (
    ProjectCard,
    ProjectDetail,
    RecommendedProject,
    SlotCard,
)

log = structlog.get_logger(__name__)

SORTS = {"newest", "budget", "deadline"}
MAX_LIMIT = 100
RECOMMENDED_LIMIT = 12
RECOMMENDED_CANDIDATES = 200
RECOMMENDED_CACHE_SECONDS = 300


def _rec_key(developer_id: uuid.UUID) -> str:
    return f"marketplace:recommended:{developer_id}"


# --------------------------------------------------------------------------- cursors


def _encode_cursor(sort: str, value: str, project_id: uuid.UUID) -> str:
    raw = f"{sort}|{value}|{project_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _bad_cursor(exc: Exception | None = None) -> DomainError:
    err = DomainError(
        "That page cursor is invalid.",
        code=ErrorCode.VALIDATION_ERROR,
        fields={"cursor": "invalid"},
    )
    if exc is not None:
        err.__cause__ = exc
    return err


def _decode_cursor(cursor: str, sort: str) -> tuple[Any, uuid.UUID]:
    """The sort key value and id of the last row on the previous page, for this sort."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        kind, value, pid = raw.split("|", 2)
        key: Any = datetime.fromisoformat(value) if kind == "newest" else int(value)
        project_id = uuid.UUID(pid)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise _bad_cursor(exc) from exc
    if kind != sort:  # a cursor from another sort order would skip or repeat rows
        raise _bad_cursor()
    return key, project_id


def _cursor_value(project: Project, sort: str) -> str:
    if sort == "budget":
        return str(project.budget_paisa)
    if sort == "deadline":
        return str(project.deadline_days)
    return project.created_at.isoformat()


async def _skill_names(
    db: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    if not project_ids:
        return {}
    rows = await db.execute(
        select(ProjectSlot.project_id, Skill.name)
        .join(Skill, Skill.id == ProjectSlot.skill_id)
        .where(ProjectSlot.project_id.in_(project_ids))
        .order_by(Skill.name)
    )
    out: dict[uuid.UUID, list[str]] = {pid: [] for pid in project_ids}
    for pid, name in rows:
        if name not in out[pid]:
            out[pid].append(name)
    return out


def _card(project: Project, skills: list[str], now: datetime) -> ProjectCard:
    return ProjectCard(
        id=project.id,
        title=project.title,
        summary=project.summary,
        status=project.status.value,
        budget_paisa=project.budget_paisa,
        deadline_days=project.deadline_days,
        team_size=project.team_size,
        bidding_deadline=project.bidding_deadline,
        skills=skills,
        created_at=project.created_at,
        open_for_bids=project.status == ProjectStatus.BIDDING
        and (project.bidding_deadline is None or project.bidding_deadline > now),
    )


def _taking_bids(now: datetime) -> Any:
    return (Project.status == ProjectStatus.BIDDING) & (
        Project.bidding_deadline.is_(None) | (Project.bidding_deadline > now)
    )


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_SKILL_FILTERS = 20


def _clean(value: str) -> str:
    """Search text as profile one-line fields are cleaned: no control characters (PostgreSQL
    rejects NUL in text, which was a 500), NFC, trimmed."""
    return unicodedata.normalize("NFC", _CONTROL.sub("", value)).strip()


def _keyset(stmt: Any, sort: str, cursor: str | None) -> Any:
    """Order by (sort key, id) and start after the cursor's row, so every sort pages without
    gaps or repeats; a tampered cursor can only move the starting point."""
    key_col: Any
    if sort == "budget":
        key_col, descending = Project.budget_paisa, True
    elif sort == "deadline":
        key_col, descending = Project.deadline_days, False
    else:
        key_col, descending = Project.created_at, True
    if cursor is not None:
        key, c_id = _decode_cursor(cursor, sort)
        beyond = key_col < key if descending else key_col > key
        stmt = stmt.where(beyond | ((key_col == key) & (Project.id < c_id)))
    return stmt.order_by(key_col.desc() if descending else key_col.asc(), Project.id.desc())


async def search(
    db: AsyncSession,
    *,
    q: str | None = None,
    skills: list[str] | None = None,
    budget_min: int | None = None,
    budget_max: int | None = None,
    deadline_max: int | None = None,
    team_size: int | None = None,
    sort: str = "newest",
    cursor: str | None = None,
    limit: int = 20,
    now: datetime | None = None,
) -> Page[ProjectCard]:
    if sort not in SORTS:
        raise DomainError(
            f"Unknown sort '{sort}'.", code=ErrorCode.VALIDATION_ERROR, fields={"sort": "invalid"}
        )
    limit = max(1, min(limit, MAX_LIMIT))
    q = _clean(q) if q else None
    skills = [name for name in (_clean(s) for s in skills or []) if name] or None
    if skills and len(skills) > MAX_SKILL_FILTERS:
        raise DomainError(
            f"Choose at most {MAX_SKILL_FILTERS} skills.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"skills": "too_many"},
        )
    now = now or get_clock().now()

    stmt = select(Project).where(_taking_bids(now))
    if q:
        # Title + summary (the stored, GIN-indexed vector) plus the slots' skill names.
        skill_text = (
            select(func.string_agg(Skill.name, " "))
            .join(ProjectSlot, ProjectSlot.skill_id == Skill.id)
            .where(ProjectSlot.project_id == Project.id)
            .correlate(Project)
            .scalar_subquery()
        )
        vector = Project.search_vector.op("||")(
            func.to_tsvector("simple", func.coalesce(skill_text, ""))
        )
        stmt = stmt.where(vector.op("@@")(func.plainto_tsquery("simple", q)))
    if skills:
        stmt = stmt.where(
            select(ProjectSlot.id)
            .join(Skill, Skill.id == ProjectSlot.skill_id)
            .where(ProjectSlot.project_id == Project.id, Skill.name.in_(skills))
            .exists()
        )
    if budget_min is not None:
        stmt = stmt.where(Project.budget_paisa >= budget_min)
    if budget_max is not None:
        stmt = stmt.where(Project.budget_paisa <= budget_max)
    if deadline_max is not None:
        stmt = stmt.where(Project.deadline_days <= deadline_max)
    if team_size is not None:
        stmt = stmt.where(Project.team_size == team_size)

    stmt = _keyset(stmt, sort, cursor)
    stmt = stmt.limit(limit + 1)

    rows = list((await db.scalars(stmt)).all())
    has_more = len(rows) > limit
    page = list(rows[:limit])
    skill_map = await _skill_names(db, [p.id for p in page])
    items = [_card(p, skill_map.get(p.id, []), now) for p in page]
    next_cursor = (
        _encode_cursor(sort, _cursor_value(page[-1], sort), page[-1].id)
        if has_more and page
        else None
    )
    return Page[ProjectCard](items=items, next_cursor=next_cursor)


# --------------------------------------------------------------------------- recommendations


async def forget_recommendations(developer_id: uuid.UUID) -> None:
    """Drop a developer's cached recommendations (after they bid or withdraw)."""
    try:
        await get_redis().delete(_rec_key(developer_id))
    except (RedisError, OSError) as exc:
        log.warning("recommendations_cache_unavailable", error=type(exc).__name__)


async def _typical_days(db: AsyncSession, developer_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Median days the developer asked for per skill, over all their past bids."""
    rows = await db.execute(
        select(ProjectSlot.skill_id, Bid.days_needed)
        .join(ProjectSlot, ProjectSlot.id == Bid.slot_id)
        .where(Bid.developer_id == developer_id)
    )
    per_skill: dict[uuid.UUID, list[int]] = defaultdict(list)
    for skill_id, days in rows:
        per_skill[skill_id].append(days)
    return {skill: int(statistics.median_low(days)) for skill, days in per_skill.items()}


async def recommended(
    db: AsyncSession, developer_id: uuid.UUID, now: datetime | None = None
) -> list[RecommendedProject]:
    """Open projects that fit the developer's skills, usual pace and free hours (§9.16)."""
    try:
        cached = await get_redis().get(_rec_key(developer_id))
    except (RedisError, OSError) as exc:
        log.warning("recommendations_cache_unavailable", error=type(exc).__name__)
        cached = None
    if cached:
        return [RecommendedProject.model_validate(r) for r in json.loads(cached)]

    now = now or get_clock().now()
    result = await _recommend(db, developer_id, now)
    try:
        await get_redis().set(
            _rec_key(developer_id),
            json.dumps([r.model_dump(mode="json") for r in result]),
            ex=RECOMMENDED_CACHE_SECONDS,
        )
    except (RedisError, OSError) as exc:
        log.warning("recommendations_cache_unavailable", error=type(exc).__name__)
    return result


async def _recommend(
    db: AsyncSession, developer_id: uuid.UUID, now: datetime
) -> list[RecommendedProject]:
    skill_ids = await bidrepo.developer_skill_ids(db, developer_id)
    if not skill_ids:
        return []
    already = (
        select(Bid.project_id)
        .where(Bid.developer_id == developer_id, Bid.status == BidStatus.ACTIVE)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Project, ProjectSlot.skill_id)
            .join(ProjectSlot, ProjectSlot.project_id == Project.id)
            .where(
                _taking_bids(now),
                ProjectSlot.skill_id.in_(skill_ids),
                Project.id.notin_(already),
            )
            .order_by(Project.created_at.desc())
            .limit(RECOMMENDED_CANDIDATES)
        )
    ).all()
    projects: dict[uuid.UUID, Project] = {}
    matched: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for project, skill_id in rows:
        projects[project.id] = project
        matched[project.id].add(skill_id)

    typical = await _typical_days(db, developer_id)
    hours = (await bidrepo.profile_hours_by_developer(db, [developer_id])).get(developer_id, 20)
    commitment = min(20, hours)
    reservations = [
        avail.Reservation(avail.Period(r.from_date, r.to_date), r.hours_per_week)
        for r in (await bidrepo.confirmed_reservations_by_developer(db, [developer_id])).get(
            developer_id, []
        )
    ]
    picked: list[tuple[int, Project, list[uuid.UUID]]] = []
    for pid, project in projects.items():
        fitting = [
            s for s in matched[pid] if s not in typical or project.deadline_days >= typical[s]
        ]
        if not fitting:
            continue
        start = project.start_date or now.date()
        period = avail.Period(start, start + timedelta(days=project.deadline_days))
        if not avail.is_feasible(reservations, period, commitment, hours):
            continue
        picked.append((len(fitting), project, fitting))
    picked.sort(key=lambda t: (-t[0], -t[1].created_at.timestamp(), str(t[1].id)))
    picked = picked[:RECOMMENDED_LIMIT]

    skill_map = await _skill_names(db, [p.id for _, p, _ in picked])
    names = dict(
        (await db.execute(select(Skill.id, Skill.name).where(Skill.id.in_(skill_ids))))
        .tuples()
        .all()
    )
    return [
        RecommendedProject(
            project=_card(p, skill_map.get(p.id, []), now),
            skill_match_count=n,
            matched_skills=sorted(names.get(s, "") for s in fitting),
            typical_days=min((typical[s] for s in fitting if s in typical), default=None),
        )
        for n, p, fitting in picked
    ]


async def get_public(
    db: AsyncSession, project_id: uuid.UUID, now: datetime | None = None
) -> ProjectDetail:
    """One non-DRAFT project with its slots for the bid sheet (limited columns, no bids)."""
    project = await db.get(Project, project_id)
    if project is None or project.status == ProjectStatus.DRAFT:
        raise NotFoundError
    rows = await db.execute(
        select(ProjectSlot, Skill.name)
        .join(Skill, Skill.id == ProjectSlot.skill_id)
        .where(ProjectSlot.project_id == project_id)
        .order_by(Skill.name)
    )
    slots = [
        SlotCard(id=s.id, label=s.label, skill=name, skill_id=s.skill_id, count=s.count)
        for s, name in rows
    ]
    card = _card(project, [sc.skill for sc in slots], now or get_clock().now())
    return ProjectDetail(**card.model_dump(), requirements=project.requirements, slots=slots)
