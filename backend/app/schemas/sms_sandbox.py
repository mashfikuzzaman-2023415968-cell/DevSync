"""Responses of the developer SMS inbox (the OTP sandbox)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SandboxSms(BaseModel):
    """One text message DevSync "sent" (never delivered to a real phone)."""

    id: str
    to: str
    text: str
    code: str | None
    at: datetime


class SandboxSmsList(BaseModel):
    """The newest texts first, and the newest one-time code for quick copying."""

    messages: list[SandboxSms]
    newest_code: str | None
