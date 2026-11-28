"""Comment and discussion contracts (spec §7.5, §10.2; D146, D169). Bodies are plain text
(≤ 4000); mentions are user ids the client picked from the member list (≤ 10), filtered to the
project's participants by the server. A deleted comment comes back without its text."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.workspace_types import CommentTarget
from app.schemas.common import StrictRequest
from app.schemas.tasks import PersonRef

MAX_MENTIONS = 10
EDIT_WINDOW_SECONDS = 15 * 60

Body = Annotated[str, Field(min_length=1, max_length=4000)]
Mentions = Annotated[list[uuid.UUID], Field(default_factory=list, max_length=MAX_MENTIONS)]


class _Distinct(StrictRequest):
    mention_ids: Mentions

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if len(set(self.mention_ids)) != len(self.mention_ids):
            raise ValueError("mention_ids lists someone twice")
        return self


class CommentCreate(_Distinct):
    target_type: CommentTarget
    target_id: uuid.UUID
    body: Body
    reply_to_id: uuid.UUID | None = None


class CommentPatch(StrictRequest):
    """Only the text changes, within 15 minutes of posting (D146)."""

    body: Body


class CommentOut(BaseModel):
    id: uuid.UUID
    target_type: Literal["TASK", "MILESTONE", "CHECKIN", "DISCUSSION_POST"]
    target_id: uuid.UUID
    author: PersonRef
    body: str = Field(description="Empty when deleted (the text stays private, D146)")
    mentions: list[PersonRef]
    reply_to_id: uuid.UUID | None
    created_at: datetime
    edited: bool
    deleted: bool
    can_edit: bool = Field(description="The caller wrote it and the 15-minute window is open")
    version: int


class ThreadCreate(_Distinct):
    title: Annotated[str, Field(min_length=3, max_length=120)]
    body: Body


class ThreadOut(BaseModel):
    id: uuid.UUID
    title: str
    created_by: PersonRef
    created_at: datetime
    last_post_at: datetime
    post_count: int = Field(ge=0)


class PostCreate(_Distinct):
    body: Body
    reply_to_id: uuid.UUID | None = None


EX_PERSON = {"id": "5f0c6c1e-2a43-4d9b-9a53-0a1f5a1b2c3d", "name": "Nusrat Jahan"}
EX_COMMENT = {
    "id": "6c7d8e9f-0a1b-4c2d-8e3f-4a5b6c7d8e9f",
    "target_type": "TASK",
    "target_id": "9b2e7d4a-6c1f-4a8e-b3d2-1f0e9c8b7a65",
    "author": {"id": "7a6b5c4d-3e2f-4a1b-9c8d-7e6f5a4b3c2d", "name": "Arif Hossain"},
    "body": "@Nusrat Jahan can you check the paging?",
    "mentions": [EX_PERSON],
    "reply_to_id": None,
    "created_at": "2026-11-23T06:00:00Z",
    "edited": False,
    "deleted": False,
    "can_edit": True,
    "version": 1,
}
EX_COMMENT_PAGE = {"items": [EX_COMMENT], "next_cursor": None}
EX_THREAD = {
    "id": "8e9f0a1b-2c3d-4e5f-9a6b-7c8d9e0f1a2b",
    "title": "Release checklist",
    "created_by": EX_PERSON,
    "created_at": "2026-11-23T06:00:00Z",
    "last_post_at": "2026-11-23T07:00:00Z",
    "post_count": 3,
}
EX_THREAD_PAGE = {"items": [EX_THREAD], "next_cursor": None}
