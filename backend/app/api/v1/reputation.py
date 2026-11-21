"""Reputation endpoints (spec §10.2 Reputation, §13.5 #16, §14.13 row 6).

Both are reads: nothing in the API writes reputation; the engine computes it from server-side
evidence in SYSTEM jobs. `GET /developers/{id}/reputation` follows the profile's visibility (a
profile the caller may not see is 404). `GET /me/reputation/history` is the developer's own.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import acting, app_settings
from app.core.config import Settings
from app.schemas.common import Page, error_responses
from app.schemas.reputation import (
    EX_HISTORY_ITEM,
    EX_REPUTATION,
    DeveloperReputation,
    ReputationHistoryItem,
)
from app.services import reputation as svc
from app.services.context import Ctx

router = APIRouter(tags=["reputation"])

AppSettings = Annotated[Settings, Depends(app_settings)]
Viewer = Annotated[Ctx, Depends(acting("reputation.read"))]
Owner = Annotated[Ctx, Depends(acting("reputation.history"))]


@router.get(
    "/developers/{developer_id}/reputation",
    summary="A developer's reputation",
    response_model=DeveloperReputation,
    responses={
        200: {"content": {"application/json": {"example": EX_REPUTATION}}},
        **error_responses(401, 403, 404, 422, 429),
    },
)
async def developer_reputation(
    ctx: Viewer, developer_id: uuid.UUID, settings: AppSettings
) -> DeveloperReputation:
    """The six parameters, competency and performance, per-skill competency and, for the
    developer themself while a newcomer, where the starting values come from. Hidden profiles
    and unknown ids are 404."""
    return await svc.developer_reputation(ctx, developer_id, production=settings.is_production)


@router.get(
    "/me/reputation/history",
    summary="How my reputation changed",
    response_model=Page[ReputationHistoryItem],
    responses={
        200: {"content": {"application/json": {
            "example": {"items": [EX_HISTORY_ITEM], "next_cursor": None}
        }}},
        **error_responses(401, 403, 422, 429),
    },
)  # fmt: skip
async def my_history(
    ctx: Owner,
    *,
    cursor: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ReputationHistoryItem]:
    """Newest project first, cursor-paged (§10.1), each with a plain-language reason per change."""
    return await svc.my_history(ctx, cursor=cursor, limit=limit)
