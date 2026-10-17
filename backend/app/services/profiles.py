"""Developer and client profiles, skills, portfolio and evidence (spec §7.2, §10.2 Profiles).

Every function acts for the signed-in caller under row-level security; another user's ids
simply aren't found (→ 404). Writes are audited and commit at the end.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, InvalidStateTransition, NotFoundError
from app.models.profiles import (
    Certificate,
    ExternalReview,
    FileKind,
    PortfolioImage,
    PortfolioItem,
    ProfileVisibility,
    StoredFile,
    VerificationStatus,
)
from app.repositories import profiles as repo
from app.schemas.profiles import (
    CertificateOut,
    CertificateUpdate,
    ClientProfileOut,
    ClientProfileUpdate,
    DeveloperProfileOut,
    DeveloperProfileUpdate,
    DeveloperPublicProfile,
    DeveloperSkillOut,
    ExternalReviewOut,
    FileOut,
    PortfolioImageOut,
    PortfolioItemCreate,
    PortfolioItemOut,
    PortfolioItemUpdate,
    PortfolioReorder,
    SkillOut,
    SkillsUpdate,
)
from app.services.context import Ctx
from app.services.files import store_upload
from app.uploads.storage import Readable

MAX_PORTFOLIO_ITEMS = 20
MAX_IMAGES_PER_ITEM = 5
MAX_CERTIFICATES = 20
MAX_EXTERNAL_REVIEWS = 20


async def _audit(
    ctx: Ctx,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    after: dict[str, Any] | None = None,
) -> None:
    await write_audit(
        ctx.db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        after=after,
    )


def _changes(body: BaseModel, nullable: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Fields the client actually sent; null is only accepted for nullable fields."""
    data = body.model_dump(exclude_unset=True)
    bad = {
        k: "This field can't be empty." for k, v in data.items() if v is None and k not in nullable
    }
    if bad:
        raise DomainError(code=ErrorCode.VALIDATION_ERROR, fields=bad)
    return data


def _file_out(f: StoredFile) -> FileOut:
    return FileOut(
        id=f.id,
        name=f.original_name,
        mime_type=f.mime_type,
        size_bytes=f.size_bytes,
        width=f.width,
        height=f.height,
    )


# --------------------------------------------------------------------------- skills


async def list_skills(db: AsyncSession) -> list[SkillOut]:
    return [
        SkillOut(id=s.id, name=s.name, domain=s.domain.value) for s in await repo.list_skills(db)
    ]


async def _skills_out(db: AsyncSession, user_id: uuid.UUID) -> list[DeveloperSkillOut]:
    return [
        DeveloperSkillOut(
            skill_id=s.id, name=s.name, domain=s.domain.value, self_level=ds.self_level
        )
        for ds, s in await repo.developer_skills(db, user_id)
    ]


async def replace_skills(ctx: Ctx, body: SkillsUpdate) -> list[DeveloperSkillOut]:
    ids = [s.skill_id for s in body.skills]
    known = await repo.existing_skill_ids(ctx.db, ids)
    unknown = {
        f"skills.{i}.skill_id": "Unknown skill." for i, sid in enumerate(ids) if sid not in known
    }
    if unknown:
        raise DomainError(code=ErrorCode.VALIDATION_ERROR, fields=unknown)
    await repo.replace_developer_skills(
        ctx.db, ctx.uid, [(s.skill_id, s.self_level) for s in body.skills]
    )
    await _audit(
        ctx,
        "profile.skills",
        "developer_profile",
        ctx.uid,
        {"skills": {str(s.skill_id): s.self_level for s in body.skills}},
    )
    await ctx.db.commit()
    return await _skills_out(ctx.db, ctx.uid)


# --------------------------------------------------------------------------- developer profile


async def get_developer_profile(ctx: Ctx) -> DeveloperProfileOut:
    row = await repo.get_developer_profile(ctx.db, ctx.uid)
    skills = await _skills_out(ctx.db, ctx.uid)
    if row is None:  # not created until the first save; show the defaults
        return DeveloperProfileOut(
            headline="",
            bio="",
            hours_per_week=20,
            github_username=None,
            timezone="Asia/Dhaka",
            visibility="PUBLIC",
            skills=skills,
            updated_at=None,
        )
    return DeveloperProfileOut(
        headline=row.headline,
        bio=row.bio,
        hours_per_week=row.hours_per_week,
        github_username=row.github_username,
        timezone=row.timezone,
        visibility=row.visibility.value,
        skills=skills,
        updated_at=row.updated_at,
    )


