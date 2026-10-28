"""Project planning: draft CRUD, plan editing, CPM preview and lifecycle transitions.

Every function acts for the signed-in client under row-level security (migration 0005); another
client's project simply isn't found (→ 404). Plan structure is validated with the pure CPM
algorithm (`app.algorithms.cpm`, §9.10): a dependency cycle is a 422 carrying the cycle. State
changes follow the spec §8 machine (DRAFT → BIDDING on publish, BIDDING → BIDDING on extend, and
→ CANCELLED before work starts); an illegal transition is a 409 `INVALID_STATE`. Writes are
audited and committed at the end. Money is integer paisa.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.cpm import (
    CpmCycleError,
    CpmResult,
    CpmValidationError,
    MilestoneInput,
    compute_cpm,
)
from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, InvalidStateTransition, NotFoundError
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.locks import advisory_xact_lock
from app.db.session import open_session
from app.models.foundation import PlatformSettings
from app.models.identity import User
from app.models.projects import (
    Milestone,
    MilestoneDependency,
    MilestoneSkill,
    MilestoneStatus,
    PlanBaseline,
    Project,
    ProjectSlot,
    ProjectStatus,
)
from app.repositories import projects as repo
from app.repositories.bids import active_bidder_ids
from app.repositories.profiles import existing_skill_ids
from app.schemas.common import Page
from app.schemas.projects import (
    CpmNodeOut,
    CpmPreviewOut,
    DependenciesReplace,
    DependencyOut,
    DraftOut,
    MilestoneOut,
    MilestonesReplace,
    PlanEdge,
    PlanOut,
    PlanPreviewIn,
    ProjectCreate,
    ProjectListItem,
    ProjectOut,
    ProjectUpdate,
    SlotOut,
    SlotsReplace,
)
from app.services import bids as bids_svc
from app.services import role_assessments
from app.services.context import Ctx
from app.services.notifications import notify_users

EDITABLE = ProjectStatus.DRAFT
CANCELLABLE = {
    ProjectStatus.DRAFT,
    ProjectStatus.BIDDING,
    ProjectStatus.FORMING,
    ProjectStatus.TEAM_PENDING,
}
# Abuse control (§14.8 "maximum active projects per client (20)"): published and not yet
# finished. Drafts don't count (they are bounded by the 10/day create limit). No §6.2 setting
# names it, so it is a constant (DECISIONS).
MAX_ACTIVE_PROJECTS = 20
ACTIVE_STATUSES = (
    ProjectStatus.BIDDING,
    ProjectStatus.FORMING,
    ProjectStatus.TEAM_PENDING,
    ProjectStatus.IN_PROGRESS,
    ProjectStatus.ON_HOLD,
    ProjectStatus.REVIEW_WINDOW,
)


# --------------------------------------------------------------------------- helpers


async def _audit(
    ctx: Ctx, action: str, entity_id: uuid.UUID, after: dict[str, Any] | None = None
) -> None:
    await write_audit(
        ctx.db,
        action=action,
        entity_type="project",
        entity_id=entity_id,
        actor_id=ctx.uid,
        actor_role=ctx.principal.role,
        after=after,
    )


async def _load_for_read(ctx: Ctx, project_id: uuid.UUID) -> Project:
    """A project the caller owns (or any for an admin); otherwise 404 (existence hidden)."""
    project = await repo.get_project(ctx.db, project_id)
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    return project


async def _load_for_write(ctx: Ctx, project_id: uuid.UUID, if_match: int | None) -> Project:
    """A project the caller owns and may change (row locked); checks the version."""
    project = await repo.get_project(ctx.db, project_id, for_update=True)
    if project is None or project.client_id != ctx.uid:
        raise NotFoundError
    if if_match is not None and project.version != if_match:
        raise DomainError(
            "This project changed since you loaded it. Reload and try again.",
            code=ErrorCode.VERSION_CONFLICT,
        )
    return project


def _require_status(project: Project, allowed: set[ProjectStatus], action: str) -> None:
    if project.status not in allowed:
        raise InvalidStateTransition(
            current_state=project.status.value,
            allowed_actions=[s.value for s in allowed],
            message=f"Can't {action} a project that is {project.status.value.lower()}.",
        )


async def _validate_skill_ids(ctx: Ctx, ids: Sequence[uuid.UUID], field: str) -> None:
    unique = list(dict.fromkeys(ids))
    if not unique:
        return
    known = await existing_skill_ids(ctx.db, unique)
    missing = [str(i) for i in unique if i not in known]
    if missing:
        raise DomainError(
            "One or more skills are unknown.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={field: f"unknown skill(s): {', '.join(missing)}"},
        )


def _require_future_bidding_deadline(deadline: datetime | None, now: datetime) -> None:
    """A bidding close time must be ahead: one in the past would close bidding the moment the
    project is published (and the too-few-bids job could cancel it straight away)."""
    if deadline is not None and deadline <= now:
        raise DomainError(
            "Choose a bidding close time in the future.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"bidding_deadline": "must be in the future"},
        )


def _pct(basis_points: int) -> str:
    """9990 → "99.9%" (rounding to whole percent said "100%, must be 100%")."""
    return f"{basis_points / 100:g}%"


def _project_out(project: Project) -> ProjectOut:
    return ProjectOut.model_validate(project, from_attributes=True)


def _milestone_inputs(
    milestones: Sequence[Milestone], deps: Sequence[MilestoneDependency]
) -> list[MilestoneInput]:
    """Build pure-CPM inputs from stored milestones and their dependencies."""
    preds: dict[uuid.UUID, list[str]] = {m.id: [] for m in milestones}
    for d in deps:
        preds.setdefault(d.successor_id, []).append(str(d.predecessor_id))
    return [
        MilestoneInput(
            id=str(m.id),
            duration_days=m.duration_days,
            predecessors=tuple(preds.get(m.id, ())),
            name=m.name,
        )
        for m in milestones
    ]


def _cpm_nodes(
    result: CpmResult, names: dict[str, str], shares: dict[str, int] | None = None
) -> list[CpmNodeOut]:
    shares = shares or {}
    return [
        CpmNodeOut(
            key=key,
            name=names.get(key, ""),
            es=node.es,
            ef=node.ef,
            ls=node.ls,
            lf=node.lf,
            slack=node.slack,
            critical=node.critical,
            share_bp=shares.get(key),
        )
        for key, node in result.nodes.items()
    ]


def _cpm_to_json(result: CpmResult, names: dict[str, str]) -> dict[str, Any]:
    """Serialise a CPM result for storage in a plan baseline."""
    return {
        "duration": result.duration,
        "critical_paths": [list(path) for path in result.critical_paths],
        "nodes": {
            key: {
                "name": names.get(key, ""),
                "es": n.es,
                "ef": n.ef,
                "ls": n.ls,
                "lf": n.lf,
                "slack": n.slack,
                "critical": n.critical,
            }
            for key, n in result.nodes.items()
        },
    }


# --------------------------------------------------------------------------- draft CRUD


async def create_draft(ctx: Ctx, data: ProjectCreate) -> ProjectOut:
    """Create a DRAFT project owned by the caller."""
    _require_future_bidding_deadline(data.bidding_deadline, ctx.now)
    project = Project(
        client_id=ctx.uid,
        title=data.title,
        summary=data.summary,
        description=data.description,
        requirements=data.requirements,
        budget_paisa=data.budget_paisa,
        bonus_pool_paisa=data.bonus_pool_paisa,
        deadline_days=data.deadline_days,
        team_size=data.team_size,
        start_date=data.start_date,
        bidding_deadline=data.bidding_deadline,
        status=ProjectStatus.DRAFT,
    )
    ctx.db.add(project)
    await ctx.db.flush()
    await _audit(ctx, "project.created", project.id, {"title": project.title})
    await ctx.db.commit()
    await ctx.db.refresh(project)
    return _project_out(project)


async def get_project(ctx: Ctx, project_id: uuid.UUID) -> ProjectOut:
    return _project_out(await _load_for_read(ctx, project_id))


_LIST_CURSOR_KIND = "mine"


def _list_cursor(project: Project) -> str:
    raw = f"{_LIST_CURSOR_KIND}|{project.created_at.isoformat()}|{project.id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _bad_list_cursor() -> DomainError:
    return DomainError(
        "That page cursor is invalid.",
        code=ErrorCode.VALIDATION_ERROR,
        fields={"cursor": "invalid"},
    )


def _decode_list_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """(created_at, id) of the previous page's last project; anything else is a 422."""
    try:
        kind, at, pid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 2)
        created_at, project_id = datetime.fromisoformat(at), uuid.UUID(pid)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise _bad_list_cursor() from exc
    if kind != _LIST_CURSOR_KIND or created_at.tzinfo is None:
        raise _bad_list_cursor()
    return created_at, project_id


