"""SMS provider selection and the offline demo's Mailpit provider (spec §14.4, §17.0)."""

from __future__ import annotations

import base64
import secrets
import smtplib
from email.message import EmailMessage
from typing import Any

import pytest

from app.core.config import Environment, Settings, production_problems
from app.integrations import sms
from app.integrations.sms import ConsoleSms, MailpitSms, sms_sender

pytestmark = pytest.mark.unit


def demo_production(**overrides: object) -> Settings:
    """The demo stack's production settings (docker-compose.demo.yml)."""
    values: dict[str, object] = {
        "DEVSYNC_ENV": Environment.PRODUCTION,
        "SECRET_KEY": base64.b64encode(secrets.token_bytes(64)).decode(),
        "SMS_PROVIDER": "mailpit",
        "SMTP_HOST": "mailpit",
        "PUBLIC_ORIGIN": "https://localhost",
        "REDIS_URL": "redis://:pw@redis:6379/0",
        "ALLOWED_HOSTS": "localhost,api",
        "CAPTCHA_HMAC_KEY": "k" * 32,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_demo_production_settings_pass_validation() -> None:
    assert production_problems(demo_production()) == []


@pytest.mark.parametrize("host", ["smtp.example.com", "", "mailpit.example.com", "MAILPIT"])
def test_mailpit_sms_is_refused_in_production_with_a_real_relay(host: str) -> None:
    problems = production_problems(demo_production(SMTP_HOST=host))
    assert any("SMS_PROVIDER=mailpit" in p for p in problems), problems


def test_console_sms_still_refused_in_production() -> None:
    problems = production_problems(demo_production(SMS_PROVIDER="console"))
    assert any("SMS_PROVIDER=console" in p for p in problems), problems


def test_sender_per_environment() -> None:
    redis: Any = object()
    assert isinstance(sms_sender(demo_production(), redis), MailpitSms)
    dev = demo_production(DEVSYNC_ENV=Environment.DEVELOPMENT, SMS_PROVIDER="console")
    assert isinstance(sms_sender(dev, redis), ConsoleSms)
    test = demo_production(DEVSYNC_ENV=Environment.TEST)
    assert isinstance(sms_sender(test, redis), sms.TestInboxSms)


@pytest.mark.parametrize(
    "overrides",
    [
        {"SMS_PROVIDER": "console"},  # console in production
        {"SMS_PROVIDER": "twilio"},  # not built yet
        {"SMS_PROVIDER": ""},
    ],
)
def test_unknown_or_unsafe_providers_fail_closed(overrides: dict[str, object]) -> None:
    with pytest.raises(RuntimeError, match="not available"):
        sms_sender(demo_production(**overrides), object())  # type: ignore[arg-type]


def test_mailpit_sender_refuses_a_real_relay_even_if_validation_was_skipped() -> None:
    with pytest.raises(RuntimeError, match="SMTP_HOST=mailpit"):
        MailpitSms(demo_production(SMTP_HOST="smtp.example.com"))


def test_mailpit_message_goes_to_the_reserved_domain() -> None:
    msg = MailpitSms(demo_production()).build("+8801712345678", "Your DevSync code is 123456")
    assert msg["To"] == "8801712345678@sms.devsync.local"
    assert msg["Subject"] == "SMS to +8801712345678"
    assert msg.get_content().strip() == "Your DevSync code is 123456"


def test_header_injection_in_the_phone_is_stripped() -> None:
    msg = MailpitSms(demo_production()).build("+880\r\nBcc: x@evil.test", "code")
    assert msg["To"] == "880@sms.devsync.local"
    assert msg["Subject"] == "SMS to +880"
    assert msg["Bcc"] is None


async def test_send_hands_the_message_to_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[EmailMessage] = []
    monkeypatch.setattr(sms, "send_via_smtp", lambda _s, m: sent.append(m))
    await MailpitSms(demo_production()).send("+8801712345678", "Your DevSync code is 654321")
    assert len(sent) == 1
    assert "654321" in sent[0].get_content()


@pytest.mark.parametrize("error", [OSError("down"), smtplib.SMTPServerDisconnected("gone")])
async def test_a_mailpit_outage_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(_s: Settings, _m: EmailMessage) -> None:
        raise error

    monkeypatch.setattr(sms, "send_via_smtp", boom)
    await MailpitSms(demo_production()).send("+8801712345678", "Your DevSync code is 111111")