async def update_developer_profile(ctx: Ctx, body: DeveloperProfileUpdate) -> DeveloperProfileOut:
    data = _changes(body, nullable=frozenset({"github_username"}))
    if "visibility" in data:  # store the enum, not the string (the ORM keeps what it is given)
        data["visibility"] = ProfileVisibility(data["visibility"])
    row = await repo.get_or_create_developer_profile(ctx.db, ctx.uid)
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = ctx.now
    await _audit(
        ctx, "profile.update", "developer_profile", row.id, {k: str(v) for k, v in data.items()}
    )
    await ctx.db.commit()
    return await get_developer_profile(ctx)


# --------------------------------------------------------------------------- client profile


async def get_client_profile(ctx: Ctx) -> ClientProfileOut:
    row = await repo.get_client_profile(ctx.db, ctx.uid)
    if row is None:
        return ClientProfileOut(organization="", description="", website=None, updated_at=None)
    return ClientProfileOut(
        organization=row.organization,
        description=row.description,
        website=row.website,
        updated_at=row.updated_at,
    )


async def update_client_profile(ctx: Ctx, body: ClientProfileUpdate) -> ClientProfileOut:
    data = _changes(body, nullable=frozenset({"website"}))
    row = await repo.get_or_create_client_profile(ctx.db, ctx.uid)
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = ctx.now
    await _audit(ctx, "client_profile.update", "client_profile", row.id, data)
    await ctx.db.commit()
    return await get_client_profile(ctx)


# --------------------------------------------------------------------------- public view


async def developer_view(db: AsyncSession, developer_id: uuid.UUID) -> DeveloperPublicProfile:
    """What the caller (anonymous or signed in) may see; hidden and missing look the same."""
    data = await repo.public_developer_profile(db, developer_id)
    if data is None:
        raise NotFoundError
    return DeveloperPublicProfile.model_validate(data)


# --------------------------------------------------------------------------- portfolio


async def _items_out(db: AsyncSession, items: Sequence[PortfolioItem]) -> list[PortfolioItemOut]:
    images = await repo.images_of(db, [i.id for i in items])
    return [
        PortfolioItemOut(
            id=i.id,
            title=i.title,
            description=i.description,
            url=i.url,
            skill_ids=list(i.skill_ids),
            position=i.position,
            images=[
                PortfolioImageOut(id=img.id, file=_file_out(f), position=img.position)
                for img, f in images[i.id]
            ],
        )
        for i in items
    ]


async def _item_out(db: AsyncSession, item: PortfolioItem) -> PortfolioItemOut:
    return (await _items_out(db, [item]))[0]


async def _check_skill_ids(db: AsyncSession, ids: Sequence[uuid.UUID]) -> None:
    known = await repo.existing_skill_ids(db, ids)
    if any(i not in known for i in ids):
        raise DomainError(code=ErrorCode.VALIDATION_ERROR, fields={"skill_ids": "Unknown skill."})


async def list_portfolio(ctx: Ctx) -> list[PortfolioItemOut]:
    return await _items_out(ctx.db, await repo.list_portfolio(ctx.db, ctx.uid))


async def create_portfolio_item(ctx: Ctx, body: PortfolioItemCreate) -> PortfolioItemOut:
    await _check_skill_ids(ctx.db, body.skill_ids)
    items = await repo.lock_portfolio(ctx.db, ctx.uid)
    if len(items) >= MAX_PORTFOLIO_ITEMS:
        raise DomainError(
            f"A portfolio can have at most {MAX_PORTFOLIO_ITEMS} items.",
            code=ErrorCode.INVALID_STATE,
        )
    item = PortfolioItem(
        user_id=ctx.uid,
        title=body.title,
        description=body.description,
        url=body.url,
        skill_ids=list(body.skill_ids),
        position=len(items),
    )
    ctx.db.add(item)
    await ctx.db.flush()
    await _audit(ctx, "portfolio.create", "portfolio_item", item.id, {"title": item.title})
    await ctx.db.commit()
    return await _item_out(ctx.db, item)


async def _own_item(ctx: Ctx, item_id: uuid.UUID, *, lock: bool = False) -> PortfolioItem:
    item = await repo.get_portfolio_item(ctx.db, item_id, ctx.uid, lock=lock)
    if item is None:
        raise NotFoundError
    return item


async def update_portfolio_item(
    ctx: Ctx, item_id: uuid.UUID, body: PortfolioItemUpdate
) -> PortfolioItemOut:
    data = _changes(body, nullable=frozenset({"url"}))
    if "skill_ids" in data:
        await _check_skill_ids(ctx.db, data["skill_ids"])
    item = await _own_item(ctx, item_id, lock=True)
    for key, value in data.items():
        setattr(item, key, value)
    item.updated_at = ctx.now
    await _audit(ctx, "portfolio.update", "portfolio_item", item.id, {"fields": sorted(data)})
    await ctx.db.commit()
    return await _item_out(ctx.db, item)


