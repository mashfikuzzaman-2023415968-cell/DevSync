"""Discussion threads and posts (spec §7.5, §10.2 Discussion; D146).

The same rules as comments (`services/comments.py`), for one project-wide conversation space:
- Participants read and write (the client too); former members, other clients and outsiders get
  404; admins 403 until Phase 12's dispute context (D142). Writing needs the project
  IN_PROGRESS.
- A thread has a title (3–120) and starts with its first post. Posts are plain text ≤ 4000, with
  at most 10 mentions kept to participants and an optional reply to a post of the same thread.
  The newest activity floats a thread up (`last_post_at`, kept by the `thread_last_post`
  trigger).
- Every post records `comment.posted` with `entity_type` `DISCUSSION_POST`, and
  `comment.replied` under the reply rule, so §9.1.4's reply score sees both places people talk.
- Authors edit within 15 minutes (revisions kept by a trigger) and soft-delete; a deleted post
  keeps its place without its text.
- Threads and posts share the 60/hour `comment` limit with comments (route dependency, §14.8).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select

from app.core.errors import DomainError, ErrorCode, ForbiddenError, NotFoundError
from app.models.workspace import DiscussionPost, DiscussionThread
from app.schemas.comments import CommentOut, CommentPatch, PostCreate, ThreadCreate, ThreadOut
from app.schemas.common import Page
from app.schemas.tasks import PersonRef
from app.services import comments as conv
from app.services import monitoring
from app.services import workspace as wsp
from app.services.context import Ctx

TARGET = "DISCUSSION_POST"


def _encode(at: datetime, item_id: uuid.UUID) -> str:
    raw = json.dumps([at.isoformat(), str(item_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, item_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(at), uuid.UUID(str(item_id))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DomainError(
            "That page link is invalid.", code=ErrorCode.BAD_REQUEST, fields={"cursor": "Invalid"}
        ) from exc


def _link(ws: wsp.Workspace, thread_id: uuid.UUID) -> str:
    return f"/w/{ws.project.id}/discussion?thread={thread_id}"


def post_out(
    p: DiscussionPost, names: dict[uuid.UUID, str], uid: uuid.UUID, now: datetime
) -> CommentOut:
    deleted = p.deleted_at is not None
    return CommentOut(
        id=p.id,
        target_type=TARGET,
        target_id=p.thread_id,
        author=PersonRef(id=p.author_id, name=names.get(p.author_id, "Former member")),
        body="" if deleted else p.body,
        mentions=[]
        if deleted
        else [PersonRef(id=m, name=names.get(m, "Former member")) for m in p.mentions],
        reply_to_id=p.reply_to_id,
        created_at=p.created_at,
        edited=p.edited_at is not None,
        deleted=deleted,
        can_edit=p.author_id == uid and conv.editable(p.created_at, p.deleted_at, now),
        version=p.version,
    )


def _thread_out(t: DiscussionThread, names: dict[uuid.UUID, str], count: int) -> ThreadOut:
    return ThreadOut(
        id=t.id,
        title=t.title,
        created_by=PersonRef(id=t.created_by, name=names.get(t.created_by, "Former member")),
        created_at=t.created_at,
        last_post_at=t.last_post_at,
        post_count=count,
    )


async def _thread(ctx: Ctx, thread_id: uuid.UUID) -> DiscussionThread:
    """The thread if the caller can see it (RLS: participants only), else 404."""
    thread = await ctx.db.get(DiscussionThread, thread_id)
    if thread is None:
        raise NotFoundError
    return thread


# --------------------------------------------------------------------------- threads


async def list_threads(
    ctx: Ctx, project_id: uuid.UUID, *, cursor: str | None, limit: int
) -> Page[ThreadOut]:
    """Most recently active first, in a total order (last_post_at, id)."""
    ws = await wsp.load(ctx, project_id, admin_read=False)
    q = select(DiscussionThread).where(DiscussionThread.project_id == ws.project.id)
    if cursor is not None:
        at, tid = _decode(cursor)
        q = q.where(
            or_(
                DiscussionThread.last_post_at < at,
                and_(DiscussionThread.last_post_at == at, DiscussionThread.id < tid),
            )
        )
    order = (DiscussionThread.last_post_at.desc(), DiscussionThread.id.desc())
    rows = list(await ctx.db.scalars(q.order_by(*order).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    counts: dict[uuid.UUID, int] = {}
    if rows:
        found = await ctx.db.execute(
            select(DiscussionPost.thread_id, func.count())
            .where(
                DiscussionPost.thread_id.in_([t.id for t in rows]),
                DiscussionPost.deleted_at.is_(None),
            )
            .group_by(DiscussionPost.thread_id)
        )
        counts = dict(found.tuples().all())
    names = await wsp.people(ws)
    last = rows[-1] if rows else None
    return Page[ThreadOut](
        items=[_thread_out(t, names, counts.get(t.id, 0)) for t in rows],
        next_cursor=_encode(last.last_post_at, last.id) if more and last else None,
    )


async def create_thread(ctx: Ctx, project_id: uuid.UUID, body: ThreadCreate) -> ThreadOut:
    """A new thread with its first post (both written by the caller)."""
    ws = await wsp.load(ctx, project_id, write=True, admin_read=False)
    db = ctx.db
    mentions = conv.keep_participants(body.mention_ids, await conv.participants(ws))
    thread = DiscussionThread(
        project_id=ws.project.id,
        title=body.title,
        created_by=ctx.uid,
        last_post_at=ctx.now,
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    db.add(thread)
    await db.flush()
    post = DiscussionPost(
        project_id=ws.project.id,
        thread_id=thread.id,
        author_id=ctx.uid,
        body=body.body,
        mentions=mentions,
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    db.add(post)
    await db.flush()
    await conv.record_conversation(
        ctx,
        ws,
        item_id=post.id,
        target_type=TARGET,
        target_id=thread.id,
        mentions=mentions,
        replied=None,
    )
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    names = await wsp.people(ws)
    await conv.notify_mentions(ws, mentions, ctx.uid, names, link=_link(ws, thread.id))
    return _thread_out(thread, names, 1)


# --------------------------------------------------------------------------- posts


async def list_posts(
    ctx: Ctx, thread_id: uuid.UUID, *, cursor: str | None, limit: int
) -> Page[CommentOut]:
    """Oldest first (a conversation). Deleted posts keep their place without their text."""
    thread = await _thread(ctx, thread_id)
    ws = await wsp.load(ctx, thread.project_id, admin_read=False)
    q = select(DiscussionPost).where(DiscussionPost.thread_id == thread.id)
    if cursor is not None:
        at, pid = _decode(cursor)
        q = q.where(
            or_(
                DiscussionPost.created_at > at,
                and_(DiscussionPost.created_at == at, DiscussionPost.id > pid),
            )
        )
    order = (DiscussionPost.created_at, DiscussionPost.id)
    rows = list(await ctx.db.scalars(q.order_by(*order).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    names = await wsp.people(ws)
    last = rows[-1] if rows else None
    return Page[CommentOut](
        items=[post_out(p, names, ctx.uid, ctx.now) for p in rows],
        next_cursor=_encode(last.created_at, last.id) if more and last else None,
    )


async def create_post(ctx: Ctx, thread_id: uuid.UUID, body: PostCreate) -> CommentOut:
    thread = await _thread(ctx, thread_id)
    ws = await wsp.load(ctx, thread.project_id, write=True, admin_read=False)
    db = ctx.db
    mentions = conv.keep_participants(body.mention_ids, await conv.participants(ws))
    replied: DiscussionPost | None = None
    if body.reply_to_id is not None:
        replied = await db.get(DiscussionPost, body.reply_to_id)
        if replied is None or replied.thread_id != thread.id:
            raise DomainError(
                "Reply to a post in the same thread.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"reply_to_id": "Not a post in this thread"},
            )
    post = DiscussionPost(
        project_id=ws.project.id,
        thread_id=thread.id,
        author_id=ctx.uid,
        body=body.body,
        mentions=mentions,
        reply_to_id=body.reply_to_id,
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    db.add(post)
    await db.flush()
    await conv.record_conversation(
        ctx,
        ws,
        item_id=post.id,
        target_type=TARGET,
        target_id=thread.id,
        mentions=mentions,
        replied=replied,
    )
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    names = await wsp.people(ws)
    await conv.notify_mentions(ws, mentions, ctx.uid, names, link=_link(ws, thread.id))
    return post_out(post, names, ctx.uid, ctx.now)


async def _own_post(ctx: Ctx, post_id: uuid.UUID, if_match: int | None) -> DiscussionPost:
    db = ctx.db
    post = await db.scalar(
        select(DiscussionPost).where(DiscussionPost.id == post_id).with_for_update()
    )
    if post is None:
        raise NotFoundError
    await wsp.load(ctx, post.project_id, write=True, admin_read=False)
    if post.author_id != ctx.uid:
        raise ForbiddenError("Only the author can change a post.")
    if post.deleted_at is not None:
        raise NotFoundError
    if if_match is not None and if_match != post.version:
        raise DomainError(
            "This post changed since you loaded it. Reload and try again.",
            code=ErrorCode.VERSION_CONFLICT,
        )
    return post


async def edit_post(
    ctx: Ctx, post_id: uuid.UUID, body: CommentPatch, if_match: int | None
) -> CommentOut:
    post = await _own_post(ctx, post_id, if_match)
    if not conv.editable(post.created_at, post.deleted_at, ctx.now):
        raise DomainError(code=ErrorCode.EDIT_WINDOW_CLOSED)
    if body.body != post.body:
        post.body = body.body
        post.edited_at = ctx.now
        post.version += 1
        post.updated_at = ctx.now
    await ctx.db.commit()
    ws = await wsp.load(ctx, post.project_id, admin_read=False)
    return post_out(post, await wsp.people(ws), ctx.uid, ctx.now)


async def delete_post(ctx: Ctx, post_id: uuid.UUID, if_match: int | None) -> None:
    post = await _own_post(ctx, post_id, if_match)
    post.deleted_at = ctx.now
    post.version += 1
    post.updated_at = ctx.now
    await ctx.db.commit()
