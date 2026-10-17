"""ALTCHA proof-of-work CAPTCHA for public forms (spec §14.16).

The server issues an HMAC-signed challenge (5-minute expiry); the browser finds
the number n with SHA-256(salt + n) = challenge and sends back a base64 payload.
Verification checks the signature, expiry and solution, then records the
challenge in Redis so every solution works exactly once.

Extra layers: a hidden honeypot field (must stay empty) and a minimum fill time
of 2 seconds. A bypass exists only when DEVSYNC_ENV=test; configuration
validation refuses to start if the bypass flag is set anywhere else.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from altcha import v1 as altcha_v1
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import DomainError, ErrorCode

CHALLENGE_TTL_SECONDS = 300
MIN_FILL_MS = 2000
DEFAULT_MAX_NUMBER = 50_000
TEST_MAX_NUMBER = 10
USED_PREFIX = "captcha:used:"
MAX_PAYLOAD_LENGTH = 4096
MAX_SIGNATURE_LENGTH = 256


class CaptchaError(DomainError):
    """Missing, expired, replayed, tampered or wrong solution (generic message)."""

    code = ErrorCode.CAPTCHA_FAILED


def create_challenge(hmac_key: str, *, test_mode: bool = False) -> dict[str, Any]:
    """New signed challenge as a JSON-ready dict."""
    options = altcha_v1.ChallengeOptions(
        algorithm="SHA-256",
        max_number=TEST_MAX_NUMBER if test_mode else DEFAULT_MAX_NUMBER,
        hmac_key=hmac_key,
        expires=datetime.now(UTC) + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    )
    challenge = altcha_v1.create_challenge(options)
    return {
        "algorithm": challenge.algorithm,
        "challenge": challenge.challenge,
        "max_number": challenge.max_number,
        "salt": challenge.salt,
        "signature": challenge.signature,
    }


def _signature_of(payload: str) -> str | None:
    try:
        data = json.loads(base64.b64decode(payload, validate=True).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    signature = data.get("signature") if isinstance(data, dict) else None
    return (
        signature if isinstance(signature, str) and len(signature) <= MAX_SIGNATURE_LENGTH else None
    )


async def verify(
    redis: Redis,
    hmac_key: str,
    *,
    payload: str | None,
    honeypot: str | None,
    started_at_ms: int | None,
    bypass: bool = False,
) -> None:
    """Raise CaptchaError unless the form passed every bot check."""
    if honeypot:
        raise CaptchaError
    if started_at_ms is not None and int(time.time() * 1000) - started_at_ms < MIN_FILL_MS:
        raise CaptchaError
    if bypass:
        return
    if not payload or len(payload) > MAX_PAYLOAD_LENGTH:
        raise CaptchaError
    ok, _err = altcha_v1.verify_solution(payload, hmac_key, check_expires=True)
    if not ok:
        raise CaptchaError
    signature = _signature_of(payload)
    if signature is None:
        raise CaptchaError
    try:
        first_use = await redis.set(
            USED_PREFIX + signature, b"1", nx=True, ex=CHALLENGE_TTL_SECONDS + 60
        )
    except RedisError as exc:
        raise CaptchaError from exc  # fail closed
    if not first_use:
        raise CaptchaError
