"""In-app notification schemas (spec §10.2 Notifications, §12, §13.5 #18–19; D122, D162)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.notification_types import Category
from app.schemas.common import StrictRequest


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    link_path: str | None  # a validated relative app path (§14.6), or null
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class ReadAll(BaseModel):
    marked: int


class PreferenceItem(BaseModel):
    """One §12 row with the caller's switches (defaults where never changed)."""

    category: str
    label: str
    in_app: bool
    email: bool
    email_available: bool = Field(description="§12 has an email for this row")


class Preferences(BaseModel):
    """Account and security emails aren't listed: they are always sent."""

    items: list[PreferenceItem]


class PreferenceSet(StrictRequest):
    category: Category
    in_app: bool
    email: bool


class PreferencesUpdate(StrictRequest):
    """The rows to change (others keep their values); each category at most once."""

    items: list[PreferenceSet] = Field(min_length=1, max_length=len(Category))


EX_NOTIFICATION = {
    "id": "5f0c2b7e-3d4a-4e8b-9c1d-2a3b4c5d6e7f",
    "type": "INVITATION_SELECTED",
    "title": "You were selected",
    "body": "The client chose you for the React developer role on “Online ordering system”.",
    "link_path": "/dev",
    "read_at": None,
    "created_at": "2026-11-24T06:00:00Z",
}
EX_PREFERENCES = {
    "items": [
        {
            "category": "mentions",
            "label": "Someone mentioned you",
            "in_app": True,
            "email": False,
            "email_available": True,
        },
        {
            "category": "blockers",
            "label": "A teammate reported a blocker",
            "in_app": True,
            "email": False,
            "email_available": False,
        },
    ]
}
EX_PREFERENCES_UPDATE = {"items": [{"category": "mentions", "in_app": True, "email": True}]}
