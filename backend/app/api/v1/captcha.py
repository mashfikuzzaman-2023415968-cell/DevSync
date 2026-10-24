"""ALTCHA challenge endpoint (spec §14.16)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, app_settings, rate_limit
from app.core import captcha
from app.core.config import Environment, Settings
from app.core.settings_cache import active_settings
from app.schemas.auth import CaptchaChallenge
from app.schemas.common import error_responses

router = APIRouter(tags=["captcha"])


@router.get(
    "/captcha/challenge",
    summary="Get a proof-of-work challenge for a public form",
    response_model=CaptchaChallenge,
    dependencies=[Depends(rate_limit("captcha_challenge"))],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "algorithm": "SHA-256",
                        "challenge": "a1b2…",
                        "max_number": 50000,
                        "salt": "7a46e7c8?expires=1792213000",
                        "signature": "c0ffee…",
                    }
                }
            }
        },
        **error_responses(429),
    },
)
async def challenge(
    settings: Annotated[Settings, Depends(app_settings)], db: DbSession
) -> CaptchaChallenge:
    """Signed, expires in 5 minutes, each solution usable once. Difficulty from the platform
    settings (`captcha.max_number`)."""
    data = captcha.create_challenge(
        settings.CAPTCHA_HMAC_KEY,
        test_mode=settings.DEVSYNC_ENV is Environment.TEST,
        max_number=(await active_settings(db)).captcha.max_number,
    )
    return CaptchaChallenge(**data)
