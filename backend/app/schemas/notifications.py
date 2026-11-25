"""In-app notification schemas (spec §10.2 Notifications, §13.5 #18; D122)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


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


EX_NOTIFICATION = {
    "id": "5f0c2b7e-3d4a-4e8b-9c1d-2a3b4c5d6e7f",
    "type": "INVITATION_SELECTED",
    "title": "You were selected",
    "body": "The client chose you for the React developer role on “Online ordering system”.",
    "link_path": "/dev",
    "read_at": None,
    "created_at": "2026-11-24T06:00:00Z",
}
