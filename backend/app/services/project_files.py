"""Project files: the workspace's Files tab (spec §10.2 Files, §14.9; D147, D173, D175).

- Participants (the client and ACTIVE members) upload while the project is IN_PROGRESS; former
  members, other clients and outsiders get 404, admins 403 until Phase 12 (D173). RLS and
  `file_access()` repeat the participant rule underneath (migration 0016).
- Types are exactly §14.9's through the existing pipeline: images re-encoded, PDF ≤ 10 MB, plain
  text or Markdown ≤ 1 MB; everything else is refused by its signature.
- Limits: 20 uploads an hour (the `upload` route limit) and a daily byte budget per user
  (`ratelimit.upload_bytes_per_day`, 500 MB). The request's size is reserved before the body is
  read and settled to the stored size afterwards; over budget is 429 with `Retry-After` until
  midnight in Dhaka. Redis down → 503 (fails closed, D175).
- The uploader or the lead deletes (soft). A deleted file is never listed or served again, but
  its bytes stay for Phase 12 (the orphan cleanup skips project files).
- The list shows which tasks use the file as evidence (no link columns on `files`).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime, time, timedelta

from redis.exceptions import RedisError
from sqlalchemy import select, update

from app.algorithms.weeks import DHAKA
from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.core.ratelimit import RateLimited, RateLimitUnavailable, hash_key
from app.core.redis import get_redis
from app.core.settings_cache import active_settings
from app.models.profiles import FileKind, StoredFile
from app.models.projects import Milestone, ProjectStatus
from app.models.workspace import Task, TaskEvidence
from app.schemas.common import Page
from app.schemas.project_files import ProjectFile, ProjectFileLink
from app.schemas.tasks import PersonRef
from app.services import workspace as wsp
from app.services.context import Ctx
from app.services.files import store_upload
from app.uploads.storage import Readable

log = get_logger(__name__)

# Under `rl:` so it lives with the other limits (and the test reset clears it).
BUDGET_PREFIX = "rl:upload_bytes"
BUDGET_TTL_SECONDS = 26 * 3600  # a Dhaka day plus slack; the key names its date anyway

# Reserve `amount` bytes unless that takes the day's total over the budget (atomic).
_RESERVE_LUA = """
local used = redis.call('INCRBY', KEYS[1], ARGV[1])
if redis.call('TTL', KEYS[1]) < 0 then redis.call('EXPIRE', KEYS[1], ARGV[3]) end
if used > tonumber(ARGV[2]) then
  redis.call('DECRBY', KEYS[1], ARGV[1])
  return 0
