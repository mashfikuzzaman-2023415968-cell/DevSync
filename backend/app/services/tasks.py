"""Tasks on the Kanban board (spec §7.5, §8 Task, §10.2 Tasks; DECISIONS D143, D144, D148,
D168, D172, D173).

- The lead creates, edits, deletes, assigns tasks and manages dependencies, in any unfinished
  milestone. The assignee or the lead moves a task (only the lead moves an unassigned one) and adds
  evidence. The client reads only (§1.6). Lead powers exist only in the lead's own project.
- Moves follow §8 one step at a time. A task leaves TODO only while its milestone is ACTIVE or
  CHANGES_REQUESTED; DONE needs every dependency DONE; a task can't leave DONE while a task that
  depends on it is DONE. `progress_pct` comes from the status (§9.10 weights).
- Positions are fractional keys chosen by the server from the neighbours the client names, under a
  per-milestone advisory lock; a column is re-keyed when a key grows too long (D144).
- Writes run in the caller's RLS session with `If-Match` (D172); every status move, creation,
  reassignment and deletion writes an audit entry, and moves record evidence events in the same
  transaction (D149). Notifications go out after commit through a SYSTEM session.
- Rows are locked project → milestone → task → dependents.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import positions as pos
from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, ForbiddenError, NotFoundError
from app.db.locks import advisory_xact_lock
from app.models.formation import MemberStatus, TeamMember
from app.models.profiles import FileKind, StoredFile
from app.models.projects import Milestone, MilestoneStatus, ProjectStatus
from app.models.workspace import (
    STATUS_PROGRESS,
    ActivityEvent,
    Comment,
    CommentTarget,
    EvidenceKind,
    Task,
    TaskDependency,
    TaskEvidence,
    TaskStatus,
)
from app.schemas.common import Page
from app.schemas.tasks import (
    MAX_DEPENDENCIES,
    MAX_EVIDENCE,
    MAX_TASKS_PER_PROJECT,
    DependencyCreate,
    EvidenceCreate,
    EvidenceOut,
    MoveOption,
    PersonRef,
    TaskCard,
    TaskCreate,
    TaskDependencyOut,
    TaskDetail,
    TaskMove,
    TaskPatch,
    TaskRef,
)
from app.services import activity, monitoring
from app.services import workspace as wsp
from app.services.context import Ctx
from app.services.notifications import notify_users

ORDER = (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.DONE)
RANK = {s: i for i, s in enumerate(ORDER)}
UNFINISHED = (
    MilestoneStatus.PLANNED,
    MilestoneStatus.FUNDED,
    MilestoneStatus.ACTIVE,
    MilestoneStatus.CHANGES_REQUESTED,
)
WORKING = (MilestoneStatus.ACTIVE, MilestoneStatus.CHANGES_REQUESTED)
# Milestones whose tasks no longer move (accepted work, or frozen by Phase 10/12 decisions).
FROZEN = (
    MilestoneStatus.APPROVED,
    MilestoneStatus.AUTO_APPROVED,
    MilestoneStatus.PAID,
    MilestoneStatus.REFUNDED,
)
STATUS_LABEL = {
    TaskStatus.TODO: "To do",
    TaskStatus.IN_PROGRESS: "In progress",
    TaskStatus.REVIEW: "Review",
    TaskStatus.DONE: "Done",
}
_LOCK_NS = uuid.UUID("6f1d3a52-9a0e-4f43-a9d4-0c2b9b7e5d10")


# --------------------------------------------------------------------------- helpers


async def _lock(db: AsyncSession, scope: str, entity_id: uuid.UUID) -> None:
    """A transaction lock for one kind of check-and-write on one entity."""
    await advisory_xact_lock(db, uuid.uuid5(_LOCK_NS, f"{scope}:{entity_id}"))


def _check_version(task: Task, if_match: int | None) -> None:
    if if_match is None:
        raise DomainError(
            "Send the task's version in If-Match.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"If-Match": "Required"},
        )
    if if_match != task.version:
        raise DomainError(
            "This task changed since you loaded it. Reload the board and try again.",
            code=ErrorCode.VERSION_CONFLICT,
        )


def _titles(tasks: Sequence[Task]) -> str:
    return ", ".join(f"“{t.title}”" for t in sorted(tasks, key=lambda t: (t.title, t.id)))


async def _task_for_update(db: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise NotFoundError
    return task


async def _visible_task(ctx: Ctx, task_id: uuid.UUID, *, write: bool) -> tuple[Task, wsp.Workspace]:
    """The task and the caller's workspace role; 404 for tasks of projects they're not in (RLS
    hides them, and `load` refuses former members)."""
    task = await ctx.db.get(Task, task_id)
    if task is None:
        raise NotFoundError
    ws = await wsp.load(ctx, task.project_id, write=write)
    return task, ws


async def _milestone(db: AsyncSession, ws: wsp.Workspace, milestone_id: uuid.UUID) -> Milestone:
    milestone = await db.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != ws.project.id:
        raise NotFoundError
    return milestone


async def _active_member(db: AsyncSession, ws: wsp.Workspace, user_id: uuid.UUID) -> None:
    found = await db.scalar(
        select(TeamMember.id).where(
            TeamMember.team_id == ws.team.id,
            TeamMember.developer_id == user_id,
            TeamMember.status == MemberStatus.ACTIVE,
        )
    )
    if found is None:
        raise DomainError(
            "Assign the task to an active member of this team.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"assignee_id": "Not an active member of this team"},
        )


def _check_deadline(ws: wsp.Workspace, deadline: date | None) -> None:
    start = ws.project.start_date
    if deadline is not None and start is not None and deadline < start:
        raise DomainError(
            "The deadline can't be before the project's start date.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"deadline": "Before the project's start date"},
        )


def _unfinished(milestone: Milestone) -> None:
    if milestone.status not in UNFINISHED:
        raise DomainError(code=ErrorCode.MILESTONE_FINISHED)


async def _column_keys(
    db: AsyncSession, milestone_id: uuid.UUID, status: TaskStatus, exclude: uuid.UUID | None
) -> list[Task]:
    q = select(Task).where(Task.milestone_id == milestone_id, Task.status == status)
    if exclude is not None:
        q = q.where(Task.id != exclude)
    return list(await db.scalars(q.order_by(Task.position, Task.id)))


async def _place(
    db: AsyncSession,
    milestone_id: uuid.UUID,
    status: TaskStatus,
    *,
    moving: uuid.UUID | None = None,
    after_id: uuid.UUID | None = None,
    before_id: uuid.UUID | None = None,
) -> str:
    """The key for a card placed between `after_id` (above) and `before_id` (below) in a column,
    under the milestone lock; re-keys the column when needed (D144). Neighbours outside the
    column are a 422."""
    column = await _column_keys(db, milestone_id, status, moving)
    ids = [t.id for t in column]
    for name, nid in (("after_id", after_id), ("before_id", before_id)):
        if nid is not None and nid not in ids:
            raise DomainError(
                "Drop the card between two cards of that column.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={name: "Not a card in the target column"},
            )
    if after_id is not None:
        index = ids.index(after_id) + 1
        if before_id is not None and ids.index(before_id) != index:
            raise DomainError(
                "The two cards aren't next to each other.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"before_id": "Not the card right below after_id"},
            )
    elif before_id is not None:
        index = ids.index(before_id)
    else:
        index = len(column)  # the end of the column
    above = column[index - 1].position if index > 0 else None
    below = column[index].position if index < len(column) else None
    try:
        key = pos.key_between(above, below)
    except pos.InvalidKeyError:
        key = None
    if key is None or pos.needs_rekey(key):
        keys = pos.spread(len(column) + 1)
        for task, new in zip(column, keys[:index] + keys[index + 1 :], strict=True):
            task.position = new
        await db.flush()
        key = keys[index]
    return key


def _cursor(task: Task) -> str:
    raw = json.dumps([task.status.value, task.position, str(task.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[TaskStatus, str, uuid.UUID]:
    try:
        status, position, tid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not pos.is_valid_key(str(position)):
            raise ValueError("bad position")
        return TaskStatus(status), str(position), uuid.UUID(str(tid))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DomainError(
            "That page link is invalid.", code=ErrorCode.BAD_REQUEST, fields={"cursor": "Invalid"}
        ) from exc


# --------------------------------------------------------------------------- reading


@dataclass(frozen=True)
class _Counts:
    blocked: dict[uuid.UUID, int]
    evidence: dict[uuid.UUID, int]
    comments: dict[uuid.UUID, int]


async def _counts(db: AsyncSession, ids: list[uuid.UUID]) -> _Counts:
    """Three grouped queries for a whole page (no N+1, §15.1)."""
    if not ids:
        return _Counts({}, {}, {})
    dep = Task.__table__.alias("dep")
    blocked = await db.execute(
        select(TaskDependency.task_id, func.count())
        .join(dep, dep.c.id == TaskDependency.depends_on_task_id)
        .where(TaskDependency.task_id.in_(ids), dep.c.status != TaskStatus.DONE)
        .group_by(TaskDependency.task_id)
    )
    evidence = await db.execute(
        select(TaskEvidence.task_id, func.count())
        .where(TaskEvidence.task_id.in_(ids))
        .group_by(TaskEvidence.task_id)
    )
    comments = await db.execute(
        select(Comment.target_id, func.count())
        .where(
            Comment.target_type == CommentTarget.TASK,
            Comment.target_id.in_(ids),
            Comment.deleted_at.is_(None),
        )
        .group_by(Comment.target_id)
    )
    return _Counts(
        dict(blocked.tuples().all()), dict(evidence.tuples().all()), dict(comments.tuples().all())
    )


def _person(names: dict[uuid.UUID, str], uid: uuid.UUID | None) -> PersonRef | None:
    if uid is None:
        return None
    return PersonRef(id=uid, name=names.get(uid, "Former member"))


def _card(task: Task, names: dict[uuid.UUID, str], counts: _Counts) -> TaskCard:
    return TaskCard(
        id=task.id,
        milestone_id=task.milestone_id,
        title=task.title,
        status=task.status,
        assignee=_person(names, task.assignee_id),
        deadline=task.deadline,
        estimate_hours=task.estimate_hours,
        difficulty=task.difficulty,
        position=task.position,
        progress_pct=task.progress_pct,
        blocked_by=counts.blocked.get(task.id, 0),
        evidence_count=counts.evidence.get(task.id, 0),
        comment_count=counts.comments.get(task.id, 0),
        last_activity_at=task.last_activity_at,
        version=task.version,
    )


async def list_tasks(
    ctx: Ctx,
    project_id: uuid.UUID,
    *,
    milestone_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    mine: bool = False,
    status: TaskStatus | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[TaskCard]:
    """The board's cards in a total order: column, position, id (D140)."""
    ws = await wsp.load(ctx, project_id)
    db = ctx.db
    # The task_status enum sorts in declaration order: TODO, IN_PROGRESS, REVIEW, DONE.
    q = select(Task).where(Task.project_id == ws.project.id)
    if milestone_id is not None:
        q = q.where(Task.milestone_id == milestone_id)
    if assignee_id is not None:
        q = q.where(Task.assignee_id == assignee_id)
    if mine:
        q = q.where(Task.assignee_id == ctx.uid)
    if status is not None:
        q = q.where(Task.status == status)
    q = q.order_by(Task.status, Task.position, Task.id)
    if cursor is not None:
        c_status, c_pos, c_id = _decode_cursor(cursor)
        q = q.where(
            tuple_(Task.status, Task.position, Task.id)
            > tuple_(literal(c_status, Task.status.type), literal(c_pos, Task.position.type), c_id)
        )
    rows = list(await db.scalars(q.limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    names = await wsp.people(ws)
    counts = await _counts(db, [t.id for t in rows])
    return Page[TaskCard](
        items=[_card(t, names, counts) for t in rows],
        next_cursor=_cursor(rows[-1]) if more and rows else None,
    )


async def list_milestone_tasks(
    ctx: Ctx,
    milestone_id: uuid.UUID,
    *,
    status: TaskStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[TaskCard]:
    """§10.2's `GET /milestones/{id}/tasks`: one milestone's cards (404 outside the project)."""
    milestone = await ctx.db.get(Milestone, milestone_id)
    if milestone is None:
        raise NotFoundError
    return await list_tasks(
        ctx,
        milestone.project_id,
        milestone_id=milestone_id,
        status=status,
        assignee_id=assignee_id,
        cursor=cursor,
        limit=limit,
    )


@dataclass(frozen=True)
class _Rules:
    """What a move is checked against: the milestone and the task's open neighbours."""

    milestone: Milestone
    deps_open: list[Task]  # tasks this one depends on that aren't DONE
    dependents_done: list[Task]  # DONE tasks that depend on this one


async def _rules(db: AsyncSession, ws: wsp.Workspace, task: Task) -> _Rules:
    milestone = await _milestone(db, ws, task.milestone_id)
    dependencies, dependents = await _deps(db, task.id)
    return _Rules(
        milestone,
        [t for t in dependencies if t.status != TaskStatus.DONE],
        [t for t in dependents if t.status == TaskStatus.DONE],
    )


def _move_options(task: Task, ws: wsp.Workspace, uid: uuid.UUID, rules: _Rules) -> list[MoveOption]:
    out: list[MoveOption] = []
    may_move = ws.is_lead or (ws.is_member and task.assignee_id == uid)
    for target in ORDER:
        if target == task.status:
            continue
        reason = _refusal(task, target, rules)
        if reason is None and not may_move:
            reason = (
                "Only the team lead moves unassigned tasks."
                if task.assignee_id is None
                else "Only the task's assignee or the team lead can move it."
            )
        out.append(MoveOption(status=target, allowed=reason is None, reason=reason))
    return out


def _refusal(task: Task, target: TaskStatus, rules: _Rules) -> str | None:
    """Why a move to `target` is refused (None if the rules allow it)."""
    step = RANK[target] - RANK[task.status]
    if abs(step) != 1:
        nxt = ORDER[RANK[task.status] + (1 if step > 0 else -1)]
        return f"Move it to {STATUS_LABEL[nxt]} first."
    if rules.milestone.status in FROZEN:
        return "This milestone is finished, so its tasks can't change."
    if task.status == TaskStatus.TODO and rules.milestone.status not in WORKING:
        return "Work on this milestone can start once it's active."
    if target == TaskStatus.DONE and rules.deps_open:
        return f"Finish {_titles(rules.deps_open)} first."
    if task.status == TaskStatus.DONE and rules.dependents_done:
        return f"{_titles(rules.dependents_done)} depends on it and is done."
    return None


async def _deps(db: AsyncSession, task_id: uuid.UUID) -> tuple[list[Task], list[Task]]:
    """(tasks this one depends on, tasks that depend on it), each in a total order."""
    dependencies = list(
        await db.scalars(
            select(Task)
            .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
            .where(TaskDependency.task_id == task_id)
            .order_by(Task.title, Task.id)
        )
    )
    dependents = list(
        await db.scalars(
            select(Task)
            .join(TaskDependency, TaskDependency.task_id == Task.id)
            .where(TaskDependency.depends_on_task_id == task_id)
            .order_by(Task.title, Task.id)
        )
    )
    return dependencies, dependents


async def get_task(ctx: Ctx, task_id: uuid.UUID) -> TaskDetail:
    task, ws = await _visible_task(ctx, task_id, write=False)
    return await _detail(ctx, task, ws)


async def _detail(ctx: Ctx, task: Task, ws: wsp.Workspace) -> TaskDetail:
    db = ctx.db
    milestone = await _milestone(db, ws, task.milestone_id)
    dependencies, dependents = await _deps(db, task.id)
    evidence = list(
        await db.execute(
            select(TaskEvidence, StoredFile.original_name)
            .outerjoin(StoredFile, StoredFile.id == TaskEvidence.file_id)
            .where(TaskEvidence.task_id == task.id)
            .order_by(TaskEvidence.created_at, TaskEvidence.id)
        )
    )
    names = await wsp.people(ws)
    counts = await _counts(db, [task.id])
    card = _card(task, names, counts)
    deps_open = [t for t in dependencies if t.status != TaskStatus.DONE]
    dependents_done = [t for t in dependents if t.status == TaskStatus.DONE]
    writable = ws.project.status == ProjectStatus.IN_PROGRESS
    return TaskDetail(
        **card.model_dump(),
        description=task.description,
        created_by=_person(names, task.created_by) or PersonRef(id=task.created_by, name=""),
        dependencies=[TaskRef(id=t.id, title=t.title, status=t.status) for t in dependencies],
        dependents=[TaskRef(id=t.id, title=t.title, status=t.status) for t in dependents],
        evidence=[
            EvidenceOut(
                id=e.id,
                kind=e.kind,
                url=e.url,
                file_id=e.file_id,
                file_name=file_name,
                note=e.note,
                added_by=_person(names, e.added_by) or PersonRef(id=e.added_by, name=""),
                created_at=e.created_at,
            )
            for e, file_name in evidence
        ],
        can_move_to=(
            _move_options(task, ws, ctx.uid, _Rules(milestone, deps_open, dependents_done))
            if writable and ws.is_member
            else []
        ),
        can_edit=writable and ws.is_lead,
    )


# --------------------------------------------------------------------------- writing


async def create_task(ctx: Ctx, milestone_id: uuid.UUID, body: TaskCreate) -> TaskDetail:
    milestone = await ctx.db.get(Milestone, milestone_id)
    if milestone is None:
        raise NotFoundError
    ws = await wsp.load(ctx, milestone.project_id, write=True)
    wsp.require_lead(ws, "create tasks")
    db = ctx.db
    await _lock(db, "tasks", ws.project.id)
    milestone = await _milestone(db, ws, milestone_id)
    _unfinished(milestone)
    if body.assignee_id is not None:
        await _active_member(db, ws, body.assignee_id)
    _check_deadline(ws, body.deadline)
    count = await db.scalar(select(func.count()).where(Task.project_id == ws.project.id))
    if (count or 0) >= MAX_TASKS_PER_PROJECT:
        raise DomainError(
            f"A project can have at most {MAX_TASKS_PER_PROJECT} tasks.",
            code=ErrorCode.LIMIT_REACHED,
            extra={"limit": MAX_TASKS_PER_PROJECT},
        )
    deps = await _same_milestone_tasks(db, milestone.id, body.depends_on_ids, "depends_on_ids")
    await _lock(db, "positions", milestone.id)
    position = await _place(db, milestone.id, TaskStatus.TODO)
    task = Task(
        project_id=ws.project.id,
        milestone_id=milestone.id,
        title=body.title,
        description=body.description,
        assignee_id=body.assignee_id,
        deadline=body.deadline,
        estimate_hours=body.estimate_hours,
        difficulty=body.difficulty,
        position=position,
        status=TaskStatus.TODO,
        progress_pct=0,
        created_by=ctx.uid,
        created_at=ctx.now,
        updated_at=ctx.now,
        last_activity_at=ctx.now,
    )
    db.add(task)
    await db.flush()
    for dep in deps:
        db.add(TaskDependency(project_id=ws.project.id, task_id=task.id, depends_on_task_id=dep.id))
    await write_audit(
        db,
        action="task.create",
        entity_type="task",
        entity_id=task.id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        after={
            "milestone_id": str(milestone.id),
            "title": task.title,
            "assignee_id": str(task.assignee_id) if task.assignee_id else None,
            "estimate_hours": str(task.estimate_hours),
        },
    )
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    await _after_change(ws, task, assigned_to=body.assignee_id, by=ctx.uid)
    return await _detail(ctx, task, ws)


async def _same_milestone_tasks(
    db: AsyncSession, milestone_id: uuid.UUID, ids: Sequence[uuid.UUID], field: str
) -> list[Task]:
    if not ids:
        return []
    found = list(await db.scalars(select(Task).where(Task.id.in_(ids))))
    if len(found) != len(set(ids)) or any(t.milestone_id != milestone_id for t in found):
        raise DomainError(
            "Dependencies must be tasks of the same milestone.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={field: "Only tasks of the same milestone"},
        )
    return found


async def move_task(ctx: Ctx, task_id: uuid.UUID, body: TaskMove, if_match: int | None) -> TaskCard:
    task, ws = await _visible_task(ctx, task_id, write=True)
    if ws.is_client:
        raise ForbiddenError("Clients watch progress; the team moves the tasks.")
    db = ctx.db
    await _lock(db, "positions", task.milestone_id)
    task = await _task_for_update(db, task_id)
    _check_version(task, if_match)
    if not (ws.is_lead or task.assignee_id == ctx.uid):
        raise ForbiddenError(
            "Only the team lead moves unassigned tasks."
            if task.assignee_id is None
            else "Only the task's assignee or the team lead can move it."
        )
    rules = await _rules(db, ws, task)
    before = task.status
    if rules.milestone.status in FROZEN:
        raise DomainError(code=ErrorCode.MILESTONE_FINISHED)
    if body.status != before:
        _raise_if_refused(task, body.status, rules)
    task.position = await _place(
        db,
        task.milestone_id,
        body.status,
        moving=task.id,
        after_id=body.after_id,
        before_id=body.before_id,
    )
    task.status = body.status
    task.progress_pct = STATUS_PROGRESS[body.status]
    task.version += 1
    task.updated_at = ctx.now
    task.last_activity_at = ctx.now
    await db.flush()
    if body.status != before:
        await _record_move(ctx, task, before)
        await write_audit(
            db,
            action="task.move",
            entity_type="task",
            entity_id=task.id,
            actor_id=ctx.uid,
            actor_role=ctx.principal.role,
            before={"status": before.value},
            after={"status": body.status.value},
        )
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    names = await wsp.people(ws)
    counts = await _counts(db, [task.id])
    return _card(task, names, counts)


def _raise_if_refused(task: Task, target: TaskStatus, rules: _Rules) -> None:
    reason = _refusal(task, target, rules)
    if reason is None:
        return
    deps_open, dependents_done = rules.deps_open, rules.dependents_done
    if abs(RANK[target] - RANK[task.status]) != 1:
        code = ErrorCode.ONE_STEP_ONLY
    elif rules.milestone.status in FROZEN:
        code = ErrorCode.MILESTONE_FINISHED
    elif task.status == TaskStatus.TODO and rules.milestone.status not in WORKING:
        code = ErrorCode.MILESTONE_NOT_ACTIVE
    elif target == TaskStatus.DONE and deps_open:
        raise DomainError(
            reason,
            code=ErrorCode.DEPENDENCIES_NOT_DONE,
            fields={"tasks": _titles(deps_open)},
            extra={"task_ids": [str(t.id) for t in deps_open]},
        )
    else:
        raise DomainError(
            reason,
            code=ErrorCode.DEPENDENTS_DONE,
            fields={"tasks": _titles(dependents_done)},
            extra={"task_ids": [str(t.id) for t in dependents_done]},
        )
    raise DomainError(reason, code=code)


async def _record_move(ctx: Ctx, task: Task, before: TaskStatus) -> None:
    """task.moved always; task.done / task.reopened at DONE; work.started for the assignee's
    first IN_PROGRESS on the project (D149). Credited to the assignee at that moment."""
    facts: dict[str, object] = {
        "task_id": task.id,
        "milestone_id": task.milestone_id,
        "assignee_id": task.assignee_id,
        "estimate_hours": task.estimate_hours,
    }
    subject = task.assignee_id

    async def emit(event_type: str, data: dict[str, object]) -> None:
        await activity.record(
            ctx.db,
            project_id=task.project_id,
            type=event_type,
            entity_type="TASK",
            entity_id=task.id,
            subject_id=subject,
            data=data,
            at=ctx.now,
        )

    await emit("task.moved", {**facts, "from_status": before, "to_status": task.status})
    if task.status == TaskStatus.DONE:
        await emit("task.done", facts)
    if before == TaskStatus.DONE:
        await emit("task.reopened", {**facts, "to_status": task.status})
    if task.status == TaskStatus.IN_PROGRESS and subject is not None:
        started = await ctx.db.scalar(
            select(ActivityEvent.id)
            .where(
                ActivityEvent.project_id == task.project_id,
                ActivityEvent.type == "work.started",
                ActivityEvent.subject_id == subject,
            )
            .limit(1)
        )
        if started is None:
            await emit("work.started", {"task_id": task.id, "milestone_id": task.milestone_id})


async def patch_task(
    ctx: Ctx, task_id: uuid.UUID, body: TaskPatch, if_match: int | None
) -> TaskDetail:
    task, ws = await _visible_task(ctx, task_id, write=True)
    wsp.require_lead(ws, "edit tasks")
    db = ctx.db
    task = await _task_for_update(db, task_id)
    _check_version(task, if_match)
    sent = body.model_fields_set
    before = {
        "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        "milestone_id": str(task.milestone_id),
    }
    if body.milestone_id is not None and body.milestone_id != task.milestone_id:
        await _change_milestone(ctx, ws, task, body.milestone_id)
    else:
        _unfinished(await _milestone(db, ws, task.milestone_id))
    if "assignee_id" in sent and body.assignee_id is not None:
        await _active_member(db, ws, body.assignee_id)
    if "deadline" in sent:
        _check_deadline(ws, body.deadline)
    newly_assigned = (
        body.assignee_id if "assignee_id" in sent and body.assignee_id != task.assignee_id else None
    )
    reassigned = "assignee_id" in sent and body.assignee_id != task.assignee_id
    for name in ("title", "description", "assignee_id", "deadline", "estimate_hours", "difficulty"):
        if name in sent:
            setattr(task, name, getattr(body, name))
    task.version += 1
    task.updated_at = ctx.now
    await db.flush()
    if reassigned or before["milestone_id"] != str(task.milestone_id):
        await write_audit(
            db,
            action="task.reassign" if reassigned else "task.update",
            entity_type="task",
            entity_id=task.id,
            actor_id=ctx.uid,
            actor_role=ctx.principal.role,
            before=before,
            after={
                "assignee_id": str(task.assignee_id) if task.assignee_id else None,
                "milestone_id": str(task.milestone_id),
            },
        )
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    await _after_change(ws, task, assigned_to=newly_assigned, by=ctx.uid)
    return await _detail(ctx, task, ws)


async def _change_milestone(
    ctx: Ctx, ws: wsp.Workspace, task: Task, milestone_id: uuid.UUID
) -> None:
    """Only a TODO task with no dependencies either way moves, to another unfinished milestone
    (dependencies never cross milestones, D143)."""
    db = ctx.db
    target = await _milestone(db, ws, milestone_id)
    _unfinished(target)
    _unfinished(await _milestone(db, ws, task.milestone_id))
    if task.status != TaskStatus.TODO:
        raise DomainError(
            "Only a task in To do can move to another milestone.", code=ErrorCode.INVALID_STATE
        )
    dependencies, dependents = await _deps(db, task.id)
    if dependencies or dependents:
        raise DomainError(
            f"Remove its dependencies first: {_titles([*dependencies, *dependents])}.",
            code=ErrorCode.DEPENDENCIES_BLOCK_MOVE,
            fields={"tasks": _titles([*dependencies, *dependents])},
        )
    await _lock(db, "positions", target.id)
    task.position = await _place(db, target.id, TaskStatus.TODO, moving=task.id)
    task.milestone_id = target.id


async def delete_task(ctx: Ctx, task_id: uuid.UUID, if_match: int | None) -> None:
    task, ws = await _visible_task(ctx, task_id, write=True)
    wsp.require_lead(ws, "delete tasks")
    db = ctx.db
    task = await _task_for_update(db, task_id)
    _check_version(task, if_match)
    if task.status == TaskStatus.DONE:
        raise DomainError("A finished task can't be deleted.", code=ErrorCode.INVALID_STATE)
    has_evidence = await db.scalar(
        select(TaskEvidence.id).where(TaskEvidence.task_id == task.id).limit(1)
    )
    if has_evidence is not None:  # evidence is kept, so its task stays (D173)
        raise DomainError(
            "This task has evidence attached, so it stays on the board.",
            code=ErrorCode.INVALID_STATE,
        )
    await write_audit(
        db,
        action="task.delete",
        entity_type="task",
        entity_id=task.id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        before={
            "title": task.title,
            "status": task.status.value,
            "milestone_id": str(task.milestone_id),
        },
    )
    await db.delete(task)  # its dependency rows go with it (FK cascade)
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    await _after_change(ws, None, assigned_to=None, by=ctx.uid)


async def add_dependency(ctx: Ctx, task_id: uuid.UUID, body: DependencyCreate) -> TaskDependencyOut:
    task, ws = await _visible_task(ctx, task_id, write=True)
    wsp.require_lead(ws, "change dependencies")
    db = ctx.db
    await _lock(db, "positions", task.milestone_id)  # dependency edits per milestone, serialised
    task = await _task_for_update(db, task_id)
    _unfinished(await _milestone(db, ws, task.milestone_id))
    (dep,) = await _same_milestone_tasks(
        db, task.milestone_id, [body.depends_on_task_id], "depends_on_task_id"
    )
    if dep.id == task.id:
        raise DomainError(
            "A task can't depend on itself.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"depends_on_task_id": "The task itself"},
        )
    rows = await db.execute(
        select(TaskDependency.task_id, TaskDependency.depends_on_task_id)
        .join(Task, Task.id == TaskDependency.task_id)
        .where(Task.milestone_id == task.milestone_id)
    )
    edges = [(a, b) for a, b in rows]
    if (task.id, dep.id) in edges:
        return TaskDependencyOut(task_id=task.id, depends_on_task_id=dep.id)
    if sum(1 for a, _ in edges if a == task.id) >= MAX_DEPENDENCIES:
        raise DomainError(
            f"A task can depend on at most {MAX_DEPENDENCIES} tasks.",
            code=ErrorCode.LIMIT_REACHED,
            extra={"limit": MAX_DEPENDENCIES},
        )
    cycle = _path(edges, dep.id, task.id)
    if cycle is not None:
        found = await db.execute(select(Task.id, Task.title).where(Task.id.in_(cycle)))
        # .all(): a Result has .keys(), so dict(result) would treat it as a mapping.
        titles = dict(found.tuples().all())
        names = " → ".join(f"“{titles[t]}”" for t in [task.id, *cycle])
        raise DomainError(
            f"That would make the tasks wait for each other: {names}.",
            code=ErrorCode.DEPENDENCY_CYCLE,
            fields={"cycle": names},
        )
    if task.status == TaskStatus.DONE and dep.status != TaskStatus.DONE:
        raise DomainError(
            f"“{task.title}” is done, so it can't wait for “{dep.title}”.",
            code=ErrorCode.DEPENDENCIES_NOT_DONE,
            fields={"tasks": f"“{dep.title}”"},
        )
    db.add(TaskDependency(project_id=ws.project.id, task_id=task.id, depends_on_task_id=dep.id))
    task.version += 1
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    return TaskDependencyOut(task_id=task.id, depends_on_task_id=dep.id)


def _path(
    edges: list[tuple[uuid.UUID, uuid.UUID]], start: uuid.UUID, goal: uuid.UUID
) -> list[uuid.UUID] | None:
    """The dependency path start → … → goal following "depends on" edges, if any (DFS in a
    fixed order, so the reported cycle is stable)."""
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for a, b in sorted(edges):
        out.setdefault(a, []).append(b)
    stack: list[tuple[uuid.UUID, list[uuid.UUID]]] = [(start, [start])]
    seen: set[uuid.UUID] = set()
    while stack:
        node, path = stack.pop()
        if node == goal:
            return path
        if node in seen:
            continue
        seen.add(node)
        for nxt in reversed(out.get(node, [])):
            stack.append((nxt, [*path, nxt]))
    return None


async def remove_dependency(ctx: Ctx, task_id: uuid.UUID, depends_on_task_id: uuid.UUID) -> None:
    task, ws = await _visible_task(ctx, task_id, write=True)
    wsp.require_lead(ws, "change dependencies")
    db = ctx.db
    task = await _task_for_update(db, task_id)
    _unfinished(await _milestone(db, ws, task.milestone_id))
    row = await db.scalar(
        select(TaskDependency).where(
            TaskDependency.task_id == task.id,
            TaskDependency.depends_on_task_id == depends_on_task_id,
        )
    )
    if row is None:
        raise NotFoundError
    await db.delete(row)
    task.version += 1
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)


async def add_evidence(ctx: Ctx, task_id: uuid.UUID, body: EvidenceCreate) -> EvidenceOut:
    task, ws = await _visible_task(ctx, task_id, write=True)
    if not (ws.is_lead or (ws.is_member and task.assignee_id == ctx.uid)):
        raise ForbiddenError("Only the task's assignee or the team lead can add evidence.")
    db = ctx.db
    task = await _task_for_update(db, task_id)
    count = await db.scalar(select(func.count()).where(TaskEvidence.task_id == task.id))
    if (count or 0) >= MAX_EVIDENCE:
        raise DomainError(
            f"A task can have at most {MAX_EVIDENCE} pieces of evidence.",
            code=ErrorCode.LIMIT_REACHED,
            extra={"limit": MAX_EVIDENCE},
        )
    file_name = None
    if body.file_id is not None:
        file = await db.get(StoredFile, body.file_id)
        image = file is not None and file.mime_type.startswith("image/")
        if (
            file is None
            or file.kind != FileKind.PROJECT_FILE
            or file.project_id != ws.project.id
            or file.deleted_at is not None
            or (body.kind == EvidenceKind.SCREENSHOT and not image)
        ):
            raise DomainError(
                "Attach a file uploaded to this project's Files"
                + (
                    " (an image for a screenshot)." if body.kind == EvidenceKind.SCREENSHOT else "."
                ),
                code=ErrorCode.VALIDATION_ERROR,
                fields={"file_id": "Not a usable file of this project"},
            )
        file_name = file.original_name
    evidence = TaskEvidence(
        project_id=ws.project.id,
        task_id=task.id,
        kind=body.kind,
        url=body.url,
        file_id=body.file_id,
        note=body.note,
        added_by=ctx.uid,
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    db.add(evidence)
    task.last_activity_at = ctx.now
    await db.flush()
    await activity.record(
        db,
        project_id=ws.project.id,
        type="task.evidence_added",
        entity_type="TASK",
        entity_id=task.id,
        subject_id=task.assignee_id,
        data={"task_id": task.id, "evidence_id": evidence.id, "kind": body.kind},
        at=ctx.now,
    )
    await db.commit()
    await monitoring.mark_dirty(ws.project.id, ctx.now)
    names = await wsp.people(ws)
    return EvidenceOut(
        id=evidence.id,
        kind=evidence.kind,
        url=evidence.url,
        file_id=evidence.file_id,
        file_name=file_name,
        note=evidence.note,
        added_by=_person(names, ctx.uid) or PersonRef(id=ctx.uid, name=""),
        created_at=evidence.created_at,
    )


async def _after_change(
    ws: wsp.Workspace, task: Task | None, *, assigned_to: uuid.UUID | None, by: uuid.UUID
) -> None:
    """After commit: tell a newly assigned member (§12 "Task assigned")."""
    if task is not None and assigned_to is not None and assigned_to != by:
        await notify_users(
            [assigned_to],
            "TASK_ASSIGNED",
            title=f"You were assigned “{task.title}”",
            body=f"In {ws.project.title}. Open the board to see the details.",
            link=f"/w/{ws.project.id}/tasks?task={task.id}",
            once=False,
        )


def touched(now: datetime, task: Task) -> None:
    """Comments and evidence count as activity on the task (STALLED_TASK reads it, D143)."""
    task.last_activity_at = now
