"""Transactional email: templates, outbox enqueue, SMTP delivery (spec §12, §14.7, §15.6).

Emails are written to `email_outbox` (by `app.services.outbox`) in the same
transaction as the business change and delivered by the `email.send` job.
Templates are plain Python strings: every value is HTML-escaped for the HTML
part and stripped of control characters for both parts; headers are validated
so user input can never inject extra headers.
"""

from __future__ import annotations

import html
import re
import smtplib
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage
from string import Template
from typing import Any

from app.core.config import Settings

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HEADER_UNSAFE = re.compile(r"[\r\n]")
SMTP_TIMEOUT_SECONDS = 10
MAX_ADDRESS_LENGTH = 254


@dataclass(frozen=True)
class EmailTemplate:
    """Subject and bodies with `$placeholders`."""

    subject: str
    text: str
    html: str


TEMPLATES: dict[str, EmailTemplate] = {
    "verify_email": EmailTemplate(
        subject="Verify your DevSync email",
        text="Hi $name,\n\nConfirm your email address: $link\n\nThe link expires in 24 hours.",
        html='<p>Hi $name,</p><p><a href="$link">Confirm your email address</a></p>'
        "<p>The link expires in 24 hours.</p>",
    ),
    "reset_password": EmailTemplate(
        subject="Reset your DevSync password",
        text="Hi $name,\n\nChoose a new password: $link\n\nThe link expires in 30 minutes. "
        "If you didn't ask for this, you can ignore this email.",
        html='<p>Hi $name,</p><p><a href="$link">Choose a new password</a></p>'
        "<p>The link expires in 30 minutes. If you didn't ask for this, ignore this email.</p>",
    ),
    "account_exists": EmailTemplate(
        subject="Someone tried to register with your email",
        text="Hi $name,\n\nSomeone tried to create a DevSync account with this email. "
        "If it was you, sign in instead: $link",
        html="<p>Hi $name,</p><p>Someone tried to create a DevSync account with this email. "
        'If it was you, <a href="$link">sign in instead</a>.</p>',
    ),
    "account_locked": EmailTemplate(
        subject="Your DevSync account is temporarily locked",
        text="Hi $name,\n\nAfter several failed sign-in attempts your account is locked for "
        "$minutes minutes. If this wasn't you, reset your password: $link",
        html="<p>Hi $name,</p><p>After several failed sign-in attempts your account is locked "
        'for $minutes minutes. If this wasn\'t you, <a href="$link">reset your password</a>.</p>',
    ),
    "new_device": EmailTemplate(
        subject="New sign-in to your DevSync account",
        text="Hi $name,\n\nYour account was signed in to from a new device ($device). "
        "If this wasn't you, sign out all devices and change your password: $link",
        html="<p>Hi $name,</p><p>Your account was signed in to from a new device ($device). "
        'If this wasn\'t you, <a href="$link">secure your account</a>.</p>',
    ),
    "password_changed": EmailTemplate(
        subject="Your DevSync password was changed",
        text="Hi $name,\n\nYour password was changed and other devices were signed out. "
        "If this wasn't you, reset it now: $link",
        html="<p>Hi $name,</p><p>Your password was changed and other devices were signed out. "
        'If this wasn\'t you, <a href="$link">reset it now</a>.</p>',
    ),
}


def _clean(value: Any) -> str:
    return _CONTROL.sub("", str(value))[:500]


def render(template: str, payload: dict[str, Any]) -> tuple[str, str, str]:
    """Return (subject, text, html). Unknown templates raise KeyError."""
    t = TEMPLATES[template]
    clean = {k: _clean(v) for k, v in payload.items()}
    escaped = {k: html.escape(v, quote=True) for k, v in clean.items()}
    return (
        Template(t.subject).safe_substitute(clean),
        Template(t.text).safe_substitute(clean),
        Template(t.html).safe_substitute(escaped),
    )


def validate_address(address: str) -> str:
    """Reject header-injection attempts and malformed addresses."""
    if _HEADER_UNSAFE.search(address) or len(address) > MAX_ADDRESS_LENGTH or "@" not in address:
        raise ValueError("invalid email address")
    return address


def build_message(
    settings: Settings, to: str, template: str, payload: dict[str, Any]
) -> EmailMessage:
    """MIME message with plain-text and HTML parts."""
    subject, text, html_body = render(template, payload)
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    local, _, domain = validate_address(to).partition("@")
    msg["To"] = Address(addr_spec=f"{local}@{domain}")
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_via_smtp(settings: Settings, message: EmailMessage) -> None:
    """Blocking SMTP send with a timeout (runs inside the RQ worker)."""
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