end
return 1
"""


def budget_key(user_id: uuid.UUID, now: datetime) -> str:
    """One counter per user and Dhaka calendar day (the user id is hashed, as for limits)."""
    day = now.astimezone(DHAKA).date()
    return f"{BUDGET_PREFIX}:{hash_key(str(user_id))}:{day.isoformat()}"


def seconds_to_dhaka_midnight(now: datetime) -> int:
    """Whole seconds until the next midnight in Dhaka (at least 1)."""
    local = now.astimezone(DHAKA)
    midnight = datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=DHAKA)
    return max(1, int((midnight - local).total_seconds()))


def reservation(content_length: int | None, max_upload_bytes: int) -> int:
    """Bytes to reserve before reading the body: the declared size, capped at the largest
    upload; without a usable Content-Length, the largest upload (never zero)."""
    if content_length is None or content_length <= 0:
        return max_upload_bytes
    return min(content_length, max_upload_bytes)


async def _reserve(key: str, amount: int, budget: int, now: datetime) -> None:
    redis = get_redis()
    try:
        script = redis.register_script(_RESERVE_LUA)
        ok = await script(keys=[key], args=[amount, budget, BUDGET_TTL_SECONDS])
    except RedisError as exc:
        log.error("upload_budget_unavailable", error=type(exc).__name__)
        raise RateLimitUnavailable from exc
    if not int(ok):
        retry = seconds_to_dhaka_midnight(now)
        log.warning("upload_budget_exceeded", retry_after=retry)
        raise RateLimited(retry)


async def _settle(key: str, delta: int) -> None:
    """Give back what wasn't used (or all of it after a failure). If Redis is gone now, the
    budget stays over-counted for the day, which errs on the safe side."""
    if delta == 0:
        return
    try:
        await get_redis().incrby(key, delta)
    except RedisError as exc:
        log.warning("upload_budget_settle_failed", error=type(exc).__name__)


def _out(
    f: StoredFile,
    names: dict[uuid.UUID, str],
    links: dict[uuid.UUID, list[ProjectFileLink]],
    ws: wsp.Workspace,
    uid: uuid.UUID,
) -> ProjectFile:
    return ProjectFile(
        id=f.id,
        name=f.original_name,
        mime=f.mime_type,
        size_bytes=f.size_bytes,
        uploaded_by=PersonRef(id=f.owner_id, name=names.get(f.owner_id, "Former member")),
        created_at=f.created_at,
        can_delete=_may_delete(ws, f, uid),
        links=links.get(f.id, []),
    )


def _may_delete(ws: wsp.Workspace, f: StoredFile, uid: uuid.UUID) -> bool:
    open_ = ws.project.status == ProjectStatus.IN_PROGRESS
    return open_ and ws.role != wsp.WorkspaceRole.ADMIN and (f.owner_id == uid or ws.is_lead)


async def _links(ctx: Ctx, file_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ProjectFileLink]]:
    """Tasks that use each file as evidence, with their milestone (one entry per task)."""
    if not file_ids:
        return {}
    rows = await ctx.db.execute(
        select(TaskEvidence.file_id, Task.id, Task.title, Milestone.name)
        .join(Task, Task.id == TaskEvidence.task_id)
        .join(Milestone, Milestone.id == Task.milestone_id)
        .where(TaskEvidence.file_id.in_(file_ids))
        .order_by(TaskEvidence.file_id, Task.title, Task.id)
        .distinct()
    )
    out: dict[uuid.UUID, list[ProjectFileLink]] = {}
    for file_id, task_id, title, milestone in rows.tuples().all():
        if file_id is not None:
            out.setdefault(file_id, []).append(
                ProjectFileLink(task_id=task_id, task_title=title, milestone_title=milestone)
            )
    return out


def _cursor(f: StoredFile) -> str:
    raw = json.dumps([f.created_at.isoformat(), str(f.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, fid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(at), uuid.UUID(str(fid))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DomainError(
            "That page link is invalid.", code=ErrorCode.BAD_REQUEST, fields={"cursor": "Invalid"}
        ) from exc


async def upload(
    ctx: Ctx,
    project_id: uuid.UUID,
    source: Readable,
    filename: str | None,
    *,
    content_length: int | None,
) -> ProjectFile:
    """Store a file in the project's Files (participants, while the project is in progress)."""
    ws = await wsp.load(ctx, project_id, write=True, admin_read=False)
    budget = (await active_settings(ctx.db)).ratelimit.upload_bytes_per_day
    key = budget_key(ctx.uid, ctx.now)
    reserved = reservation(content_length, ctx.settings.MAX_UPLOAD_MB * 1024 * 1024)
    await _reserve(key, reserved, budget, ctx.now)
    try:
        stored = await store_upload(
            ctx, source, FileKind.PROJECT_FILE, filename, project_id=ws.project.id
        )
        await ctx.db.refresh(stored)  # created_at comes from the server
        await write_audit(
            ctx.db,
            action="project_file.upload",
            entity_type="file",
            entity_id=stored.id,
            actor_id=ctx.uid,
            actor_role=ctx.principal.role,
            after={
                "project_id": str(ws.project.id),
                "mime": stored.mime_type,
                "size_bytes": stored.size_bytes,
            },
        )
        await ctx.db.commit()
    except BaseException:
        await _settle(key, -reserved)
        raise
    await _settle(key, stored.size_bytes - reserved)
    names = await wsp.people(ws)
    return _out(stored, names, {}, ws, ctx.uid)


async def list_files(
    ctx: Ctx, project_id: uuid.UUID, *, cursor: str | None, limit: int
) -> Page[ProjectFile]:
    """Newest first; deleted files are never listed."""
    ws = await wsp.load(ctx, project_id, admin_read=False)
    stmt = (
        select(StoredFile)
        .where(
            StoredFile.project_id == ws.project.id,
            StoredFile.kind == FileKind.PROJECT_FILE,
            StoredFile.deleted_at.is_(None),
        )
        .order_by(StoredFile.created_at.desc(), StoredFile.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        at, fid = _decode(cursor)
        stmt = stmt.where(
            (StoredFile.created_at < at) | ((StoredFile.created_at == at) & (StoredFile.id < fid))
        )
    rows = list((await ctx.db.scalars(stmt)).all())
    more = len(rows) > limit
    rows = rows[:limit]
    links = await _links(ctx, [f.id for f in rows])
    names = await wsp.people(ws)
    return Page[ProjectFile](
        items=[_out(f, names, links, ws, ctx.uid) for f in rows],
        next_cursor=_cursor(rows[-1]) if more and rows else None,
    )


async def delete_file(ctx: Ctx, file_id: uuid.UUID) -> None:
    """Soft delete by the uploader or the lead. Anything that isn't a project file the caller
    can see is 404; another member's file is 403."""
    found = await ctx.db.scalar(
        select(StoredFile).where(
            StoredFile.id == file_id,
            StoredFile.kind == FileKind.PROJECT_FILE,
            StoredFile.deleted_at.is_(None),
        )
    )
    if found is None or found.project_id is None:
        raise NotFoundError
    ws = await wsp.load(ctx, found.project_id, write=True, admin_read=False)
    if not (found.owner_id == ctx.uid or ws.is_lead):
        raise ForbiddenError("Only the person who uploaded a file or the team lead can delete it.")
    # No RETURNING: it would check the *new* row against the SELECT policies, which hide
    # deleted files from everyone but their owner, so a lead's delete would be refused.
    result = await ctx.db.execute(
        update(StoredFile)
        .where(StoredFile.id == found.id, StoredFile.deleted_at.is_(None))
        .values(deleted_at=ctx.now)
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:  # deleted by someone else a moment ago
        raise NotFoundError
    await write_audit(
        ctx.db,
        action="project_file.delete",
        entity_type="file",
        entity_id=found.id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        before={"project_id": str(ws.project.id), "name": found.original_name},
    )
    await ctx.db.commit()
