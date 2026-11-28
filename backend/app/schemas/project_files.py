"""Project files in the workspace (spec §10.2 Files, §14.9; D147)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.tasks import PersonRef


class ProjectFileLink(BaseModel):
    """A task that uses the file as evidence (screen 35's "linked task/milestone")."""

    task_id: uuid.UUID
    task_title: str
    milestone_title: str


class ProjectFile(BaseModel):
    """A file in the project's Files tab. Download through `GET /files/{id}/download`."""

    id: uuid.UUID
    name: str = Field(description="Sanitized name; the extension matches the detected type.")
    mime: str
    size_bytes: int
    uploaded_by: PersonRef
    created_at: datetime
    can_delete: bool = Field(description="The caller uploaded it or leads the team.")
    links: list[ProjectFileLink]


_FILE = {
    "id": "5a0e9b1c-3d2f-4e6a-8b7c-9d0e1f2a3b4c",
    "name": "wireframes.pdf",
    "mime": "application/pdf",
    "size_bytes": 204800,
    "uploaded_by": {"id": "0f3c2b1a-9e8d-4c7b-a6f5-e4d3c2b1a098", "name": "Farhan Hossain"},
    "created_at": "2026-12-14T05:30:00Z",
    "can_delete": True,
    "links": [
        {
            "task_id": "7c6b5a49-3827-4615-a5b4-c3d2e1f0a9b8",
            "task_title": "UI kit",
            "milestone_title": "UI design",
        }
    ],
}
EX_PROJECT_FILE = _FILE
EX_PROJECT_FILE_PAGE = {"items": [_FILE], "next_cursor": None}
