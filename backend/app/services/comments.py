"""Comments on tasks, milestones and check-ins (spec §7.5, §10.2, §12; D146, D149, D169).

- Anyone in the project comments (the client too); admins get 403 until Phase 12 (D142).
- Plain text only; the frontend renders it as text and links only `https://` URLs (§13.7).
- Mentions: the client sends user ids; the server keeps the project's participants and drops
  anyone else silently (§17 "mention of non-member ignored"); at most 10. Mentioned people are
  told (§12 "mentioned in comment"; email only if they opted in, D153).
- A reply names a comment on the same target. When that comment's author had mentioned the
  replier, the reply records `comment.replied` with the response time (§9.1.4 "reply score").
  The first reply to a check-in with blockers by another *member* records `blocker.answered`
  (§9.1.5 "help": the client and the author themselves don't count).
- The author edits within 15 minutes (revisions kept by a trigger, D169) and deletes (soft); a
  deleted comment's text is never shown again to participants.
- Comments and discussion posts share one 60/hour limit (route dependency, §14.8).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, or_, select

from app.core.errors import DomainError, ErrorCode, ForbiddenError, NotFoundError
from app.db.context import DbContext
from app.db.session import open_session
from app.models.formation import MemberStatus, TeamMember
from app.models.projects import Milestone
from app.models.workspace import (
    ActivityEvent,
    Checkin,
    Comment,
    CommentTarget,
    DiscussionPost,
    Task,
)
from app.schemas.comments import EDIT_WINDOW_SECONDS, CommentCreate, CommentOut, CommentPatch
from app.schemas.common import Page
from app.schemas.tasks import PersonRef
from app.services import activity, monitoring
from app.services import workspace as wsp
from app.services.context import Ctx
from app.services.notifications import EmailSpec, notify_users

READING_MEMBERS = (MemberStatus.ACTIVE, MemberStatus.COMPLETED)


async def _target_project(ctx: Ctx, target: CommentTarget, target_id: uuid.UUID) -> uuid.UUID:
    """The project a comment target belongs to; 404 if the caller can't see it (RLS)."""
    db = ctx.db
    project_id: uuid.UUID | None
    if target == CommentTarget.TASK:
        project_id = await db.scalar(select(Task.project_id).where(Task.id == target_id))
    elif target == CommentTarget.MILESTONE:
        project_id = await db.scalar(select(Milestone.project_id).where(Milestone.id == target_id))
    else:
        project_id = await db.scalar(select(Checkin.project_id).where(Checkin.id == target_id))
    if project_id is None:
        raise NotFoundError
    return project_id


async def participants(ws: wsp.Workspace) -> set[uuid.UUID]:
    """User ids who may be mentioned: the client and ACTIVE or COMPLETED members (read as
    SYSTEM after `load` admitted the caller; team rows are SYSTEM-written)."""
    async with open_session(DbContext.system(), job=True) as sdb:
        devs = await sdb.scalars(
            select(TeamMember.developer_id).where(
                TeamMember.team_id == ws.team.id, TeamMember.status.in_(READING_MEMBERS)
            )
        )
        return {ws.project.client_id, *devs}


def keep_participants(ids: Sequence[uuid.UUID], allowed: set[uuid.UUID]) -> list[uuid.UUID]:
    """The mentioned ids that are participants, in the order given, without repeats."""
    return [i for i in dict.fromkeys(ids) if i in allowed]


