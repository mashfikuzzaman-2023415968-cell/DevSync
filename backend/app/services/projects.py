"""Project planning: draft CRUD, plan editing, CPM preview and lifecycle transitions.

Every function acts for the signed-in client under row-level security (migration 0005); another
client's project simply isn't found (→ 404). Plan structure is validated with the pure CPM
algorithm (`app.algorithms.cpm`, §9.10): a dependency cycle is a 422 carrying the cycle. State
changes follow the spec §8 machine (DRAFT → BIDDING on publish, BIDDING → BIDDING on extend, and
→ CANCELLED before work starts); an illegal transition is a 409 `INVALID_STATE`. Writes are
audited and committed at the end. Money is integer paisa.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.cpm import (
    CpmCycleError,
    CpmResult,
    MilestoneInput,
    compute_cpm,
)
from app.core.audit import write_audit
from app.core.errors import DomainError, ErrorCode, InvalidStateTransition, NotFoundError
from app.core.settings_cache import active_settings
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
from app.repositories.profiles import existing_skill_ids
from app.schemas.projects import (
    CpmNodeOut,
    CpmPreviewOut,
    DependenciesReplace,
    MilestoneOut,
    MilestonesReplace,
    PlanOut,
    PlanPreviewIn,
    ProjectCreate,
    ProjectListItem,
    ProjectOut,
    ProjectUpdate,
    SlotOut,
    SlotsReplace,
)
from app.services.context import Ctx

EDITABLE = ProjectStatus.DRAFT
CANCELLABLE = {
    ProjectStatus.DRAFT,
    ProjectStatus.BIDDING,
    ProjectStatus.FORMING,
    ProjectStatus.TEAM_PENDING,
}


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
    """A project the caller owns and may change; checks the optimistic-concurrency version."""
    project = await repo.get_project(ctx.db, project_id)
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


def _cpm_nodes(result: CpmResult, names: dict[str, str]) -> list[CpmNodeOut]:
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


async def list_mine(ctx: Ctx) -> list[ProjectListItem]:
    projects = await repo.list_mine(ctx.db, ctx.uid)
    return [ProjectListItem.model_validate(p, from_attributes=True) for p in projects]


async def update_draft(
    ctx: Ctx, project_id: uuid.UUID, data: ProjectUpdate, if_match: int | None
) -> ProjectOut:
    project = await _load_for_write(ctx, project_id, if_match)
    _require_status(project, {EDITABLE}, "edit")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    project.version += 1
    await _audit(ctx, "project.updated", project.id, {"fields": sorted(changes)})
    await ctx.db.commit()
    await ctx.db.refresh(project)
    return _project_out(project)


async def delete_draft(ctx: Ctx, project_id: uuid.UUID) -> None:
    project = await _load_for_write(ctx, project_id, None)
    _require_status(project, {EDITABLE}, "delete")
    await ctx.db.delete(project)
    await _audit(ctx, "project.deleted", project.id)
    await ctx.db.commit()


# --------------------------------------------------------------------------- plan editing


async def replace_slots(ctx: Ctx, project_id: uuid.UUID, data: SlotsReplace) -> list[SlotOut]:
    """Replace all slots; the team size auto-sums to the slot counts (wizard §13.5 step 3)."""
    project = await _load_for_write(ctx, project_id, None)
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
    await ctx.db.commit()
    return [
        SlotOut.model_validate(s, from_attributes=True)
        for s in await repo.load_slots(ctx.db, project_id)
    ]


async def replace_milestones(
    ctx: Ctx, project_id: uuid.UUID, data: MilestonesReplace
) -> list[MilestoneOut]:
    """Replace all milestones (and their skills); dependencies cascade away and must be re-set."""
    project = await _load_for_write(ctx, project_id, None)
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
    await ctx.db.commit()
    return await _milestones_out(ctx.db, project_id)


async def replace_dependencies(
    ctx: Ctx, project_id: uuid.UUID, data: DependenciesReplace
) -> list[CpmNodeOut]:
    """Replace all dependency edges; rejects a cycle (422 with the cycle) via CPM validation."""
    project = await _load_for_write(ctx, project_id, None)
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
    await ctx.db.commit()
    names = {str(m.id): m.name for m in milestones}
    return _cpm_nodes(result, names)


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
    total_share = sum(m.share_bp for m in data.milestones)
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
        )
    if data.milestones and total_share != 10_000:  # noqa: PLR2004 - 100% in basis points
        warnings.append(f"Milestone shares total {total_share / 100:.0f}%, not 100%.")
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
        nodes=_cpm_nodes(result, names),
        critical_paths=[[names.get(k, k) for k in path] for path in result.critical_paths],
        cycle=None,
        total_share_bp=total_share,
        warnings=warnings,
    )


async def get_plan(ctx: Ctx, project_id: uuid.UUID) -> PlanOut:
    """The project's current CPM schedule and critical paths (baseline once published)."""
    project = await _load_for_read(ctx, project_id)
    milestones = await repo.load_milestones(ctx.db, project_id)
    deps = await repo.load_dependencies(ctx.db, project_id)
    result = _compute_or_cycle(milestones, deps)
    names = {str(m.id): m.name for m in milestones}
    baseline = await repo.latest_baseline(ctx.db, project_id)
    return PlanOut(
        baseline_version=baseline.version if baseline else None,
        duration=result.duration,
        nodes=_cpm_nodes(result, names),
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

    user = await ctx.db.get(User, ctx.uid)
    if user is None or user.payment_verified_at is None:
        raise DomainError(
            "Verify a payment method before publishing for bids.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"payment_method": "a verified payment method is required"},
        )

    slots = await repo.load_slots(ctx.db, project_id)
    if not slots:
        raise DomainError(
            "Add at least one skill slot before publishing.",
            code=ErrorCode.VALIDATION_ERROR,
            fields={"slots": "at least one slot is required"},
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
            fields={"milestones": f"shares total {total_share / 100:.0f}%, must be 100%"},
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
    base = project.bidding_deadline or ctx.now
    project.bidding_deadline = base + timedelta(days=bidding.extend_days)
    project.bidding_extensions += 1
    project.version += 1
    await _audit(ctx, "project.bidding_extended", project_id, {"n": project.bidding_extensions})
    await ctx.db.commit()
    await ctx.db.refresh(project)
    return _project_out(project)


async def cancel(ctx: Ctx, project_id: uuid.UUID, reason: str) -> ProjectOut:
    """Cancel a project before work starts (free; no escrow yet in Phase 4)."""
    project = await repo.get_project(ctx.db, project_id)
    if project is None or (project.client_id != ctx.uid and not ctx.principal.is_admin):
        raise NotFoundError
    _require_status(project, CANCELLABLE, "cancel")
    project.status = ProjectStatus.CANCELLED
    project.cancel_reason = reason
    project.cancelled_at = ctx.now
    project.version += 1
    await _audit(ctx, "project.cancelled", project_id, {"by": ctx.principal.role})
    await ctx.db.commit()
    await ctx.db.refresh(project)
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
