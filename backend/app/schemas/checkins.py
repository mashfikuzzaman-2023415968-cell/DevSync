"""Weekly check-in contracts (spec §7.5, §10.2 Check-ins; D145). `week_start`, `on_time`, the
member and the project are set by the server; sending them is a 422 (mass assignment)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import StrictRequest
from app.schemas.tasks import PersonRef

Text2000 = Annotated[str, Field(min_length=1, max_length=2000)]


class CheckinCreate(StrictRequest):
    done: Text2000
    next: Text2000
    blockers: Annotated[str, Field(max_length=2000)] | None = None
    confidence: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def _blank_blockers(self) -> Self:
        if self.blockers == "":
            self.blockers = None
        return self


class CheckinOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    member: PersonRef
    week_start: date
    done: str
    next: str
    blockers: str | None
    confidence: int
    on_time: bool
    created_at: datetime
    reply_count: int = Field(ge=0)


class ThisWeek(BaseModel):
    week_start: date
    due_at: datetime = Field(description="Tuesday 23:59 Asia/Dhaka: posted by then is on time")
    posted: bool = Field(description="Whether the caller (a member) has checked in this week")
    missing: list[PersonRef] = Field(description="Active members who haven't checked in yet")


class CheckinFeed(BaseModel):
    """Newest week first, then by member; plus this week's state."""

    items: list[CheckinOut]
    next_cursor: str | None = None
    this_week: ThisWeek


EX_CHECKIN = {
    "id": "4b5c6d7e-8f90-4a1b-9c2d-3e4f5a6b7c8d",
    "member_id": "1f2e3d4c-5b6a-4978-8a9b-0c1d2e3f4a5b",
    "member": {"id": "5f0c6c1e-2a43-4d9b-9a53-0a1f5a1b2c3d", "name": "Nusrat Jahan"},
    "week_start": "2026-11-23",
    "done": "Finished the stock table and its filters.",
    "next": "Paging and the low-stock view.",
    "blockers": None,
    "confidence": 4,
    "on_time": True,
    "created_at": "2026-11-23T06:00:00Z",
    "reply_count": 0,
}
EX_FEED = {
    "items": [EX_CHECKIN],
    "next_cursor": None,
    "this_week": {
        "week_start": "2026-11-23",
        "due_at": "2026-11-24T17:59:59.999999Z",
        "posted": True,
        "missing": [{"id": "7a6b5c4d-3e2f-4a1b-9c8d-7e6f5a4b3c2d", "name": "Arif Hossain"}],
    },
}
