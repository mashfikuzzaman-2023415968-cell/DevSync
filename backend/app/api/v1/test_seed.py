"""Test-only helpers (spec §16.2): mounted **only** when DEVSYNC_ENV=test.

`create_app` refuses to include this router in any other environment, and the
production configuration check runs before routers are added. It lets E2E tests
create users in a given state and read codes/links that real users would get by
SMS or email.
"""

from __future__ import annotations

from typing import Annotated, Literal

import pyotp
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis

from app.api.deps import app_settings, redis_client
from app.core.config import Settings
from app.schemas.common import StrictRequest
from app.services.testing import seed

router = APIRouter(prefix="/__test__", tags=["test-only"], include_in_schema=False)


class SeedUserRequest(StrictRequest):
    """User to create."""

    role: Literal["CLIENT", "DEVELOPER", "ADMIN"]
    email: EmailStr
    phone: str | None = Field(default=None, max_length=16)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(default="Test User", max_length=80)
    verified: bool = True
    with_totp: bool = True


class SeedUserResponse(BaseModel):
    """Created user and, for admins, the TOTP secret and recovery codes."""

    user_id: str
    totp_secret: str | None = None
    recovery_codes: list[str] = []


@router.post("/seed/user", response_model=SeedUserResponse)
async def seed_user(
    body: SeedUserRequest, settings: Annotated[Settings, Depends(app_settings)]
) -> SeedUserResponse:
    """Create a user in the requested state."""
    result = await seed.create_user(
        settings,
        role=body.role,
        email=str(body.email),
        phone=body.phone,
        password=body.password,
        display_name=body.display_name,
        verified=body.verified,
        with_totp=body.with_totp,
    )
    return SeedUserResponse(**result)


@router.get("/sms")
async def last_sms(phone: Annotated[str, Query(max_length=16)]) -> dict[str, str | None]:
    """Last text message sent to a phone (the `noop` SMS provider keeps it for tests)."""
    raw = await redis_client().get(f"test:sms:{phone}")
    return {"message": raw.decode() if isinstance(raw, bytes) else raw}


@router.get("/email-link")
async def last_email_link(
    to: Annotated[str, Query(max_length=254)],
    template: Annotated[str, Query(max_length=40)],
) -> dict[str, str | None]:
    """Latest link emailed to `to` with `template` (read from the outbox)."""
    return {"link": await seed.latest_email_link(to, template)}


@router.get("/totp")
async def totp_now(secret: Annotated[str, Query(max_length=64)]) -> dict[str, str]:
    """Current TOTP code for a seeded admin secret."""
    return {"code": pyotp.TOTP(secret).now()}


@router.get("/ratelimits/reset", status_code=204)
async def reset_rate_limits(redis: Annotated[Redis, Depends(redis_client)]) -> Response:
    """Clear rate-limit counters so independent E2E tests from one IP don't throttle each other.

    A GET so it works even while CSRF cookies are rate limited; test environment only."""
    for pattern in ("rl:*", "auth:delay:*"):
        async for key in redis.scan_iter(pattern):
            await redis.delete(key)
    return Response(status_code=204)
