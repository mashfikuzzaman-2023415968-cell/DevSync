"""SMS delivery behind an interface (spec §14.4, §6.1).

- `console`: prints the code to the log **only in development** (startup refuses it in
  production via config validation);
- `noop`: test environment; keeps the last message per phone in Redis for 10 minutes
  so the test-only seed router and E2E tests can read the OTP;
- `mailpit`: the offline demo stack (`make demo-up`, production settings, no internet): each
  text is delivered as an email to the stack's local Mailpit, where the presenter reads the
  code. Production validation refuses it unless `SMTP_HOST` is that local catcher;
- a real provider adapter is added at deployment (Phase 15).
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

from redis.asyncio import Redis

from app.core.config import DEMO_MAIL_CAPTURE_HOST, Environment, Settings
from app.core.logging import get_logger
from app.integrations.email import send_via_smtp

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


MAILPIT_SMS_DOMAIN = "sms.devsync.local"


class MailpitSms:
    """Offline demo only: hands each text to the local Mailpit as an email.

    The message goes to `<phone digits>@sms.devsync.local`, a reserved domain no real relay
    delivers, and only when `SMTP_HOST` is the stack's own Mailpit (checked again here, so a
    mis-set provider can never send codes through a real mail server).
    """

    def __init__(self, settings: Settings) -> None:
        if settings.SMTP_HOST != DEMO_MAIL_CAPTURE_HOST:
            raise RuntimeError("SMS provider 'mailpit' needs SMTP_HOST=mailpit")
        self.settings = settings

    def build(self, phone_e164: str, text: str) -> EmailMessage:
        """The email standing in for one text message."""
        digits = "".join(c for c in phone_e164 if c.isascii() and c.isdigit())
        msg = EmailMessage()
        msg["From"] = self.settings.EMAIL_FROM
        msg["To"] = f"{digits}@{MAILPIT_SMS_DOMAIN}"
        msg["Subject"] = f"SMS to +{digits}"
        msg.set_content(text)
        return msg

    async def send(self, phone_e164: str, text: str) -> None:
        try:
            await asyncio.to_thread(send_via_smtp, self.settings, self.build(phone_e164, text))
        except (OSError, smtplib.SMTPException) as exc:
            # Like a lost text: the account change is already saved and "Resend code" works.
            log.warning("demo_sms_failed", to_last4=phone_e164[-4:], error=type(exc).__name__)


def sms_sender(settings: Settings, redis: Redis) -> SmsSender:
    """Pick the sender for this environment (fail closed for unknown providers)."""
    if settings.DEVSYNC_ENV is Environment.TEST:
        return TestInboxSms(redis)
    if settings.SMS_PROVIDER == "console" and settings.DEVSYNC_ENV is Environment.DEVELOPMENT:
        return ConsoleSms()
    if settings.SMS_PROVIDER == "mailpit":
        return MailpitSms(settings)
    raise RuntimeError(f"SMS provider '{settings.SMS_PROVIDER}' is not available here")