async def list_mine(
    ctx: Ctx, *, cursor: str | None = None, limit: int = 20
) -> Page[ProjectListItem]:
    """The client's projects, newest first, one cursor page at a time (§10.1)."""
    after = _decode_list_cursor(cursor) if cursor is not None else None
    rows = await repo.list_mine(ctx.db, ctx.uid, limit=limit + 1, after=after)
    page, more = rows[:limit], len(rows) > limit
    return Page[ProjectListItem](
        items=[ProjectListItem.model_validate(p, from_attributes=True) for p in page],
        next_cursor=_list_cursor(page[-1]) if more and page else None,
    )


async def update_draft(
    ctx: Ctx, project_id: uuid.UUID, data: ProjectUpdate, if_match: int | None
) -> ProjectOut:
    project = await _load_for_write(ctx, project_id, if_match)
    _require_status(project, {EDITABLE}, "edit")
    changes = data.model_dump(exclude_unset=True)
    if "bidding_deadline" in changes:
        _require_future_bidding_deadline(changes["bidding_deadline"], ctx.now)
    for field, value in changes.items():
        setattr(project, field, value)
    project.version += 1
    await _audit(ctx, "project.updated", project.id, {"fields": sorted(changes)})
    await ctx.db.commit()
    await ctx.db.refresh(project)
    return _project_out(project)