async def delete_portfolio_item(ctx: Ctx, item_id: uuid.UUID) -> None:
    items = list(await repo.lock_portfolio(ctx.db, ctx.uid))
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        raise NotFoundError
    images = (await repo.images_of(ctx.db, [item.id]))[item.id]
    await repo.mark_files_deleted(ctx.db, [f.id for _, f in images], ctx.now)
    await repo.delete_row(ctx.db, item)
    for position, other in enumerate(i for i in items if i.id != item_id):
        other.position = position
    await _audit(ctx, "portfolio.delete", "portfolio_item", item_id)
    await ctx.db.commit()


async def reorder_portfolio(ctx: Ctx, body: PortfolioReorder) -> list[PortfolioItemOut]:
    items = await repo.lock_portfolio(ctx.db, ctx.uid)
    by_id = {i.id: i for i in items}
    if set(body.ids) != set(by_id):
        raise DomainError(
            code=ErrorCode.VALIDATION_ERROR,
            fields={"ids": "List every portfolio item exactly once."},
        )
    for position, item_id in enumerate(body.ids):
        by_id[item_id].position = position
    await _audit(
        ctx, "portfolio.reorder", "portfolio_item", None, {"ids": [str(i) for i in body.ids]}
    )
    await ctx.db.commit()
    return await _items_out(ctx.db, [by_id[i] for i in body.ids])


async def add_portfolio_image(
    ctx: Ctx, item_id: uuid.UUID, source: Readable, filename: str | None
) -> PortfolioItemOut:
    item = await _own_item(ctx, item_id, lock=True)  # serialises uploads to the same item
    existing = (await repo.images_of(ctx.db, [item.id]))[item.id]
    if len(existing) >= MAX_IMAGES_PER_ITEM:
        raise DomainError(
            f"An item can have at most {MAX_IMAGES_PER_ITEM} images.", code=ErrorCode.INVALID_STATE
        )
    stored = await store_upload(ctx, source, FileKind.PORTFOLIO_IMAGE, filename)
    ctx.db.add(PortfolioImage(portfolio_item_id=item.id, file_id=stored.id, position=len(existing)))
    await ctx.db.flush()
    await _audit(ctx, "portfolio.image_add", "portfolio_item", item.id, {"file_id": str(stored.id)})
    await ctx.db.commit()
    return await _item_out(ctx.db, item)


async def delete_portfolio_image(
    ctx: Ctx, item_id: uuid.UUID, image_id: uuid.UUID
) -> PortfolioItemOut:
    item = await _own_item(ctx, item_id, lock=True)
    image = await repo.get_portfolio_image(ctx.db, item.id, image_id)
    if image is None:
        raise NotFoundError
    file_id = image.file_id
    await repo.delete_row(ctx.db, image)
    await repo.mark_files_deleted(ctx.db, [file_id], ctx.now)
    for position, (img, _f) in enumerate((await repo.images_of(ctx.db, [item.id]))[item.id]):
        img.position = position
    await _audit(
        ctx, "portfolio.image_delete", "portfolio_item", item.id, {"file_id": str(file_id)}
    )
    await ctx.db.commit()
    return await _item_out(ctx.db, item)


# --------------------------------------------------------------------------- certificates


async def _certs_out(db: AsyncSession, certs: Sequence[Certificate]) -> list[CertificateOut]:
    files = await repo.get_files(db, [c.file_id for c in certs])
    return [
        CertificateOut(
            id=c.id,
            title=c.title,
            issuer=c.issuer,
            file=_file_out(files[c.file_id]),
            status=c.status.value,
            reason=c.reason,
            created_at=c.created_at,
        )
        for c in certs
    ]


async def list_certificates(ctx: Ctx) -> list[CertificateOut]:
    return await _certs_out(ctx.db, await repo.list_certificates(ctx.db, ctx.uid))


async def create_certificate(
    ctx: Ctx, *, title: str, issuer: str, source: Readable, filename: str | None
) -> CertificateOut:
    if await repo.count_certificates(ctx.db, ctx.uid) >= MAX_CERTIFICATES:
        raise DomainError(
            f"You can add at most {MAX_CERTIFICATES} certificates.", code=ErrorCode.INVALID_STATE
        )
    stored = await store_upload(ctx, source, FileKind.CERTIFICATE, filename)
    cert = Certificate(user_id=ctx.uid, title=title, issuer=issuer, file_id=stored.id)
    ctx.db.add(cert)
    await ctx.db.flush()
    await _audit(
        ctx, "certificate.create", "certificate", cert.id, {"title": title, "issuer": issuer}
    )
    await ctx.db.commit()
    await ctx.db.refresh(cert)
    return (await _certs_out(ctx.db, [cert]))[0]


