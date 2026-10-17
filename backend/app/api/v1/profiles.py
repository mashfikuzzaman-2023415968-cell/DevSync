"""Profiles, skills, portfolio and evidence (spec §10.2 Profiles, Skills)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.api.deps import DbSession, acting, rate_limit, require
from app.schemas.common import error_responses
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
    PortfolioItemCreate,
    PortfolioItemOut,
    PortfolioItemUpdate,
    PortfolioReorder,
    SkillOut,
    SkillsUpdate,
    SourceName,
    Title,
)
from app.services import profiles as svc
from app.services.context import Ctx

router = APIRouter(tags=["profiles"])

Dev = Annotated[Ctx, Depends(acting("profile.developer"))]
Client = Annotated[Ctx, Depends(acting("profile.client"))]
Upload = Annotated[UploadFile, File(description="The file (type checked by its content).")]
UPLOAD_LIMIT = [Depends(rate_limit("upload"))]

_ID = "6f1c3a52-6a3e-4c0e-9d4c-2f1b0b6e2a11"
_SKILL = {"skill_id": "0b7d4c1e-2f3a-4b5c-8d9e-0f1a2b3c4d5e", "name": "React", "domain": "FRONTEND"}
_FILE = {
    "id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "name": "dashboard.png",
    "mime_type": "image/png",
    "size_bytes": 182044,
    "width": 1600,
    "height": 1000,
}
EX_SKILLS = [{**_SKILL, "self_level": 4}]
EX_PROFILE = {
    "headline": "Frontend developer who likes accessible forms",
    "bio": "Three years of React and TypeScript.",
    "hours_per_week": 20,
    "github_username": "nadia-dev",
    "timezone": "Asia/Dhaka",
    "visibility": "PUBLIC",
    "skills": EX_SKILLS,
    "updated_at": "2026-10-18T05:00:00Z",
}
EX_ITEM = {
    "id": _ID,
    "title": "Clinic booking app",
    "description": "Booking flow with SMS reminders.",
    "url": None,
    "skill_ids": [_SKILL["skill_id"]],
    "position": 0,
    "images": [{"id": "c0ffee00-0000-4000-8000-000000000001", "file": _FILE, "position": 0}],
}
EX_CERT = {
    "id": _ID,
    "title": "AWS Cloud Practitioner",
    "issuer": "Amazon Web Services",
    "file": {**_FILE, "name": "certificate.pdf", "mime_type": "application/pdf"},
    "status": "PENDING",
    "reason": None,
    "created_at": "2026-10-18T05:00:00Z",
}
EX_REVIEW = {
    "id": _ID,
    "source": "Upwork",
    "rating_norm": "0.960",
    "project_date": "2026-03-01",
    "file": {**_FILE, "name": "review.png"},
    "status": "PENDING",
    "reason": None,
    "created_at": "2026-10-18T05:00:00Z",
}
EX_CLIENT = {
    "organization": "Rahim Traders",
    "description": "Wholesale textiles; we need an ordering app.",
    "website": None,
    "updated_at": "2026-10-18T05:00:00Z",
}
EX_PUBLIC = {
    "id": _ID,
    "display_name": "Nadia Rahman",
    "member_since": "2026-10-01T05:00:00Z",
    "headline": EX_PROFILE["headline"],
    "bio": EX_PROFILE["bio"],
    "hours_per_week": 20,
    "github_username": "nadia-dev",
    "visibility": "PUBLIC",
    "skills": EX_SKILLS,
    "verified_scores": [{**_SKILL, "score": "0.800", "at": "2026-10-10T05:00:00Z"}],
    "portfolio": [
        {
            "id": _ID,
            "title": "Clinic booking app",
            "description": "Booking flow with SMS reminders.",
            "url": None,
            "skill_ids": [],
            "image_ids": [_FILE["id"]],
        }
    ],
    "certificates": [{"title": "AWS Cloud Practitioner", "issuer": "Amazon Web Services"}],
}


def _ok(example: Any, *errors: int) -> dict[int | str, dict[str, Any]]:
    return {
        200: {"content": {"application/json": {"example": example}}},
        **error_responses(401, 403, 404, *errors),
    }


def _created(example: Any, *errors: int) -> dict[int | str, dict[str, Any]]:
    return {
        201: {"content": {"application/json": {"example": example}}},
        **error_responses(401, 403, 404, *errors),
    }


# --------------------------------------------------------------------------- skills


@router.get(
    "/skills",
    summary="Skill taxonomy",
    response_model=list[SkillOut],
    dependencies=[Depends(require("catalog.read"))],
    responses=_ok([{"id": _SKILL["skill_id"], "name": "React", "domain": "FRONTEND"}]),
)
async def list_skills(db: DbSession) -> list[SkillOut]:
    """Active skills, by name."""
    return await svc.list_skills(db)


@router.put(
    "/me/skills",
    summary="Replace my skills",
    response_model=list[DeveloperSkillOut],
    responses=_ok(EX_SKILLS, 422),
)
async def put_skills(body: SkillsUpdate, ctx: Dev) -> list[DeveloperSkillOut]:
    """Up to 20 skills, each with a self-assessed level 1–5 (verified scores come from tests)."""
    return await svc.replace_skills(ctx, body)


# --------------------------------------------------------------------------- developer profile


@router.get(
    "/me/developer-profile",
    summary="My developer profile",
    response_model=DeveloperProfileOut,
    responses=_ok(EX_PROFILE),
)
async def get_developer_profile(ctx: Dev) -> DeveloperProfileOut:
    """Defaults are shown until the first save."""
    return await svc.get_developer_profile(ctx)


@router.patch(
    "/me/developer-profile",
    summary="Update my developer profile",
    response_model=DeveloperProfileOut,
    responses=_ok(EX_PROFILE, 422),
)
async def patch_developer_profile(body: DeveloperProfileUpdate, ctx: Dev) -> DeveloperProfileOut:
    """Send only the fields that changed (autosave)."""
    return await svc.update_developer_profile(ctx, body)


# --------------------------------------------------------------------------- client profile


@router.get(
    "/me/client-profile",
    summary="My client profile",
    response_model=ClientProfileOut,
    responses=_ok(EX_CLIENT),
)
async def get_client_profile(ctx: Client) -> ClientProfileOut:
    """Organisation details shown to developers on your projects."""
    return await svc.get_client_profile(ctx)


@router.patch(
    "/me/client-profile",
    summary="Update my client profile",
    response_model=ClientProfileOut,
    responses=_ok(EX_CLIENT, 422),
)
async def patch_client_profile(body: ClientProfileUpdate, ctx: Client) -> ClientProfileOut:
    """Send only the fields that changed; an empty website removes it."""
    return await svc.update_client_profile(ctx, body)


# --------------------------------------------------------------------------- portfolio


@router.get(
    "/me/portfolio",
    summary="My portfolio",
    response_model=list[PortfolioItemOut],
    responses=_ok([EX_ITEM]),
)
async def list_portfolio(ctx: Dev) -> list[PortfolioItemOut]:
    """Items in display order with their images."""
    return await svc.list_portfolio(ctx)


@router.post(
    "/me/portfolio",
    summary="Add a portfolio item",
    status_code=201,
    response_model=PortfolioItemOut,
    responses=_created(EX_ITEM, 409, 422),
)
async def create_portfolio_item(body: PortfolioItemCreate, ctx: Dev) -> PortfolioItemOut:
    """Added at the end; at most 20 items."""
    return await svc.create_portfolio_item(ctx, body)


@router.put(
    "/me/portfolio-order",
    summary="Reorder my portfolio",
    response_model=list[PortfolioItemOut],
    responses=_ok([EX_ITEM], 422),
)
async def reorder_portfolio(body: PortfolioReorder, ctx: Dev) -> list[PortfolioItemOut]:
    """Send every item id once, in the new order."""
    return await svc.reorder_portfolio(ctx, body)


@router.patch(
    "/me/portfolio/{item_id}",
    summary="Update a portfolio item",
    response_model=PortfolioItemOut,
    responses=_ok(EX_ITEM, 422),
)
async def update_portfolio_item(
    item_id: uuid.UUID, body: PortfolioItemUpdate, ctx: Dev
) -> PortfolioItemOut:
    """Send only the fields that changed."""
    return await svc.update_portfolio_item(ctx, item_id, body)


@router.delete(
    "/me/portfolio/{item_id}",
    summary="Delete a portfolio item",
    status_code=204,
    responses=error_responses(401, 403, 404, 422),
)
async def delete_portfolio_item(item_id: uuid.UUID, ctx: Dev) -> Response:
    """Its images are deleted too."""
    await svc.delete_portfolio_item(ctx, item_id)
    return Response(status_code=204)


@router.post(
    "/me/portfolio/{item_id}/images",
    summary="Add an image to a portfolio item",
    status_code=201,
    response_model=PortfolioItemOut,
    dependencies=UPLOAD_LIMIT,
    responses=_created(EX_ITEM, 409, 413, 422, 429),
)
async def add_portfolio_image(item_id: uuid.UUID, file: Upload, ctx: Dev) -> PortfolioItemOut:
    """PNG, JPEG or WebP (≤ MAX_UPLOAD_MB), re-encoded without metadata, ≤ 4096 px; 5 per item."""
    return await svc.add_portfolio_image(ctx, item_id, file, file.filename)


@router.delete(
    "/me/portfolio/{item_id}/images/{image_id}",
    summary="Remove an image from a portfolio item",
    response_model=PortfolioItemOut,
    responses=_ok(EX_ITEM, 422),
)
async def delete_portfolio_image(
    item_id: uuid.UUID, image_id: uuid.UUID, ctx: Dev
) -> PortfolioItemOut:
    """The remaining images keep their order."""
    return await svc.delete_portfolio_image(ctx, item_id, image_id)


# --------------------------------------------------------------------------- certificates


@router.get(
    "/me/certificates",
    summary="My certificates",
    response_model=list[CertificateOut],
    responses=_ok([EX_CERT]),
)
async def list_certificates(ctx: Dev) -> list[CertificateOut]:
    """With their verification status."""
    return await svc.list_certificates(ctx)


@router.post(
    "/me/certificates",
    summary="Upload a certificate",
    status_code=201,
    response_model=CertificateOut,
    dependencies=UPLOAD_LIMIT,
    responses=_created(EX_CERT, 409, 413, 422, 429),
)
async def create_certificate(
    title: Annotated[Title, Form()],
    issuer: Annotated[Title, Form()],
    file: Upload,
    ctx: Dev,
) -> CertificateOut:
    """PDF (≤ 10 MB, no scripts or attachments) or an image; pending until an admin verifies it."""
    return await svc.create_certificate(
        ctx, title=title, issuer=issuer, source=file, filename=file.filename
    )


@router.patch(
    "/me/certificates/{cert_id}",
    summary="Correct a pending certificate",
    response_model=CertificateOut,
    responses=_ok(EX_CERT, 409, 422),
)
async def update_certificate(
    cert_id: uuid.UUID, body: CertificateUpdate, ctx: Dev
) -> CertificateOut:
    """Only while it is pending; a verified or rejected certificate can only be deleted."""
    return await svc.update_certificate(ctx, cert_id, body)


@router.delete(
    "/me/certificates/{cert_id}",
    summary="Delete a certificate",
    status_code=204,
    responses=error_responses(401, 403, 404, 422),
)
async def delete_certificate(cert_id: uuid.UUID, ctx: Dev) -> Response:
    """The file is deleted too."""
    await svc.delete_certificate(ctx, cert_id)
    return Response(status_code=204)


# --------------------------------------------------------------------------- external reviews


@router.get(
    "/me/external-reviews",
    summary="My external reviews",
    response_model=list[ExternalReviewOut],
    responses=_ok([EX_REVIEW]),
)
async def list_external_reviews(ctx: Dev) -> list[ExternalReviewOut]:
    """Reviews from other platforms with their verification status."""
    return await svc.list_external_reviews(ctx)


@router.post(
    "/me/external-reviews",
    summary="Add an external review",
    status_code=201,
    response_model=ExternalReviewOut,
    dependencies=UPLOAD_LIMIT,
    responses=_created(EX_REVIEW, 409, 413, 422, 429),
)
async def create_external_review(
    *,
    source: Annotated[SourceName, Form(description="Platform, e.g. Upwork.")],
    rating: Annotated[Decimal, Form(ge=0, le=100, max_digits=6, decimal_places=2)],
    scale: Annotated[int, Form(ge=1, le=100, description="The platform's top rating, e.g. 5.")],
    project_date: Annotated[date, Form()],
    file: Upload,
    ctx: Dev,
) -> ExternalReviewOut:
    """Evidence: a screenshot, PDF or text export. Counts towards reputation only once verified."""
    return await svc.create_external_review(
        ctx,
        source_name=source,
        rating=rating,
        scale=scale,
        project_date=project_date,
        source=file,
        filename=file.filename,
    )


@router.delete(
    "/me/external-reviews/{review_id}",
    summary="Delete an external review",
    status_code=204,
    responses=error_responses(401, 403, 404, 422),
)
async def delete_external_review(review_id: uuid.UUID, ctx: Dev) -> Response:
    """The evidence file is deleted too."""
    await svc.delete_external_review(ctx, review_id)
    return Response(status_code=204)


# --------------------------------------------------------------------------- viewing developers


@router.get(
    "/developers/{developer_id}",
    summary="A developer's profile",
    response_model=DeveloperPublicProfile,
    dependencies=[Depends(require("catalog.read"))],
    responses=_ok(EX_PUBLIC, 422),
)
async def get_developer(developer_id: uuid.UUID, db: DbSession) -> DeveloperPublicProfile:
    """Respects the developer's visibility (clients-only profiles are hidden from developers)."""
    return await svc.developer_view(db, developer_id)


@router.get(
    "/public/developers/{developer_id}",
    summary="A developer's public profile",
    response_model=DeveloperPublicProfile,
    dependencies=[Depends(rate_limit("public_stats"))],
    responses={
        200: {"content": {"application/json": {"example": EX_PUBLIC}}},
        **error_responses(404, 422, 429),
    },
)
async def get_public_developer(developer_id: uuid.UUID, db: DbSession) -> DeveloperPublicProfile:
    """Never email or phone; a clients-only profile is 'not found' unless a client signed in."""
    return await svc.developer_view(db, developer_id)