async def get_draft(ctx: Ctx, project_id: uuid.UUID) -> DraftOut:
    """The owner's draft with its slots, milestones and dependencies, so the wizard can resume
    where the client left off (D55). Other users (admins included) get 404; non-drafts 409."""
    project = await _load_for_write(ctx, project_id, None)
    _require_status(project, {EDITABLE}, "continue editing")
    return DraftOut(
        project=_project_out(project),
        slots=[
            SlotOut.model_validate(s, from_attributes=True)
            for s in await repo.load_slots(ctx.db, project_id)
        ],
        milestones=await _milestones_out(ctx.db, project_id),
        dependencies=[
            DependencyOut.model_validate(d, from_attributes=True)
            for d in await repo.load_dependencies(ctx.db, project_id)
        ],
    )


async def delete_draft(ctx: Ctx, project_id: uuid.UUID) -> None:
    project = await _load_for_write(ctx, project_id, None)
    _require_status(project, {EDITABLE}, "delete")
    await ctx.db.delete(project)
    await _audit(ctx, "project.deleted", project.id)
    await ctx.db.commit()


# --------------------------------------------------------------------------- plan editing


T = TypeVar("T")


@dataclass(frozen=True)
class Replaced(Generic[T]):  # noqa: UP046 - Generic[T] keeps Semgrep able to parse the module
    """A whole-set replace's result and the project's new version (sent back as `X-Version`,
    for the next `If-Match`)."""

    items: list[T]
    version: int


