"""Reading a background job (spec §10.3, D107): its requester or an admin; anyone else, and
any unknown id, gets 404. Row-level security (`jobs_select`) enforces the same rule."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Principal
from app.core.errors import NotFoundError
from app.models.foundation import Job
from app.schemas.jobs import JobOut


async def get_job(db: AsyncSession, principal: Principal, job_id: uuid.UUID) -> JobOut:
    job = await db.scalar(select(Job).where(Job.id == job_id))
    if job is None or (job.requested_by != principal.user_id and not principal.is_admin):
        raise NotFoundError()
    return JobOut(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        error_code=job.error_code,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
