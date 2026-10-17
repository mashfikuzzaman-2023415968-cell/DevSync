"""Profile, portfolio, evidence and file queries (no business rules).

Everything runs under the caller's row-level-security context, so a query for another user's
row simply finds nothing. Cross-user reads go through the SECURITY DEFINER functions of
migration 0004 (`public_developer_profile`, `file_access`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import column, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profiles import (
    Certificate,
    ClientProfile,
    DeveloperProfile,
    DeveloperSkill,
    ExternalReview,
    PortfolioImage,
    PortfolioItem,
    Skill,
    StoredFile,
)

# --------------------------------------------------------------------------- skills


async def list_skills(db: AsyncSession, *, active_only: bool = True) -> Sequence[Skill]:
    stmt = select(Skill).order_by(Skill.name)
    if active_only:
        stmt = stmt.where(Skill.active.is_(True))
    return (await db.scalars(stmt)).all()


async def existing_skill_ids(db: AsyncSession, ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    """Which of `ids` are active skills."""
    if not ids:
        return set()
    rows = await db.scalars(select(Skill.id).where(Skill.id.in_(ids), Skill.active.is_(True)))
    return set(rows.all())


async def developer_skills(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[DeveloperSkill, Skill]]:
    stmt = (
        select(DeveloperSkill, Skill)
        .join(Skill, Skill.id == DeveloperSkill.skill_id)
        .where(DeveloperSkill.user_id == user_id)
        .order_by(Skill.name)
    )
    return [(ds, s) for ds, s in (await db.execute(stmt)).all()]


async def replace_developer_skills(
    db: AsyncSession, user_id: uuid.UUID, levels: Sequence[tuple[uuid.UUID, int]]
) -> None:
    await db.execute(delete(DeveloperSkill).where(DeveloperSkill.user_id == user_id))
    db.add_all(
        DeveloperSkill(user_id=user_id, skill_id=skill_id, self_level=level)
        for skill_id, level in levels
    )
    await db.flush()


# --------------------------------------------------------------------------- profiles


async def get_developer_profile(db: AsyncSession, user_id: uuid.UUID) -> DeveloperProfile | None:
    return await db.scalar(select(DeveloperProfile).where(DeveloperProfile.user_id == user_id))


async def get_or_create_developer_profile(db: AsyncSession, user_id: uuid.UUID) -> DeveloperProfile:
    row = await get_developer_profile(db, user_id)
    if row is None:
        row = DeveloperProfile(user_id=user_id)
        db.add(row)
        await db.flush()
        await db.refresh(row)
    return row


async def get_client_profile(db: AsyncSession, user_id: uuid.UUID) -> ClientProfile | None:
    return await db.scalar(select(ClientProfile).where(ClientProfile.user_id == user_id))


async def get_or_create_client_profile(db: AsyncSession, user_id: uuid.UUID) -> ClientProfile:
    row = await get_client_profile(db, user_id)
    if row is None:
        row = ClientProfile(user_id=user_id)
        db.add(row)
        await db.flush()
        await db.refresh(row)
    return row


async def public_developer_profile(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any] | None:
    """Visibility-filtered public fields (NULL when the caller may not see the profile)."""
    value: dict[str, Any] | None = await db.scalar(select(func.public_developer_profile(user_id)))
    return value


# --------------------------------------------------------------------------- files


async def add_file(db: AsyncSession, row: StoredFile) -> StoredFile:
    db.add(row)
    await db.flush()
    return row


async def get_files(db: AsyncSession, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, StoredFile]:
    if not ids:
        return {}
    rows = await db.scalars(select(StoredFile).where(StoredFile.id.in_(ids)))
    return {f.id: f for f in rows.all()}


@dataclass(frozen=True)
class FileLocation:
    """Where a downloadable file lives (from `file_access`)."""

    storage_key: uuid.UUID
    mime_type: str
    original_name: str


async def file_access(db: AsyncSession, file_id: uuid.UUID) -> FileLocation | None:
    """The file's location if the caller may download it, else None."""
    stmt: Any = select(
        column("storage_key"), column("mime_type"), column("original_name")
    ).select_from(func.file_access(file_id))
    row = (await db.execute(stmt)).first()
    return FileLocation(row[0], str(row[1]), str(row[2])) if row else None


async def mark_files_deleted(db: AsyncSession, ids: Sequence[uuid.UUID], now: datetime) -> None:
    """Soft-delete (the file content is removed by the cleanup job)."""
    for f in (await get_files(db, ids)).values():
        f.deleted_at = now
        f.attached_at = None
    await db.flush()


# --------------------------------------------------------------------------- portfolio


