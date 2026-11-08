"""The developer SMS inbox: read and clear the texts kept by `integrations.sms` (OTP sandbox).

Only mounted where `Settings.sms_sandbox_enabled` (development, test, the offline demo stack).
"""

from __future__ import annotations

import json

from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.logging import get_logger
from app.integrations.sms import SANDBOX_KEY, SANDBOX_MAX
from app.schemas.sms_sandbox import SandboxSms, SandboxSmsList

log = get_logger(__name__)


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isascii() and c.isdigit())


async def list_messages(redis: Redis, phone: str | None, limit: int) -> SandboxSmsList:
    """Newest first; `phone` keeps only texts to that number (digits compared, `+` ignored)."""
    raw = await redis.lrange(SANDBOX_KEY, 0, SANDBOX_MAX - 1)
    wanted = _digits(phone) if phone else ""
    messages: list[SandboxSms] = []
    for item in raw:
        try:
            msg = SandboxSms.model_validate(json.loads(item))
        except (ValueError, ValidationError):
            log.warning("sandbox_sms_unreadable")  # never fails the page for one bad entry
            continue
        if wanted and _digits(msg.to) != wanted:
            continue
        messages.append(msg)
        if len(messages) >= limit:
            break
    newest = next((m.code for m in messages if m.code), None)
    return SandboxSmsList(messages=messages, newest_code=newest)


async def clear_messages(redis: Redis) -> None:
    """Empty the inbox."""
    await redis.delete(SANDBOX_KEY)
