"""Admin area (spec §14.17). Everyone but a TOTP-verified admin gets 404.

Phase 1 exposes only the admin's own security status; Phase 12 adds the console.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import now, require
from app.core.authz import Principal
from app.schemas.auth import AdminSessionResponse
from app.schemas.common import error_responses

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/session",
    summary="Admin session security status",
    response_model=AdminSessionResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "user_id": "6f1c3a52-6a3e-4c0e-9d4c-2f1b0b6e2a11",
                        "totp_verified": True,
                        "step_up_active": False,
                    }
                }
            }
        },
        **error_responses(401, 403, 404),
    },
)
async def admin_session(
    principal: Annotated[Principal, Depends(require("admin.access"))],
) -> AdminSessionResponse:
    """Used by the admin UI to confirm access before loading its bundle."""
    return AdminSessionResponse(
        user_id=principal.user_id,
        totp_verified=principal.totp_verified,
        step_up_active=principal.has_step_up(now()),
    )
