"""SMS delivery behind an interface (spec §14.4, §6.1).

- `console`: prints the code to the log **only in development** (startup refuses it in
  production via config validation);
- `noop`: test environment; keeps the last message per phone in Redis for 10 minutes
  so the test-only seed router and E2E tests can read the OTP;
- a real provider adapter is added at deployment (Phase 15).
"""

from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis

from app.core.config import Environment, Settings
from app.core.logging import get_logger

log = get_logger(__name__)
TEST_INBOX_PREFIX = "test:sms:"
TEST_INBOX_TTL = 600


class SmsSender(Protocol):
    """Sends one text message."""

    async def send(self, phone_e164: str, text: str) -> None:
        """Deliver `text` to `phone_e164`."""


class ConsoleSms:
    """Development only: writes the message to the log (the phone is masked by redaction)."""

    async def send(self, phone_e164: str, text: str) -> None:
        # The OTP is deliberately logged in development so you can sign up without SMS.
        log.info("dev_sms", to_last4=phone_e164[-4:], message=text)


class TestInboxSms:
    """Test only: stores the last message per phone in Redis."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def send(self, phone_e164: str, text: str) -> None:
        await self.redis.set(TEST_INBOX_PREFIX + phone_e164, text, ex=TEST_INBOX_TTL)


def sms_sender(settings: Settings, redis: Redis) -> SmsSender:
    """Pick the sender for this environment (fail closed for unknown providers)."""
    if settings.DEVSYNC_ENV is Environment.TEST:
        return TestInboxSms(redis)
    if settings.SMS_PROVIDER == "console" and settings.DEVSYNC_ENV is Environment.DEVELOPMENT:
        return ConsoleSms()
    raise RuntimeError(f"SMS provider '{settings.SMS_PROVIDER}' is not available here")