async def replace_slots(
    ctx: Ctx, project_id: uuid.UUID, data: SlotsReplace, if_match: int | None = None
) -> Replaced[SlotOut]:
    """Replace all slots; the team size auto-sums to the slot counts (wizard §13.5 step 3)."""
    project = await _load_for_write(ctx, project_id, if_match)
    _require_status(project, {EDITABLE}, "edit the slots of")
    await _validate_skill_ids(ctx, [s.skill_id for s in data.slots], "slots")
    total = sum(s.count for s in data.slots)
    if not (2 <= total <= 10):  # noqa: PLR2004 - team size bounds (§7.3)
        raise DomainError(
            "Slot counts must total a team size between 2 and 10.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"slots": f"counts total {total}; must be 2–10"},
        )
    await repo.delete_slots(ctx.db, project_id)
    for s in data.slots:
        ctx.db.add(
            ProjectSlot(project_id=project_id, skill_id=s.skill_id, label=s.label, count=s.count)
        )
    project.team_size = total
    project.version += 1
    await ctx.db.flush()
    await _audit(ctx, "project.slots_replaced", project_id, {"count": len(data.slots)})
    version = project.version
    await ctx.db.commit()
    slots = [
        SlotOut.model_validate(s, from_attributes=True)
        for s in await repo.load_slots(ctx.db, project_id)
    ]
    return Replaced(slots, version)


async def replace_milestones(
    ctx: Ctx, project_id: uuid.UUID, data: MilestonesReplace, if_match: int | None = None
) -> Replaced[MilestoneOut]:
    """Replace all milestones (and their skills); dependencies cascade away and must be re-set."""
    project = await _load_for_write(ctx, project_id, if_match)
    _require_status(project, {EDITABLE}, "edit the milestones of")
    all_skill_ids = [sid for m in data.milestones for sid in m.skill_ids]
    await _validate_skill_ids(ctx, all_skill_ids, "milestones")
    await repo.delete_milestones(ctx.db, project_id)  # cascades skills + dependencies
    for position, m in enumerate(data.milestones):
        milestone = Milestone(
            project_id=project_id,
            name=m.name,
            description=m.description,
            duration_days=m.duration_days,
            share_bp=m.share_bp,
            position=position,
            status=MilestoneStatus.PLANNED,
        )
        ctx.db.add(milestone)
        await ctx.db.flush()
        for sid in dict.fromkeys(m.skill_ids):
            ctx.db.add(MilestoneSkill(milestone_id=milestone.id, skill_id=sid))
    project.version += 1
    await ctx.db.flush()
    await _audit(ctx, "project.milestones_replaced", project_id, {"count": len(data.milestones)})
    version = project.version
    await ctx.db.commit()
    return Replaced(await _milestones_out(ctx.db, project_id), version)


async def replace_dependencies(
    ctx: Ctx, project_id: uuid.UUID, data: DependenciesReplace, if_match: int | None = None
) -> Replaced[CpmNodeOut]:
    """Replace all dependency edges; rejects a cycle (422 with the cycle) via CPM validation."""
    project = await _load_for_write(ctx, project_id, if_match)
    _require_status(project, {EDITABLE}, "edit the dependencies of")
    milestones = await repo.load_milestones(ctx.db, project_id)
    known = {m.id for m in milestones}
    for d in data.dependencies:
        if d.predecessor_id not in known or d.successor_id not in known:
            raise DomainError(
                "A dependency refers to a milestone that isn't in this project.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={
                    "dependencies": "predecessor and successor must be milestones of this project"
                },
            )
    await repo.delete_dependencies(ctx.db, project_id)
    for d in data.dependencies:
        ctx.db.add(
            MilestoneDependency(
                project_id=project_id,
                predecessor_id=d.predecessor_id,
                successor_id=d.successor_id,
            )
        )
    await ctx.db.flush()
    deps = await repo.load_dependencies(ctx.db, project_id)
    result = _compute_or_cycle(milestones, deps)
    project.version += 1
    await _audit(
        ctx, "project.dependencies_replaced", project_id, {"count": len(data.dependencies)}
    )
    version = project.version
    await ctx.db.commit()
    names = {str(m.id): m.name for m in milestones}
    return Replaced(_cpm_nodes(result, names, {str(m.id): m.share_bp for m in milestones}), version)


def _compute_or_cycle(
    milestones: Sequence[Milestone], deps: Sequence[MilestoneDependency]
) -> CpmResult:
    """Run CPM; turn a dependency cycle into a 422 naming the milestones in the cycle."""
    try:
        return compute_cpm(_milestone_inputs(milestones, deps))
    except CpmCycleError as exc:
        names = {str(m.id): m.name for m in milestones}
        cycle = " → ".join(names.get(mid, mid) for mid in exc.cycle)
        raise DomainError(
            f"The milestones form a dependency cycle: {cycle}.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"dependencies": f"cycle: {cycle}"},
        ) from exc


