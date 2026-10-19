"""Project, slot, milestone, dependency and baseline queries (no business rules).

Every query runs under the caller's row-level-security context (migration 0005), so a DRAFT
project that isn't the caller's simply isn't found, and a non-owner cannot load another client's
plan. Business rules, validation and CPM live in `services/projects.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.projects import (
    Milestone,
    MilestoneDependency,
    MilestoneSkill,
    PlanBaseline,
    Project,
    ProjectSlot,
)


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    """Load a project visible to the caller (RLS), or None."""
    return await db.get(Project, project_id)


async def list_mine(db: AsyncSession, client_id: uuid.UUID) -> Sequence[Project]:
    """The caller's own projects, newest first."""
    stmt = select(Project).where(Project.client_id == client_id).order_by(Project.created_at.desc())
    return (await db.scalars(stmt)).all()


async def load_slots(db: AsyncSession, project_id: uuid.UUID) -> Sequence[ProjectSlot]:
    stmt = select(ProjectSlot).where(ProjectSlot.project_id == project_id).order_by(ProjectSlot.id)
    return (await db.scalars(stmt)).all()


async def load_milestones(db: AsyncSession, project_id: uuid.UUID) -> Sequence[Milestone]:
    stmt = (
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.position, Milestone.id)
    )
    return (await db.scalars(stmt)).all()


async def load_milestone_skills(
    db: AsyncSession, milestone_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Map each milestone id to its skill ids."""
    if not milestone_ids:
        return {}
    rows = await db.execute(
        select(MilestoneSkill.milestone_id, MilestoneSkill.skill_id).where(
            MilestoneSkill.milestone_id.in_(milestone_ids)
        )
    )
    out: dict[uuid.UUID, list[uuid.UUID]] = {mid: [] for mid in milestone_ids}
    for milestone_id, skill_id in rows.all():
        out[milestone_id].append(skill_id)
    return out


async def load_dependencies(
    db: AsyncSession, project_id: uuid.UUID
) -> Sequence[MilestoneDependency]:
    stmt = (
        select(MilestoneDependency)
        .where(MilestoneDependency.project_id == project_id)
        .order_by(MilestoneDependency.id)
    )
    return (await db.scalars(stmt)).all()


async def delete_slots(db: AsyncSession, project_id: uuid.UUID) -> None:
    await db.execute(delete(ProjectSlot).where(ProjectSlot.project_id == project_id))


async def delete_milestones(db: AsyncSession, project_id: uuid.UUID) -> None:
    # milestone_skills and milestone_dependencies cascade on the milestone/project foreign keys.
    await db.execute(delete(Milestone).where(Milestone.project_id == project_id))


async def delete_dependencies(db: AsyncSession, project_id: uuid.UUID) -> None:
    await db.execute(
        delete(MilestoneDependency).where(MilestoneDependency.project_id == project_id)
    )


async def latest_baseline(db: AsyncSession, project_id: uuid.UUID) -> PlanBaseline | None:
    stmt = (
        select(PlanBaseline)
        .where(PlanBaseline.project_id == project_id)
        .order_by(PlanBaseline.version.desc())
        .limit(1)
    )
    return (await db.scalars(stmt)).first()
