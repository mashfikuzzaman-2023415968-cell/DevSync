"""Responses of the developer SMS inbox (the OTP sandbox)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class DemoAccount(BaseModel):
    """A seeded demo account the quick sign-in tab can open (never an administrator)."""

    email: str
    name: str
    role: str


class DemoAccountList(BaseModel):
    """Every seeded demo client and developer."""

    accounts: list[DemoAccount]


class DemoSignInRequest(BaseModel):
    """Which demo account to sign in as."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)


class DemoSignInResponse(BaseModel):
    """Where the browser goes after the quick sign-in."""

    redirect_to: str