async def _milestones_out(db: AsyncSession, project_id: uuid.UUID) -> list[MilestoneOut]:
    milestones = await repo.load_milestones(db, project_id)
    skills = await repo.load_milestone_skills(db, [m.id for m in milestones])
    return [
        MilestoneOut(
            id=m.id,
            name=m.name,
            description=m.description,
            duration_days=m.duration_days,
            share_bp=m.share_bp,
            position=m.position,
            status=m.status.value,
            skill_ids=skills.get(m.id, []),
        )
        for m in milestones
    ]


# --------------------------------------------------------------------------- preview / plan


async def plan_preview(ctx: Ctx, project_id: uuid.UUID, data: PlanPreviewIn) -> CpmPreviewOut:
    """Run CPM on an unsaved plan and report the timeline, critical paths and warnings."""
    project = await _load_for_read(ctx, project_id)
    inputs = [
        MilestoneInput(
            id=m.key,
            duration_days=m.duration_days,
            predecessors=tuple(m.predecessor_keys),
            name=m.name,
        )
        for m in data.milestones
    ]
    names = {m.key: m.name for m in data.milestones}
    shares = {m.key: m.share_bp for m in data.milestones}
    total_share = sum(m.share_bp for m in data.milestones)
    pay = (await active_settings(ctx.db)).pay
    warnings: list[str] = []
    try:
        result = compute_cpm(inputs)
    except CpmCycleError as exc:
        cycle = [names.get(mid, mid) for mid in exc.cycle]
        return CpmPreviewOut(
            feasible=False,
            duration=0,
            nodes=[],
            critical_paths=[],
            cycle=cycle,
            total_share_bp=total_share,
            warnings=[f"Dependency cycle: {' → '.join(cycle)}."],
            platform_fee_bp=pay.platform_fee_bp,
            bonus_pool_bp=pay.bonus_pool_bp,
        )
    except CpmValidationError as exc:
        # Duplicate keys, a milestone after itself, an unknown predecessor: the request is
        # malformed (the wizard never sends these), so say so instead of a 500.
        raise DomainError(
            "This plan can't be scheduled as sent.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"milestones": str(exc)},
        ) from exc
    if data.milestones and total_share != 10_000:  # noqa: PLR2004 - 100% in basis points
        warnings.append(f"Milestone shares total {_pct(total_share)}, not 100%.")
    if result.duration > project.deadline_days:
        warnings.append(
            f"The plan needs {result.duration} days, over the {project.deadline_days}-day deadline."
        )
    if (
        data.slot_count is not None
        and data.team_size is not None
        and data.slot_count != data.team_size
    ):
        warnings.append("Slot counts don't total the team size yet.")
    return CpmPreviewOut(
        feasible=True,
        duration=result.duration,
        nodes=_cpm_nodes(result, names, shares),
        critical_paths=[[names.get(k, k) for k in path] for path in result.critical_paths],
        cycle=None,
        total_share_bp=total_share,
        warnings=warnings,
        platform_fee_bp=pay.platform_fee_bp,
        bonus_pool_bp=pay.bonus_pool_bp,
    )


async def get_plan(ctx: Ctx, project_id: uuid.UUID) -> PlanOut:
    """The project's current CPM schedule and critical paths (baseline once published)."""
    project = await _load_for_read(ctx, project_id)
    milestones = await repo.load_milestones(ctx.db, project_id)
    deps = await repo.load_dependencies(ctx.db, project_id)
    result = _compute_or_cycle(milestones, deps)
    names = {str(m.id): m.name for m in milestones}
    shares = {str(m.id): m.share_bp for m in milestones}
    baseline = await repo.latest_baseline(ctx.db, project_id)
    return PlanOut(
        baseline_version=baseline.version if baseline else None,
        duration=result.duration,
        nodes=_cpm_nodes(result, names, shares),
        # The dependency graph needs the edges too (spec §13.5 screen 22); keys match node keys.
        edges=[
            PlanEdge(predecessor=str(d.predecessor_id), successor=str(d.successor_id)) for d in deps
        ],
        critical_paths=[[names.get(k, k) for k in path] for path in result.critical_paths],
        deadline_days=project.deadline_days,
        exceeds_deadline=result.duration > project.deadline_days,
    )


