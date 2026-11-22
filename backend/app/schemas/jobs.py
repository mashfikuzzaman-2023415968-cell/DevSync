"""Generic background job status (spec §10.3, D107)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]


class JobOut(BaseModel):
    """A job as its requester (or an admin) sees it. No payload, no internal references."""

    id: uuid.UUID
    type: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


EX_JOB = {
    "id": "0b7c1a52-8d1e-4f55-9a3e-2f1c6f2d9b10",
    "type": "formation.run",
    "status": "RUNNING",
    "progress": 42,
    "error_code": None,
    "created_at": "2026-11-22T06:00:00Z",
    "started_at": "2026-11-22T06:00:01Z",
    "finished_at": None,
}