async def list_portfolio(db: AsyncSession, user_id: uuid.UUID) -> Sequence[PortfolioItem]:
    stmt = (
        select(PortfolioItem)
        .where(PortfolioItem.user_id == user_id)
        .order_by(PortfolioItem.position, PortfolioItem.created_at)
    )
    return (await db.scalars(stmt)).all()


async def lock_portfolio(db: AsyncSession, user_id: uuid.UUID) -> Sequence[PortfolioItem]:
    """The caller's items, locked (serialises add/reorder/delete for one developer)."""
    stmt = (
        select(PortfolioItem)
        .where(PortfolioItem.user_id == user_id)
        .order_by(PortfolioItem.position, PortfolioItem.created_at)
        .with_for_update()
    )
    return (await db.scalars(stmt)).all()


async def get_portfolio_item(
    db: AsyncSession, item_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> PortfolioItem | None:
    stmt = select(PortfolioItem).where(
        PortfolioItem.id == item_id, PortfolioItem.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update()
    return await db.scalar(stmt)


async def images_of(
    db: AsyncSession, item_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[PortfolioImage, StoredFile]]]:
    out: dict[uuid.UUID, list[tuple[PortfolioImage, StoredFile]]] = {i: [] for i in item_ids}
    if not item_ids:
        return out
    stmt = (
        select(PortfolioImage, StoredFile)
        .join(StoredFile, StoredFile.id == PortfolioImage.file_id)
        .where(PortfolioImage.portfolio_item_id.in_(item_ids))
        .order_by(PortfolioImage.position, PortfolioImage.created_at)
    )
    for img, f in (await db.execute(stmt)).all():
        out[img.portfolio_item_id].append((img, f))
    return out


async def get_portfolio_image(
    db: AsyncSession, item_id: uuid.UUID, image_id: uuid.UUID
) -> PortfolioImage | None:
    return await db.scalar(
        select(PortfolioImage).where(
            PortfolioImage.id == image_id, PortfolioImage.portfolio_item_id == item_id
        )
    )


async def delete_row(db: AsyncSession, row: object) -> None:
    await db.delete(row)
    await db.flush()


# --------------------------------------------------------------------------- evidence


async def list_certificates(db: AsyncSession, user_id: uuid.UUID) -> Sequence[Certificate]:
    stmt = (
        select(Certificate).where(Certificate.user_id == user_id).order_by(Certificate.created_at)
    )
    return (await db.scalars(stmt)).all()


async def get_certificate(
    db: AsyncSession, cert_id: uuid.UUID, user_id: uuid.UUID
) -> Certificate | None:
    return await db.scalar(
        select(Certificate).where(Certificate.id == cert_id, Certificate.user_id == user_id)
    )


async def count_certificates(db: AsyncSession, user_id: uuid.UUID) -> int:
    value = await db.scalar(
        select(func.count()).select_from(Certificate).where(Certificate.user_id == user_id)
    )
    return int(value or 0)


async def list_external_reviews(db: AsyncSession, user_id: uuid.UUID) -> Sequence[ExternalReview]:
    stmt = (
        select(ExternalReview)
        .where(ExternalReview.developer_id == user_id)
        .order_by(ExternalReview.created_at)
    )
    return (await db.scalars(stmt)).all()


async def get_external_review(
    db: AsyncSession, review_id: uuid.UUID, user_id: uuid.UUID
) -> ExternalReview | None:
    return await db.scalar(
        select(ExternalReview).where(
            ExternalReview.id == review_id, ExternalReview.developer_id == user_id
        )
    )


async def count_external_reviews(db: AsyncSession, user_id: uuid.UUID) -> int:
    value = await db.scalar(
        select(func.count())
        .select_from(ExternalReview)
        .where(ExternalReview.developer_id == user_id)
    )
    return int(value or 0)


# --------------------------------------------------------------------------- cleanup (worker)


async def purgeable_files(db: AsyncSession, cutoff: datetime, limit: int) -> Sequence[StoredFile]:
    """Deleted files, and files never attached that are older than `cutoff` (SYSTEM context)."""
    stmt = (
        select(StoredFile)
        .where(
            (StoredFile.deleted_at.is_not(None))
            | (StoredFile.attached_at.is_(None) & (StoredFile.created_at < cutoff))
        )
        .order_by(StoredFile.created_at)
        .limit(limit)
    )
    return (await db.scalars(stmt)).all()


async def known_storage_keys(db: AsyncSession, keys: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    """Which of `keys` still belong to a file row (SYSTEM context)."""
    if not keys:
        return set()
    rows = await db.scalars(select(StoredFile.storage_key).where(StoredFile.storage_key.in_(keys)))
    return set(rows.all())
