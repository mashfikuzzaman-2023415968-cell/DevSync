"""Marketplace search and recommendations (spec §10 Marketplace, §9.16). Read-only.

Search is full-text over the project `search_vector` (title + summary, via `plainto_tsquery`,
§14.7) with whitelisted filters and keyset (cursor) pagination. It only ever lists projects open
for bids and never exposes any bid data (§14.5). Recommendations are the open projects needing one
of the developer's skills that they haven't bid on, ranked by skill-match count then newest.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, ErrorCode, NotFoundError
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

SORTS = {"newest", "budget", "deadline"}
MAX_LIMIT = 100
RECOMMENDED_LIMIT = 12


def _encode_cursor(created_at: datetime, project_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{project_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        iso, pid = raw.split("|", 1)
        return datetime.fromisoformat(iso), uuid.UUID(pid)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise DomainError(
            "That page cursor is invalid.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"cursor": "invalid"},
        ) from exc


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
        out[pid].append(name)
    return out


def _card(project: Project, skills: list[str]) -> ProjectCard:
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
    )


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_SKILL_FILTERS = 20


def _clean(value: str) -> str:
    """Search text as profile one-line fields are cleaned: no control characters (PostgreSQL
    rejects NUL in text, which was a 500), NFC, trimmed."""
    return unicodedata.normalize("NFC", _CONTROL.sub("", value)).strip()


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

    stmt = select(Project).where(Project.status == ProjectStatus.BIDDING)
    if q:
        stmt = stmt.where(Project.search_vector.op("@@")(func.plainto_tsquery("simple", q)))
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

    # Keyset pagination on (created_at, id) descending, so a tampered cursor can't scan arbitrarily.
    order: tuple[Any, Any]
    if sort == "budget":
        order = (Project.budget_paisa.desc(), Project.id.desc())
    elif sort == "deadline":
        order = (Project.deadline_days.asc(), Project.id.desc())
    else:
        order = (Project.created_at.desc(), Project.id.desc())
    if cursor is not None and sort == "newest":
        c_created, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            (Project.created_at < c_created)
            | ((Project.created_at == c_created) & (Project.id < c_id))
        )
    stmt = stmt.order_by(*order).limit(limit + 1)

    rows = list((await db.scalars(stmt)).all())
    has_more = len(rows) > limit
    page = list(rows[:limit])
    skill_map = await _skill_names(db, [p.id for p in page])
    items = [_card(p, skill_map.get(p.id, [])) for p in page]
    next_cursor = (
        _encode_cursor(page[-1].created_at, page[-1].id)
        if has_more and sort == "newest" and page
        else None
    )
    return Page[ProjectCard](items=items, next_cursor=next_cursor)


async def recommended(db: AsyncSession, developer_id: uuid.UUID) -> list[RecommendedProject]:
    """Open projects needing one of the developer's skills they haven't bid on (§9.16)."""
    skill_ids = await bidrepo.developer_skill_ids(db, developer_id)
    if not skill_ids:
        return []
    already = (
        select(Bid.project_id)
        .where(Bid.developer_id == developer_id, Bid.status == BidStatus.ACTIVE)
        .scalar_subquery()
    )
    match_count = func.count(func.distinct(ProjectSlot.skill_id)).label("matches")
    stmt = (
        select(Project, match_count)
        .join(ProjectSlot, ProjectSlot.project_id == Project.id)
        .where(
            Project.status == ProjectStatus.BIDDING,
            ProjectSlot.skill_id.in_(skill_ids),
            Project.id.notin_(already),
        )
        .group_by(Project.id)
        .order_by(match_count.desc(), Project.created_at.desc())
        .limit(RECOMMENDED_LIMIT)
    )
    rows = (await db.execute(stmt)).all()
    skill_map = await _skill_names(db, [p.id for p, _ in rows])
    return [
        RecommendedProject(project=_card(p, skill_map.get(p.id, [])), skill_match_count=int(n))
        for p, n in rows
    ]


async def get_public(db: AsyncSession, project_id: uuid.UUID) -> ProjectDetail:
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
    card = _card(project, [sc.skill for sc in slots])
    return ProjectDetail(**card.model_dump(), requirements=project.requirements, slots=slots)
