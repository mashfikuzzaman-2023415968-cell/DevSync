"""The caller's own account (spec §10.2 Me)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, app_settings, redis_client, require
from app.core.authz import Principal
from app.core.config import Settings
from app.schemas.auth import MeResponse, MeUpdateRequest
from app.schemas.common import error_responses
from app.services.auth import account
from app.services.auth.common import AuthDeps

router = APIRouter(tags=["me"])
SettingsDep = Annotated[Settings, Depends(app_settings)]
EXAMPLE = {
    "id": "6f1c3a52-6a3e-4c0e-9d4c-2f1b0b6e2a11",
    "email": "rahim@devsync.local",
    "phone_e164": "+8801712345678",
    "display_name": "Rahim",
    "role": "CLIENT",
    "status": "ACTIVE",
    "email_verified": True,
    "phone_verified": True,
    "totp_enabled": False,
    "totp_verified": False,
    "payment_verified": False,
    "created_at": "2026-10-17T05:00:00Z",
}


@router.get(
    "/me",
    summary="My account",
    response_model=MeResponse,
    responses={
        200: {"content": {"application/json": {"example": EXAMPLE}}},
        **error_responses(401, 403, 404),
    },
)
async def get_me(
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.read"))],
) -> MeResponse:
    """Works for PENDING accounts too (the verification screen needs it)."""
    return await account.get_me(AuthDeps(db, settings, redis_client()), principal)


@router.patch(
    "/me",
    summary="Update my account basics",
    response_model=MeResponse,
    responses={
        200: {"content": {"application/json": {"example": EXAMPLE}}},
        **error_responses(401, 403, 404, 422),
    },
)
async def patch_me(
    body: MeUpdateRequest,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.update"))],
) -> MeResponse:
    """Only the display name is editable in Phase 1 (role, status, email are server-owned)."""
    deps = AuthDeps(db, settings, redis_client())
    await account.update_me(deps, principal, body.display_name)
    return await account.get_me(deps, principal)