async def _own_certificate(ctx: Ctx, cert_id: uuid.UUID) -> Certificate:
    cert = await repo.get_certificate(ctx.db, cert_id, ctx.uid)
    if cert is None:
        raise NotFoundError
    return cert


async def update_certificate(
    ctx: Ctx, cert_id: uuid.UUID, body: CertificateUpdate
) -> CertificateOut:
    data = _changes(body)
    cert = await _own_certificate(ctx, cert_id)
    if cert.status is not VerificationStatus.PENDING:
        raise InvalidStateTransition(cert.status.value, ["delete"])
    for key, value in data.items():
        setattr(cert, key, value)
    cert.updated_at = ctx.now
    await _audit(ctx, "certificate.update", "certificate", cert.id, data)
    await ctx.db.commit()
    return (await _certs_out(ctx.db, [cert]))[0]


async def delete_certificate(ctx: Ctx, cert_id: uuid.UUID) -> None:
    cert = await _own_certificate(ctx, cert_id)
    file_id = cert.file_id
    await repo.delete_row(ctx.db, cert)
    await repo.mark_files_deleted(ctx.db, [file_id], ctx.now)
    await _audit(ctx, "certificate.delete", "certificate", cert_id)
    await ctx.db.commit()


# --------------------------------------------------------------------------- external reviews


def normalise_rating(rating: Decimal, scale: int) -> Decimal:
    """Rating on its platform's scale → 0–1 with 3 decimals (exact Decimal maths)."""
    if scale < 1 or rating < 0 or rating > scale:
        raise DomainError(
            code=ErrorCode.VALIDATION_ERROR, fields={"rating": f"Use a rating from 0 to {scale}."}
        )
    return (rating / Decimal(scale)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


async def _reviews_out(db: AsyncSession, rows: Sequence[ExternalReview]) -> list[ExternalReviewOut]:
    files = await repo.get_files(db, [r.evidence_file_id for r in rows])
    return [
        ExternalReviewOut(
            id=r.id,
            source=r.source,
            rating_norm=r.rating_norm,
            project_date=r.project_date,
            file=_file_out(files[r.evidence_file_id]),
            status=r.status.value,
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]


async def list_external_reviews(ctx: Ctx) -> list[ExternalReviewOut]:
    return await _reviews_out(ctx.db, await repo.list_external_reviews(ctx.db, ctx.uid))


async def create_external_review(
    ctx: Ctx,
    *,
    source_name: str,
    rating: Decimal,
    scale: int,
    project_date: date,
    source: Readable,
    filename: str | None,
) -> ExternalReviewOut:
    if project_date > ctx.now.date():
        raise DomainError(
            code=ErrorCode.VALIDATION_ERROR, fields={"project_date": "Use a date in the past."}
        )
    rating_norm = normalise_rating(rating, scale)
    if await repo.count_external_reviews(ctx.db, ctx.uid) >= MAX_EXTERNAL_REVIEWS:
        raise DomainError(
            f"You can add at most {MAX_EXTERNAL_REVIEWS} reviews.", code=ErrorCode.INVALID_STATE
        )
    stored = await store_upload(ctx, source, FileKind.EXTERNAL_REVIEW, filename)
    review = ExternalReview(
        developer_id=ctx.uid,
        source=source_name,
        rating_norm=rating_norm,
        project_date=project_date,
        evidence_file_id=stored.id,
    )
    ctx.db.add(review)
    await ctx.db.flush()
    await _audit(
        ctx,
        "external_review.create",
        "external_review",
        review.id,
        {"source": source_name, "rating_norm": str(rating_norm)},
    )
    await ctx.db.commit()
    await ctx.db.refresh(review)
    return (await _reviews_out(ctx.db, [review]))[0]


async def delete_external_review(ctx: Ctx, review_id: uuid.UUID) -> None:
    review = await repo.get_external_review(ctx.db, review_id, ctx.uid)
    if review is None:
        raise NotFoundError
    file_id = review.evidence_file_id
    await repo.delete_row(ctx.db, review)
    await repo.mark_files_deleted(ctx.db, [file_id], ctx.now)
    await _audit(ctx, "external_review.delete", "external_review", review_id)
    await ctx.db.commit()