# --------------------------------------------------------------------------- lifecycle


async def publish(
    ctx: Ctx, project_id: uuid.UUID, acknowledge_schedule_risk: bool, if_match: int | None
) -> ProjectOut:
    """Publish a DRAFT for bidding after the §8 guards; writes baseline v1 (DRAFT → BIDDING)."""
    project = await _load_for_write(ctx, project_id, if_match)
    _require_status(project, {EDITABLE}, "publish")
    # Count-then-publish under a per-client lock, so two publishes at once can't pass the cap.
    await advisory_xact_lock(ctx.db, ctx.uid)
    active = await ctx.db.scalar(
        select(func.count())
        .select_from(Project)
        .where(Project.client_id == ctx.uid, Project.status.in_(ACTIVE_STATUSES))
    )
    if int(active or 0) >= MAX_ACTIVE_PROJECTS:
        raise DomainError(
            f"You already have {MAX_ACTIVE_PROJECTS} active projects, the most allowed at once. "
            "Finish or cancel one before publishing another.",
            code=ErrorCode.LIMIT_REACHED,
            extra={"limit": MAX_ACTIVE_PROJECTS},
        )

    user = await ctx.db.get(User, ctx.uid)
    if user is None or user.payment_verified_at is None:
        raise DomainError(
            "Verify a payment method before publishing for bids.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"payment_method": "a verified payment method is required"},
        )

    if project.budget_paisa < 1:
        raise DomainError(
            "Set a budget before publishing.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"budget_paisa": "a budget is required"},
        )
    if project.bidding_deadline is not None and project.bidding_deadline <= ctx.now:
        raise DomainError(
            "The bidding close time has passed. Choose a new one before publishing.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"bidding_deadline": "must be in the future"},
        )
    slots = await repo.load_slots(ctx.db, project_id)
    if not slots:
        raise DomainError(
            "Add at least one skill slot before publishing.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"slots": "at least one slot is required"},
        )
    places = sum(s.count for s in slots)
    if places != project.team_size:
        raise DomainError(
            f"The skill slots add up to {places} people but the team size is "
            f"{project.team_size}. Make them match before publishing.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"slots": f"slot counts total {places}; team size is {project.team_size}"},
        )
    milestones = await repo.load_milestones(ctx.db, project_id)
    if not milestones:
        raise DomainError(
            "Add at least one milestone before publishing.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"milestones": "at least one milestone is required"},
        )
    total_share = sum(m.share_bp for m in milestones)
    if total_share != 10_000:  # noqa: PLR2004 - 100% in basis points
        raise DomainError(
            "Milestone shares must total 100% before publishing.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"milestones": f"shares total {_pct(total_share)}, must be 100%"},
        )
    deps = await repo.load_dependencies(ctx.db, project_id)
    result = _compute_or_cycle(milestones, deps)  # raises 422 on a cycle
    if result.duration > project.deadline_days and not acknowledge_schedule_risk:
        raise DomainError(
            f"The plan needs {result.duration} days, beyond the {project.deadline_days}-day "
            "deadline. Acknowledge the schedule risk to publish anyway.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"acknowledge_schedule_risk": "required because the plan exceeds the deadline"},
        )

    names = {str(m.id): m.name for m in milestones}
    baseline = PlanBaseline(
        project_id=project_id,
        version=1,
        cpm=_cpm_to_json(result, names),
        reason="Initial baseline at publish.",
        created_by=ctx.uid,
        approved_by_client=True,
    )
    ctx.db.add(baseline)
    await ctx.db.flush()
    project.current_baseline_id = baseline.id
    project.settings_version = (
        await ctx.db.execute(select(func.max(PlatformSettings.version)))
    ).scalar_one()
    if project.bidding_deadline is None:
        bidding = (await active_settings(ctx.db)).bidding
        project.bidding_deadline = ctx.now + timedelta(days=bidding.extend_days)
    project.status = ProjectStatus.BIDDING  # publish-guard trigger re-checks shares/slots
    project.version += 1
    await ctx.db.flush()
    # Each slot's role assessment blueprint is built now and frozen with the published project
    # (role assessment spec §4.4, Decision 2).
    await role_assessments.ensure_slot_assessments(ctx.db, project, await active_settings(ctx.db))
    await _audit(ctx, "project.published", project_id, {"duration": result.duration})
    await ctx.db.commit()
    await ctx.db.refresh(project)
    return _project_out(project)


