"""Public homepage data and client error reports (spec §13.11 #3, §15.7)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PublicStats(BaseModel):
    """Live platform numbers for the homepage. A number is present only once the phase that
    produces it exists; the homepage never shows zeros (spec §13.11 #3)."""

    model_config = ConfigDict(extra="forbid")

    developers: int | None = Field(
        None, ge=0, description="Verified, active developer accounts.", examples=[42]
    )


class ClientErrorReport(BaseModel):
    """A short, already-truncated summary of a frontend error (sanitized again server-side)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=500, examples=["TypeError: x is undefined"])
    stack: str | None = Field(None, max_length=4000)
    path: str = Field(min_length=1, max_length=300, pattern=r"^/", examples=["/settings"])
    kind: Literal["render", "chunk", "unhandled"]
    request_id: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