def _cursor(c: Comment) -> str:
    raw = json.dumps([c.created_at.isoformat(), str(c.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, cid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(at), uuid.UUID(str(cid))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DomainError(
            "That page link is invalid.", code=ErrorCode.BAD_REQUEST, fields={"cursor": "Invalid"}
        ) from exc


def editable(created_at: datetime, deleted_at: datetime | None, now: datetime) -> bool:
    return deleted_at is None and (now - created_at).total_seconds() <= EDIT_WINDOW_SECONDS


def out(c: Comment, names: dict[uuid.UUID, str], uid: uuid.UUID, now: datetime) -> CommentOut:
    deleted = c.deleted_at is not None
    return CommentOut(
        id=c.id,
        target_type=c.target_type.value,
        target_id=c.target_id,
        author=PersonRef(id=c.author_id, name=names.get(c.author_id, "Former member")),
        body="" if deleted else c.body,
        mentions=[]
        if deleted
        else [PersonRef(id=m, name=names.get(m, "Former member")) for m in c.mentions],
        reply_to_id=c.reply_to_id,
        created_at=c.created_at,
        edited=c.edited_at is not None,
        deleted=deleted,
        can_edit=c.author_id == uid and editable(c.created_at, c.deleted_at, now),
        version=c.version,
    )


async def list_comments(
    ctx: Ctx,
    target_type: CommentTarget,
    target_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[CommentOut]:
    """Oldest first (a conversation), in a total order (created_at, id)."""
    project_id = await _target_project(ctx, target_type, target_id)
    ws = await wsp.load(ctx, project_id, admin_read=False)
    q = select(Comment).where(Comment.target_type == target_type, Comment.target_id == target_id)
    if cursor is not None:
        at, cid = decode_cursor(cursor)
        q = q.where(or_(Comment.created_at > at, and_(Comment.created_at == at, Comment.id > cid)))
    rows = list(await ctx.db.scalars(q.order_by(Comment.created_at, Comment.id).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    names = await wsp.people(ws)
    return Page[CommentOut](
        items=[out(c, names, ctx.uid, ctx.now) for c in rows],
        next_cursor=_cursor(rows[-1]) if more and rows else None,
    )


async def create_comment(ctx: Ctx, body: CommentCreate) -> CommentOut:
    project_id = await _target_project(ctx, body.target_type, body.target_id)
    ws = await wsp.load(ctx, project_id, write=True)
    db = ctx.db
    allowed = await participants(ws)
    mentions = keep_participants(body.mention_ids, allowed)
    replied: Comment | None = None
    if body.reply_to_id is not None:
        replied = await db.get(Comment, body.reply_to_id)
        if (
            replied is None
            or replied.target_type != body.target_type
            or replied.target_id != body.target_id
        ):
            raise DomainError(
                "Reply to a comment in the same conversation.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"reply_to_id": "Not a comment here"},
            )
    comment = Comment(
        project_id=ws.project.id,
        target_type=body.target_type,
        target_id=body.target_id,
        author_id=ctx.uid,
        body=body.body,
        mentions=mentions,
        reply_to_id=body.reply_to_id,
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    db.add(comment)
    await db.flush()
    await record_conversation(
        ctx,
        ws,
        item_id=comment.id,
        target_type=body.target_type.value,
        target_id=body.target_id,
        mentions=mentions,
        replied=replied,
    )
    if body.target_type == CommentTarget.TASK and ws.is_member:
        await _touch_task(ctx, body.target_id)
    if body.target_type == CommentTarget.CHECKIN and ws.is_member:
        await _maybe_blocker_answered(ctx, ws, body.target_id, comment.id)
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    names = await wsp.people(ws)
    link = _link(ws, body.target_type, body.target_id)
    await notify_mentions(ws, mentions, ctx.uid, names, link=link)
    return out(comment, names, ctx.uid, ctx.now)


async def record_conversation(
    ctx: Ctx,
    ws: wsp.Workspace,
    *,
    item_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    mentions: list[uuid.UUID],
    replied: Comment | DiscussionPost | None,
) -> None:
    """`comment.posted`, and `comment.replied` when the replied-to author had mentioned the
    caller (§9.1.4) — shared by comments and discussion posts (D146)."""
    await activity.record(
        ctx.db,
        project_id=ws.project.id,
        type="comment.posted",
        entity_type="DISCUSSION_POST" if target_type == "DISCUSSION_POST" else "COMMENT",
        entity_id=item_id,
        subject_id=ctx.uid,
        data={
            "comment_id": item_id,
            "target_type": target_type,
            "target_id": target_id,
            "mentions": mentions,
        },
        at=ctx.now,
    )
    if replied is not None and replied.author_id != ctx.uid and ctx.uid in replied.mentions:
        await activity.record(
            ctx.db,
            project_id=ws.project.id,
            type="comment.replied",
            entity_type="DISCUSSION_POST" if target_type == "DISCUSSION_POST" else "COMMENT",
            entity_id=item_id,
            subject_id=ctx.uid,
            data={
                "comment_id": item_id,
                "reply_to_id": replied.id,
                "to_author_id": replied.author_id,
                "response_seconds": max(0, int((ctx.now - replied.created_at).total_seconds())),
            },
            at=ctx.now,
        )


async def _touch_task(ctx: Ctx, task_id: uuid.UUID) -> None:
    """A member's comment is activity on the task (STALLED_TASK reads it, D143)."""
    task = await ctx.db.get(Task, task_id)
    if task is not None:
        task.last_activity_at = ctx.now


async def _maybe_blocker_answered(
    ctx: Ctx, ws: wsp.Workspace, checkin_id: uuid.UUID, comment_id: uuid.UUID
) -> None:
    """The first reply by another member to a check-in with blockers (§9.1.5 "help")."""
    db = ctx.db
    checkin = await db.get(Checkin, checkin_id)
    if checkin is None or checkin.blockers is None:
        return
    author = await db.scalar(
        select(TeamMember.developer_id).where(TeamMember.id == checkin.team_member_id)
    )
    if author is None or author == ctx.uid:
        return
    answered = await db.scalar(
        select(ActivityEvent.id)
        .where(
            ActivityEvent.project_id == ws.project.id,
            ActivityEvent.type == "blocker.answered",
            ActivityEvent.entity_id == checkin_id,
        )
        .limit(1)
    )
    if answered is not None:
        return
    await activity.record(
        db,
        project_id=ws.project.id,
        type="blocker.answered",
        entity_type="CHECKIN",
        entity_id=checkin_id,
        subject_id=ctx.uid,
        data={"checkin_id": checkin_id, "comment_id": comment_id, "reporter_id": author},
        at=ctx.now,
    )


def _link(ws: wsp.Workspace, target: CommentTarget, target_id: uuid.UUID) -> str:
    if target == CommentTarget.TASK:
        return f"/w/{ws.project.id}/tasks?task={target_id}"
    if target == CommentTarget.CHECKIN:
        return f"/w/{ws.project.id}/check-ins?checkin={target_id}"
    return f"/w/{ws.project.id}/milestones?milestone={target_id}"


async def notify_mentions(
    ws: wsp.Workspace,
    mentions: Sequence[uuid.UUID],
    author: uuid.UUID,
    names: dict[uuid.UUID, str],
    *,
    link: str,
) -> None:
    """§12 "mentioned in comment" (in-app; email only when opted in, D153). No text quoted."""
    others = [m for m in mentions if m != author]
    if others:
        await notify_users(
            others,
            "MENTIONED",
            title=f"{names.get(author, 'Someone')} mentioned you",
            body=f"In {ws.project.title}. Open the conversation to reply.",
            link=link,
            once=False,
            email=EmailSpec(
                "mentioned",
                {"who": names.get(author, "Someone"), "project": ws.project.title},
            ),
        )


async def _own_comment(ctx: Ctx, comment_id: uuid.UUID, if_match: int | None) -> Comment:
    db = ctx.db
    comment = await db.scalar(select(Comment).where(Comment.id == comment_id).with_for_update())
    if comment is None:
        raise NotFoundError
    await wsp.load(ctx, comment.project_id, write=True)
    if comment.author_id != ctx.uid:
        raise ForbiddenError("Only the author can change a comment.")
    if comment.deleted_at is not None:
        raise NotFoundError
    if if_match is not None and if_match != comment.version:
        raise DomainError(
            "This comment changed since you loaded it. Reload and try again.",
            code=ErrorCode.VERSION_CONFLICT,
        )
    return comment


async def edit_comment(
    ctx: Ctx, comment_id: uuid.UUID, body: CommentPatch, if_match: int | None
) -> CommentOut:
    comment = await _own_comment(ctx, comment_id, if_match)
    if not editable(comment.created_at, comment.deleted_at, ctx.now):
        raise DomainError(code=ErrorCode.EDIT_WINDOW_CLOSED)
    if body.body != comment.body:
        comment.body = body.body
        comment.edited_at = ctx.now
        comment.version += 1
        comment.updated_at = ctx.now
    await ctx.db.commit()
    ws = await wsp.load(ctx, comment.project_id)
    return out(comment, await wsp.people(ws), ctx.uid, ctx.now)


async def delete_comment(ctx: Ctx, comment_id: uuid.UUID, if_match: int | None) -> None:
    comment = await _own_comment(ctx, comment_id, if_match)
    comment.deleted_at = ctx.now
    comment.version += 1
    comment.updated_at = ctx.now
    await ctx.db.commit()