async def extend_bidding(ctx: Ctx, project_id: uuid.UUID) -> ProjectOut:
    """Extend the bidding deadline, up to `bidding.max_extensions` times (spec §8)."""
    project = await _load_for_write(ctx, project_id, None)
    _require_status(project, {ProjectStatus.BIDDING}, "extend bidding for")
    bidding = (await active_settings(ctx.db)).bidding
    if project.bidding_extensions >= bidding.max_extensions:
        raise InvalidStateTransition(
            current_state=project.status.value,
            allowed_actions=["cancel"],
            message=f"Bidding has already been extended {bidding.max_extensions} times.",
        )
    # From the current deadline, or from now when it already passed (too few bids), so an
    # extension always gives bidders `extend_days` of real time.
    base = max(project.bidding_deadline or ctx.now, ctx.now)
    project.bidding_deadline = base + timedelta(days=bidding.extend_days)
    project.bidding_extensions += 1
    project.version += 1
    await _audit(ctx, "project.bidding_extended", project_id, {"n": project.bidding_extensions})
    await ctx.db.commit()
    await ctx.db.refresh(project)
    # Bidding is open again: bids filtered out at the last close become ACTIVE so their bidders
    # can improve them (§8 "re-evaluated"). Bids are SYSTEM-written for anyone but the bidder.
    async with open_session(DbContext.system(), job=True) as sysdb:
        reopened = await bids_svc.reopen_bids(sysdb, project_id)
        await sysdb.commit()
    if reopened:
        await notify_users(
            reopened,
            "BIDDING_REOPENED",
            title="Bidding reopened on a project you bid on",
            body=f"The client extended bidding for “{project.title}”. Your bid is open again "
            "and you can change it until the new close time.",
            link="/dev/bids",
            once=False,
        )
    return _project_out(project)


async def cancel(ctx: Ctx, project_id: uuid.UUID, reason: str) -> ProjectOut:
    """Cancel a project before work starts (free; no escrow yet in Phase 4)."""
    project = await repo.get_project(ctx.db, project_id, for_update=True)
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    _require_status(project, CANCELLABLE, "cancel")
    was_bidding = project.status in {ProjectStatus.BIDDING, ProjectStatus.FORMING}
    project.status = ProjectStatus.CANCELLED
    project.cancel_reason = reason
    project.cancelled_at = ctx.now
    project.version += 1
    await _audit(ctx, "project.cancelled", project_id, {"by": ctx.principal.role})
    await ctx.db.commit()
    await ctx.db.refresh(project)
    if was_bidding:
        await notify_users(
            await active_bidder_ids(ctx.db, project_id),
            "PROJECT_CANCELLED",
            title="A project you bid on was cancelled",
            body=f"“{project.title}” was cancelled by its client. Your bid is closed.",
            link="/dev/bids",
            once=False,  # each cancellation is its own event
        )
    return _project_out(project)


async def verify_payment_method(ctx: Ctx) -> None:
    """Mark the client's (simulated) payment method verified (D39); idempotent."""
    user = await ctx.db.get(User, ctx.uid)
    if user is None:
        raise NotFoundError
    if user.payment_verified_at is None:
        user.payment_verified_at = ctx.now
        await write_audit(
            ctx.db,
            action="payment_method.verified",
            entity_type="user",
            entity_id=ctx.uid,
            actor_id=ctx.uid,
            actor_role=ctx.principal.role,
        )
        await ctx.db.commit()
