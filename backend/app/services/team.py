"""Team lifecycle: invitations, lead, start, leave, removal, cancel (spec §1.6, §8, §9.17, §10.2
Team; DECISIONS D118–D136).

Authorization is decided here (the caller is the project's client, a current member, the invitee,
the lead, or an admin); every write then happens in a SYSTEM session (D50; the team tables are
SYSTEM-write under RLS). Rows are locked in one order — project → team → members → invitations →
bids → reservations — and the state is re-checked inside the transaction, so accept, decline,
expiry, choosing a lead and choosing a replacement can race without a half-applied result.

What each action does is listed in its docstring; the rules are D118–D136.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms import availability as avail
from app.algorithms.lead import LeadCandidate, recommend_lead
from app.core.audit import write_audit
from app.core.authz import authorize
from app.core.clock import get_clock, to_display
from app.core.config import get_settings
from app.core.errors import DomainError, ErrorCode, InvalidStateTransition, NotFoundError
from app.core.logging import get_logger
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import AvailabilityReservation, Bid, BidStatus, ReservationStatus
from app.models.formation import (
    Invitation,
    InvitationResponse,
    LeadChangeRequest,
    LeadChangeStatus,
    MemberRemovalRequest,
    MemberStatus,
    RemovalBasis,
    RemovalStatus,
    RepairProposal,
    RepairStatus,
    Team,
    TeamMember,
    TeamStatus,
)
from app.models.identity import User, UserStatus
from app.models.profiles import Skill
from app.models.projects import (
    Milestone,
    MilestoneStatus,
    PlanBaseline,
    Project,
    ProjectSlot,
    ProjectStatus,
)
from app.models.workspace import ActivityEvent, Task, TaskStatus
from app.repositories import bids as bidrepo
from app.repositories import projects as projrepo
from app.schemas.platform_settings import PlatformSettingsValues
from app.schemas.team import (
    ActionOut,
    ChooseLeadIn,
    ClientTeamCard,
    DeclineIn,
    InvitationOut,
    LeadChangeRequestIn,
    LeadChangeRequestOut,
    LeadRecommendationOut,
    LeaveIn,
    MyInvitationOut,
    MyInvitationsOut,
    MyMembershipOut,
    RemovalRequestIn,
    RemovalRequestOut,
    RepairSummaryOut,
    TeamForClient,
    TeamForMember,
    TeamMemberForClient,
    TeamMemberForMember,
)
from app.services import activity, outbox, reputation_read
from app.services import repair as repair_svc
from app.services.context import Ctx
from app.services.notifications import notify

log = get_logger(__name__)

# Abuse caps with no §6.2 setting (D125, D132), like MAX_OPEN_BIDS.
MAX_PENDING_INVITATIONS = 10
MAX_LEAD_CHANGE_REQUESTS_PER_WEEK = 3
CURRENT = (MemberStatus.INVITED, MemberStatus.ACTIVE, MemberStatus.COMPLETED)
LIVE_PROJECT = (ProjectStatus.TEAM_PENDING, ProjectStatus.IN_PROGRESS)
OPEN_REPAIR = (RepairStatus.COMPUTING, RepairStatus.READY, RepairStatus.NO_CANDIDATES)
DONE_MILESTONE = (MilestoneStatus.APPROVED, MilestoneStatus.AUTO_APPROVED, MilestoneStatus.PAID)
RECENT_ANSWERS = timedelta(days=30)


# ------------------------------------------------------------------------------ helpers


def _system() -> Any:
    return open_session(DbContext.system(), job=True)


def _link_team(project_id: uuid.UUID) -> str:
    return f"/client/projects/{project_id}/team"


def _link_workspace(project_id: uuid.UUID) -> str:
    return f"/w/{project_id}/team"


def milestone_may_activate(milestone: Milestone, predecessors: set[uuid.UUID]) -> bool:
    """D118: at project start a milestone with no predecessors becomes ACTIVE. Phase 10 tightens
    this to also require the milestone to be FUNDED (escrow), as §8 says."""
    return not predecessors and milestone.status == MilestoneStatus.PLANNED


# What counts as a member being active in a project (D150): their check-ins, task events,
# comments and discussion posts — read from the evidence events, so nothing new is tracked.
ACTIVITY_SIGNALS = (
    "checkin.posted",
    "task.moved",
    "task.done",
    "task.reopened",
    "task.evidence_added",
    "work.started",
    "comment.posted",
    "comment.replied",
    "blocker.reported",
    "blocker.answered",
)


async def member_inactive_days(
    db: AsyncSession, member: TeamMember, now: datetime | None = None
) -> int | None:
    """Whole days since the member's last check-in, task event, comment or discussion post in
    the project; with none, since they became ACTIVE (D150, replacing D121's "no signal"). None
    only for a member who never became ACTIVE. INACTIVE_MEMBER and removal both use it."""
    at = now or get_clock().now()
    project_id = await db.scalar(select(Team.project_id).where(Team.id == member.team_id))
    last = await db.scalar(
        select(func.max(ActivityEvent.at)).where(
            ActivityEvent.project_id == project_id,
            ActivityEvent.actor_id == member.developer_id,
            ActivityEvent.type.in_(ACTIVITY_SIGNALS),
        )
    )
    since = last or member.joined_at
    if since is None:
        return None
    return max(0, (at - since).days)


async def _email(db: AsyncSession, user_id: uuid.UUID, template: str, **payload: str) -> None:
    user = await db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        return
    link = payload.pop("link", "/")
    await outbox.enqueue(
        db,
        to=str(user.email),
        template=template,
        payload={
            "name": user.display_name,
            "link": f"{get_settings().PUBLIC_ORIGIN}{link}",
            **payload,
        },
        user_id=user.id,
    )


async def _lock_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if project is None:
        raise NotFoundError
    return project


async def _team_of(db: AsyncSession, project_id: uuid.UUID, *, lock: bool = False) -> Team | None:
    stmt = select(Team).where(Team.project_id == project_id)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def _members(db: AsyncSession, team_id: uuid.UUID, *, lock: bool = False) -> list[TeamMember]:
    stmt = (
        select(TeamMember)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.created_at, TeamMember.id)
    )
    return list((await db.scalars(stmt.with_for_update() if lock else stmt)).all())


async def _invitations(
    db: AsyncSession, member_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Invitation]:
    if not member_ids:
        return {}
    rows = await db.scalars(select(Invitation).where(Invitation.team_member_id.in_(member_ids)))
    return {i.team_member_id: i for i in rows}


async def _reservation(
    db: AsyncSession, project_id: uuid.UUID, developer_id: uuid.UUID, *, lock: bool = False
) -> AvailabilityReservation | None:
    stmt = (
        select(AvailabilityReservation)
        .where(
            AvailabilityReservation.project_id == project_id,
            AvailabilityReservation.developer_id == developer_id,
            AvailabilityReservation.status != ReservationStatus.RELEASED,
        )
        .order_by(AvailabilityReservation.created_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt.with_for_update() if lock else stmt)


def invitation_state(inv: Invitation | None, now: datetime) -> str:
    if inv is None:
        return "CLOSED"
    if inv.response is not None:
        return inv.response.value
    if inv.sent_at is None:
        return "UNSENT"
    if inv.expires_at is not None and inv.expires_at <= now:
        return "EXPIRED"
    return "PENDING"


def _invitation_out(inv: Invitation | None, now: datetime) -> InvitationOut | None:
    if inv is None:
        return None
    return InvitationOut(
        id=inv.id,
        state=invitation_state(inv, now),
        sent_at=inv.sent_at,
        expires_at=inv.expires_at,
        responded_at=inv.responded_at,
        is_replacement=inv.is_replacement,
    )


async def free_hours(
    db: AsyncSession, developer_id: uuid.UUID, project_id: uuid.UUID, period: avail.Period
) -> tuple[int, int]:
    """(profile hours a week, hours already committed elsewhere over `period`): CONFIRMED
    reservations on other projects only; TENTATIVE ones never count (§9.17, D124)."""
    hours = (await bidrepo.profile_hours_by_developer(db, [developer_id])).get(developer_id, 20)
    rows = (await bidrepo.confirmed_reservations_by_developer(db, [developer_id])).get(
        developer_id, []
    )
    others = [
        avail.Reservation(avail.Period(r.from_date, r.to_date), r.hours_per_week)
        for r in rows
        if r.project_id != project_id
    ]
    return hours, avail.committed_hours(others, period)


async def pending_invitations(
    db: AsyncSession, developer_ids: Sequence[uuid.UUID], now: datetime
) -> dict[uuid.UUID, int]:
    """Sent, unanswered, unexpired invitations per developer (D125)."""
    if not developer_ids:
        return {}
    rows = await db.execute(
        select(TeamMember.developer_id, func.count())
        .join(Invitation, Invitation.team_member_id == TeamMember.id)
        .where(
            TeamMember.developer_id.in_(developer_ids),
            Invitation.sent_at.is_not(None),
            Invitation.responded_at.is_(None),
            Invitation.expires_at > now,
        )
        .group_by(TeamMember.developer_id)
    )
    return {dev: int(n) for dev, n in rows.tuples().all()}


def _period_of(res: AvailabilityReservation) -> avail.Period:
    return avail.Period(res.from_date, res.to_date)


def _today(now: datetime) -> date:
    return to_display(now).date()


# ------------------------------------------------------------------------ invitations


async def send_invitations(
    db: AsyncSession,
    project: Project,
    team: Team,
    now: datetime,
    settings: PlatformSettingsValues,
    *,
    member_ids: Sequence[uuid.UUID] | None = None,
) -> int:
    """Send every unsent invitation of the team (or of `member_ids`): the 48 h clock starts now
    (`invite.expiry_hours`), and the developer gets "You were selected" in-app and by email (D123).
    Idempotent: only rows with `sent_at IS NULL`."""
    stmt = (
        select(Invitation, TeamMember)
        .join(TeamMember, TeamMember.id == Invitation.team_member_id)
        .where(
            TeamMember.team_id == team.id,
            TeamMember.status == MemberStatus.INVITED,
            Invitation.sent_at.is_(None),
        )
        .with_for_update(of=Invitation)
    )
    if member_ids is not None:
        stmt = stmt.where(TeamMember.id.in_(member_ids))
    rows = (await db.execute(stmt)).tuples().all()
    expiry = timedelta(hours=settings.invite.expiry_hours)
    slots = {s.id: s for s in await projrepo.load_slots(db, project.id)}
    names = await _skill_names(db, [s.skill_id for s in slots.values()])
    for inv, member in rows:
        inv.sent_at = now
        inv.expires_at = now + expiry
        slot = slots.get(member.slot_id)
        role = (slot.label or names.get(slot.skill_id, "team")) if slot else "team"
        expires = f"{to_display(inv.expires_at):%d %b %Y, %H:%M}"
        if inv.is_replacement:
            title, template = "You were selected as a replacement", "invitation_replacement"
        else:
            title, template = "You were selected", "invitation_selected"
        await notify(
            db,
            member.developer_id,
            "INVITATION_SELECTED",
            title=title,
            body=f"The client chose you for the {role} role on “{project.title}”. Accept or "
            f"decline by {expires} (Asia/Dhaka).",
            link="/dev",
        )
        await _email(
            db,
            member.developer_id,
            template,
            project=project.title,
            role=role,
            expires=expires,
            link="/dev",
        )
    return len(rows)


async def _skill_names(db: AsyncSession, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict(
        (await db.execute(select(Skill.id, Skill.name).where(Skill.id.in_(ids)))).tuples().all()
    )


@dataclass
class _Answer:
    project: Project
    team: Team
    member: TeamMember
    invitation: Invitation
    bid: Bid
    reservation: AvailabilityReservation | None


async def _load_answer(db: AsyncSession, ctx: Ctx, invitation_id: uuid.UUID) -> _Answer:
    """The caller's own invitation with everything it touches, locked in the standard order."""
    found = (
        await db.execute(
            select(Invitation.id, TeamMember.developer_id, Team.project_id)
            .join(TeamMember, TeamMember.id == Invitation.team_member_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Invitation.id == invitation_id)
        )
    ).first()
    if found is None or found[1] != ctx.uid:
        raise NotFoundError
    project = await _lock_project(db, found[2])
    team = await _team_of(db, project.id, lock=True)
    inv = await db.scalar(
        select(Invitation).where(Invitation.id == invitation_id).with_for_update()
    )
    if team is None or inv is None:
        raise NotFoundError
    member = await db.scalar(
        select(TeamMember).where(TeamMember.id == inv.team_member_id).with_for_update()
    )
    if member is None:
        raise NotFoundError
    bid = await db.scalar(select(Bid).where(Bid.id == member.bid_id).with_for_update())
    if bid is None:
        raise NotFoundError
    res = await _reservation(db, project.id, member.developer_id, lock=True)
    return _Answer(project, team, member, inv, bid, res)


def _check_answerable(a: _Answer, now: datetime) -> None:
    inv = a.invitation
    if inv.sent_at is None:
        raise DomainError("This invitation hasn't been sent yet.", code=ErrorCode.INVALID_STATE)
    if inv.response is not None or a.member.status != MemberStatus.INVITED:
        raise InvalidStateTransition(
            inv.response.value if inv.response else a.member.status.value,
            [],
            "You already answered this invitation.",
        )
    if inv.expires_at is not None and inv.expires_at <= now:
        raise InvalidStateTransition("EXPIRED", [], "This invitation has expired.")
    if a.project.status not in LIVE_PROJECT or a.team.status not in (
        TeamStatus.PENDING,
        TeamStatus.ACTIVE,
    ):
        raise InvalidStateTransition(a.project.status.value, [], "This team is no longer forming.")


async def accept(ctx: Ctx, invitation_id: uuid.UUID) -> ActionOut:
    """Join the team (D124): member ACTIVE, bid ACCEPTED, reservation CONFIRMED — after
    re-checking free hours. A replacement joining an IN_PROGRESS project reserves from today to
    the planned finish."""
    authorize(ctx.principal, "invitation.respond")
    async with _system() as db:
        a = await _load_answer(db, ctx, invitation_id)
        _check_answerable(a, ctx.now)
        today = _today(ctx.now)
        res = a.reservation
        start = a.project.start_date or today
        until = start + timedelta(days=a.project.deadline_days)
        if a.project.status == ProjectStatus.IN_PROGRESS:
            start = max(start, today)
        period = avail.Period(start, max(until, start))
        hours, committed = await free_hours(db, ctx.uid, a.project.id, period)
        need = a.bid.hours_per_week_committed
        if committed + need > hours:
            free = max(0, hours - committed)
            raise DomainError(
                f"You have {free} free hours a week over this project's dates and it needs "
                f"{need}. Raise your weekly hours in your profile or leave another project, then "
                "accept before the invitation expires.",
                code=ErrorCode.UNAVAILABLE,
                extra={"free_hours": free, "needed_hours": need},
            )
        a.member.status = MemberStatus.ACTIVE
        a.member.joined_at = ctx.now
        a.invitation.response = InvitationResponse.ACCEPTED
        a.invitation.responded_at = ctx.now
        a.bid.status = BidStatus.ACCEPTED
        a.bid.version += 1
        if res is None:
            res = AvailabilityReservation(
                developer_id=ctx.uid,
                project_id=a.project.id,
                hours_per_week=need,
                from_date=start,
                to_date=until,
            )
            db.add(res)
        res.status = ReservationStatus.CONFIRMED
        res.from_date, res.to_date = period.from_, period.to
        if a.invitation.is_replacement:  # D149: the team was repaired
            activity.record_system(
                db,
                project_id=a.project.id,
                type="member.replaced",
                entity_type="TEAM_MEMBER",
                entity_id=a.member.id,
                actor_id=ctx.uid,
                subject_id=ctx.uid,
                data={
                    "member_id": a.member.id,
                    "slot_label": await _slot_label(db, a.member.slot_id),
                },
                at=ctx.now,
            )
        await notify(
            db,
            a.project.client_id,
            "INVITATION_ACCEPTED",
            title="Invitation accepted",
            body=f"A developer accepted their place on “{a.project.title}”.",
            link=_link_team(a.project.id),
        )
        await write_audit(
            db,
            action="invitation.accepted",
            entity_type="invitation",
            entity_id=a.invitation.id,
            actor_id=ctx.uid,
            actor_role="DEVELOPER",
        )
        await db.commit()
    return ActionOut(status="ACTIVE", message="You joined the team.")


async def decline(ctx: Ctx, invitation_id: uuid.UUID, body: DeclineIn) -> ActionOut:
    """Say no: member and bid DECLINED, reservation RELEASED, the client told, repair queued."""
    authorize(ctx.principal, "invitation.respond")
    settings = await active_settings(ctx.db)
    async with _system() as db:
        a = await _load_answer(db, ctx, invitation_id)
        _check_answerable(a, ctx.now)
        a.member.status = MemberStatus.DECLINED
        a.member.left_reason = body.reason
        a.invitation.response = InvitationResponse.DECLINED
        a.invitation.responded_at = ctx.now
        a.bid.status = BidStatus.DECLINED
        a.bid.version += 1
        if a.reservation is not None:
            a.reservation.status = ReservationStatus.RELEASED
        await notify(
            db,
            a.project.client_id,
            "INVITATION_DECLINED",
            title="Invitation declined",
            body=f"A developer declined their place on “{a.project.title}”. DevSync is "
            "looking for a replacement.",
            link=_link_team(a.project.id),
        )
        await write_audit(
            db,
            action="invitation.declined",
            entity_type="invitation",
            entity_id=a.invitation.id,
            actor_id=ctx.uid,
            actor_role="DEVELOPER",
        )
        proposal = await repair_svc.open_repair(
            db, a.project, a.team, a.member, now=ctx.now, settings=settings
        )
        await db.commit()
    repair_svc.queue(proposal)
    return ActionOut(status="DECLINED", message="You declined the invitation.")


async def expire_due(now: datetime) -> dict[str, int]:
    """`lifecycle.expire`: send unsent invitations of TEAM_PENDING teams (D123), then expire
    overdue ones — member, invitation and bid EXPIRED, reservation RELEASED, the client told,
    repair queued. One invitation per transaction, locked and re-checked (race-safe with accept)."""
    sent = expired = 0
    async with _system() as db:
        settings = await active_settings(db)
        pending_teams = (
            (
                await db.execute(
                    select(Team.id, Team.project_id)
                    .join(Project, Project.id == Team.project_id)
                    .join(TeamMember, TeamMember.team_id == Team.id)
                    .join(Invitation, Invitation.team_member_id == TeamMember.id)
                    .where(
                        Project.status == ProjectStatus.TEAM_PENDING,
                        Team.status == TeamStatus.PENDING,
                        Invitation.sent_at.is_(None),
                        TeamMember.status == MemberStatus.INVITED,
                    )
                    .distinct()
                )
            )
            .tuples()
            .all()
        )
        due = (
            await db.scalars(
                select(Invitation.id).where(
                    Invitation.sent_at.is_not(None),
                    Invitation.responded_at.is_(None),
                    Invitation.expires_at <= now,
                )
            )
        ).all()
    for team_id, project_id in pending_teams:
        async with _system() as db:
            project = await _lock_project(db, project_id)
            team = await db.scalar(select(Team).where(Team.id == team_id).with_for_update())
            if team is not None and project.status == ProjectStatus.TEAM_PENDING:
                sent += await send_invitations(db, project, team, now, settings)
            await db.commit()
    for inv_id in due:
        proposal = None
        async with _system() as db:
            row = (
                await db.execute(
                    select(Team.project_id)
                    .join(TeamMember, TeamMember.team_id == Team.id)
                    .join(Invitation, Invitation.team_member_id == TeamMember.id)
                    .where(Invitation.id == inv_id)
                )
            ).first()
            if row is None:
                continue
            project = await _lock_project(db, row[0])
            team = await _team_of(db, project.id, lock=True)
            inv = await db.scalar(
                select(Invitation).where(Invitation.id == inv_id).with_for_update()
            )
            if team is None or inv is None or inv.responded_at is not None:
                await db.rollback()
                continue  # answered meanwhile
            member = await db.scalar(
                select(TeamMember).where(TeamMember.id == inv.team_member_id).with_for_update()
            )
            if member is None or member.status != MemberStatus.INVITED:
                await db.rollback()
                continue
            bid = await db.scalar(select(Bid).where(Bid.id == member.bid_id).with_for_update())
            res = await _reservation(db, project.id, member.developer_id, lock=True)
            member.status = MemberStatus.EXPIRED
            inv.response = InvitationResponse.EXPIRED
            inv.responded_at = now
            if bid is not None:
                bid.status = BidStatus.EXPIRED
                bid.version += 1
            if res is not None:
                res.status = ReservationStatus.RELEASED
            await notify(
                db,
                project.client_id,
                "INVITATION_EXPIRED",
                title="Invitation expired",
                body=f"An invitation for “{project.title}” expired without an answer. DevSync "
                "is looking for a replacement.",
                link=_link_team(project.id),
            )
            await write_audit(
                db,
                action="invitation.expired",
                entity_type="invitation",
                entity_id=inv.id,
                actor_role="SYSTEM",
            )
            if project.status in LIVE_PROJECT:
                proposal = await repair_svc.open_repair(
                    db, project, team, member, now=now, settings=settings
                )
            await db.commit()
            expired += 1
        if proposal is not None:
            repair_svc.queue(proposal)
    return {"invitations_sent": sent, "invitations_expired": expired}


# --------------------------------------------------------------------------- team read


@dataclass
class _View:
    project: Project
    team: Team
    role: str  # CLIENT, ADMIN, MEMBER
    me: TeamMember | None


async def _view(db: AsyncSession, ctx: Ctx, project_id: uuid.UUID) -> _View:
    """Who the caller is for this project's team; 404 for anyone else (D130)."""
    project = await db.get(Project, project_id)
    team = await _team_of(db, project_id) if project is not None else None
    if project is None or team is None:
        raise NotFoundError
    if project.client_id == ctx.uid:
        return _View(project, team, "CLIENT", None)
    if ctx.principal.is_admin:
        return _View(project, team, "ADMIN", None)
    me = await db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.developer_id == ctx.uid,
            TeamMember.status.in_(CURRENT),
        )
    )
    if me is None:
        raise NotFoundError
    return _View(project, team, "MEMBER", me)


def slots_filled(slots: Sequence[ProjectSlot], members: Sequence[TeamMember]) -> list[ProjectSlot]:
    """Slots that don't yet have `count` ACTIVE members (empty: every place accepted)."""
    active: dict[uuid.UUID, int] = {}
    for m in members:
        if m.status == MemberStatus.ACTIVE:
            active[m.slot_id] = active.get(m.slot_id, 0) + 1
    return [s for s in slots if active.get(s.id, 0) < s.count]


async def _recommendation(
    db: AsyncSession,
    team: Team,
    members: Sequence[TeamMember],
    *,
    names: dict[uuid.UUID, str],
    reps: dict[uuid.UUID, Any],
    invs: dict[uuid.UUID, Invitation],
) -> LeadRecommendationOut | None:
    """§1.6 rule 1 when nobody leads (D131): ACTIVE members, X_m and the tie-breaks; the outgoing
    lead of an approved change request is excluded and its suggested member pre-selected."""
    if any(m.is_lead and m.status == MemberStatus.ACTIVE for m in members):
        return None
    approved = await db.scalar(
        select(LeadChangeRequest)
        .where(
            LeadChangeRequest.team_id == team.id,
            LeadChangeRequest.status == LeadChangeStatus.APPROVED,
            LeadChangeRequest.outgoing_member_id.is_not(None),
        )
        .order_by(LeadChangeRequest.decided_at.desc())
        .limit(1)
    )
    led = await _led_teams(db, [m.developer_id for m in members])
    candidates = [
        LeadCandidate(
            member_id=str(m.id),
            developer_id=str(m.developer_id),
            active=m.status == MemberStatus.ACTIVE,
            xm=reps[m.developer_id].xm,
            completed_projects=reps[m.developer_id].completed_projects,
            competency=reps[m.developer_id].c,
            responded_at=invs[m.id].responded_at if m.id in invs else m.joined_at,
            declined_lead=m.lead_declined_at is not None,
            led_teams=led.get(m.developer_id, 0),
        )
        for m in members
        if m.developer_id in reps
    ]
    exclude = [str(approved.outgoing_member_id)] if approved is not None else []
    rec = recommend_lead(candidates, exclude)
    if rec is None:
        return None
    member_id = uuid.UUID(rec.member_id)
    pre = None
    if approved is not None and approved.suggested_member_id is not None:
        pre_member = next(
            (
                m
                for m in members
                if m.id == approved.suggested_member_id and m.status == MemberStatus.ACTIVE
            ),
            None,
        )
        pre = pre_member.id if pre_member is not None else None
    who = next(m for m in members if m.id == member_id)
    return LeadRecommendationOut(
        member_id=member_id,
        developer_name=names.get(who.developer_id, ""),
        reason=rec.reason,
        preselected_member_id=pre,
    )


async def _led_teams(db: AsyncSession, developer_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Completed teams each developer led (D131); 0 for everyone until Phase 11 completes teams."""
    if not developer_ids:
        return {}
    rows = await db.execute(
        select(TeamMember.developer_id, func.count())
        .join(Team, Team.id == TeamMember.team_id)
        .where(
            TeamMember.developer_id.in_(developer_ids),
            TeamMember.is_lead.is_(True),
            Team.status == TeamStatus.COMPLETED,
        )
        .group_by(TeamMember.developer_id)
    )
    return {d: int(n) for d, n in rows.tuples().all()}


async def get_team(ctx: Ctx, project_id: uuid.UUID) -> TeamForClient | TeamForMember:
    """The project's team, shaped for the caller (D130, D134)."""
    authorize(ctx.principal, "team.read")
    settings = await active_settings(ctx.db)
    async with _system() as db:
        v = await _view(db, ctx, project_id)
        members = await _members(db, v.team.id)
        if v.role == "MEMBER":
            members = [m for m in members if m.status in CURRENT]
        invs = await _invitations(db, [m.id for m in members])
        dev_ids = [m.developer_id for m in members]
        names = dict(
            (await db.execute(select(User.id, User.display_name).where(User.id.in_(dev_ids))))
            .tuples()
            .all()
        )
        reps = await reputation_read.read_many(db, dev_ids, settings)
        hours = await bidrepo.profile_hours_by_developer(db, dev_ids)
        slots = list(await projrepo.load_slots(db, project_id))
        skill_names = await _skill_names(db, [s.skill_id for s in slots])
        label = {s.id: s.label or skill_names.get(s.skill_id, "Role") for s in slots}
        # A stable order for people to read (role, then name): members are created together, so
        # creation time ties and the random ids would shuffle the list between loads.
        members.sort(
            key=lambda m: (
                label.get(m.slot_id, "Role").casefold(),
                names.get(m.developer_id, "Developer").casefold(),
                str(m.id),
            )
        )
        lead = next((m.id for m in members if m.is_lead and m.status == MemberStatus.ACTIVE), None)
        base: dict[str, Any] = {
            "project_id": v.project.id,
            "project_title": v.project.title,
            "project_status": v.project.status.value,
            "project_version": v.project.version,
            "team_id": v.team.id,
            "team_status": v.team.status.value,
            "lead_member_id": lead,
        }

        def common(m: TeamMember) -> dict[str, Any]:
            rep = reps.get(m.developer_id)
            return {
                "id": m.id,
                "developer_id": m.developer_id,
                "developer_name": names.get(m.developer_id, "Developer"),
                "slot_id": m.slot_id,
                "slot_label": label.get(m.slot_id, "Role"),
                "status": m.status.value,
                "is_lead": m.is_lead and m.status == MemberStatus.ACTIVE,
                "is_newcomer": bool(rep and rep.is_newcomer),
                "competency": round(rep.c, 3) if rep else 0.0,
                "teamwork": round(rep.xm, 3) if rep else 0.0,
                "hours_per_week": hours.get(m.developer_id, 20),
                "joined_at": m.joined_at,
                "invitation": _invitation_out(invs.get(m.id), ctx.now),
                "is_you": m.developer_id == ctx.uid,
            }

        requests = list(
            (
                await db.scalars(
                    select(LeadChangeRequest)
                    .where(LeadChangeRequest.team_id == v.team.id)
                    .order_by(LeadChangeRequest.created_at.desc())
                    .limit(50)
                )
            ).all()
        )
        if v.role == "MEMBER":
            me = v.me
            if me is None:  # found or locked above; fail closed
                raise NotFoundError
            own = [r for r in requests if r.requested_by == ctx.uid]
            return TeamForMember(
                **base,
                my_member_id=me.id,
                members=[TeamMemberForMember(**common(m)) for m in members],
                lead_change_requests=[_lcr_out(r, names) for r in own],
            )
        booked = await _fully_booked(db, v.project, members, invs, ctx.now)
        client_members = [
            TeamMemberForClient(
                **common(m),
                price_paisa=m.price_paisa,
                days_needed=m.days_needed,
                left_reason=m.left_reason,
                lead_declined=m.lead_declined_at is not None,
                fully_booked=m.id in booked,
            )
            for m in members
        ]
        open_slots = slots_filled(slots, members)
        live = v.project.status in LIVE_PROJECT and v.team.status in (
            TeamStatus.PENDING,
            TeamStatus.ACTIVE,
        )
        rec = None
        if live and (not open_slots or v.project.status == ProjectStatus.IN_PROGRESS):
            rec = await _recommendation(db, v.team, members, names=names, reps=reps, invs=invs)
        blockers: list[str] = []
        if v.project.status == ProjectStatus.TEAM_PENDING:
            for s in sorted(open_slots, key=lambda s: (label.get(s.id, "").casefold(), str(s.id))):
                blockers.append(f"{label.get(s.id, 'A role')} needs a developer who accepted.")
            if lead is None:
                blockers.append("Choose a team lead.")
        removals = list(
            (
                await db.scalars(
                    select(MemberRemovalRequest)
                    .join(TeamMember, TeamMember.id == MemberRemovalRequest.team_member_id)
                    .where(TeamMember.team_id == v.team.id)
                    .order_by(MemberRemovalRequest.created_at.desc())
                )
            ).all()
        )
        repair = await db.scalar(
            select(RepairProposal)
            .where(RepairProposal.team_id == v.team.id)
            .order_by(RepairProposal.created_at.desc())
            .limit(1)
        )
        by_member = {m.id: m for m in members}
        return TeamForClient(
            **base,
            members=client_members,
            recommendation=rec,
            can_choose_lead=live
            and (not open_slots or v.project.status == ProjectStatus.IN_PROGRESS)
            and v.role == "CLIENT",
            can_start=v.project.status == ProjectStatus.TEAM_PENDING
            and not blockers
            and v.role == "CLIENT",
            start_blockers=blockers,
            lead_change_requests=[_lcr_out(r, names) for r in requests],
            removal_requests=[
                RemovalRequestOut(
                    id=r.id,
                    team_member_id=r.team_member_id,
                    member_name=names.get(by_member[r.team_member_id].developer_id, "Developer")
                    if r.team_member_id in by_member
                    else "Developer",
                    reason=r.reason,
                    basis=r.basis.value,
                    status=r.status.value,
                    decision_reason=r.decision_reason,
                    created_at=r.created_at,
                )
                for r in removals
            ],
            repair=RepairSummaryOut(
                id=repair.id,
                status=repair.status.value,
                departed_member_id=repair.departed_member_id,
                job_id=repair.job_id,
                created_at=repair.created_at,
            )
            if repair is not None
            else None,
        )


def _lcr_out(r: LeadChangeRequest, names: dict[uuid.UUID, str]) -> LeadChangeRequestOut:
    return LeadChangeRequestOut(
        id=r.id,
        requested_by=r.requested_by,
        requester_name=names.get(r.requested_by, "Developer"),
        reason=r.reason,
        suggested_member_id=r.suggested_member_id,
        status=r.status.value,
        decision_reason=r.decision_reason,
        created_at=r.created_at,
        decided_at=r.decided_at,
    )


async def _fully_booked(
    db: AsyncSession,
    project: Project,
    members: Sequence[TeamMember],
    invs: dict[uuid.UUID, Invitation],
    now: datetime,
) -> set[uuid.UUID]:
    """Invited members whose accept would be refused for lack of free hours now (D124)."""
    out: set[uuid.UUID] = set()
    today = _today(now)
    for m in members:
        if m.status != MemberStatus.INVITED or invitation_state(invs.get(m.id), now) != "PENDING":
            continue
        start = max(project.start_date or today, today)
        period = avail.Period(start, start + timedelta(days=project.deadline_days))
        hours, committed = await free_hours(db, m.developer_id, project.id, period)
        bid = await db.get(Bid, m.bid_id)
        if bid is not None and committed + bid.hours_per_week_committed > hours:
            out.add(m.id)
    return out


# -------------------------------------------------------------------------------- lead


async def _client_team(db: AsyncSession, ctx: Ctx, project_id: uuid.UUID) -> tuple[Project, Team]:
    project = await _lock_project(db, project_id)
    if project.client_id != ctx.uid:
        raise NotFoundError
    team = await _team_of(db, project_id, lock=True)
    if team is None:
        raise NotFoundError
    if project.status not in LIVE_PROJECT or team.status not in (
        TeamStatus.PENDING,
        TeamStatus.ACTIVE,
    ):
        raise InvalidStateTransition(project.status.value, [], "This team can't be changed now.")
    return project, team


def _check_version(project: Project, if_match: int | None) -> None:
    if if_match is not None and if_match != project.version:
        raise DomainError(
            "This project was changed in another tab. Reload and try again.",
            code=ErrorCode.VERSION_CONFLICT,
            extra={"current_version": project.version},
        )


async def choose_lead(
    ctx: Ctx, project_id: uuid.UUID, body: ChooseLeadIn, if_match: int | None
) -> ActionOut:
    """§1.6 rules 2 and 4 (D132): the client picks any ACTIVE member who hasn't declined the role,
    once every place is accepted (before start) — after start at any time, with a reason."""
    authorize(ctx.principal, "team.lead.choose")
    async with _system() as db:
        project, team = await _client_team(db, ctx, project_id)
        _check_version(project, if_match)
        members = await _members(db, team.id, lock=True)
        slots = list(await projrepo.load_slots(db, project_id))
        started = project.status == ProjectStatus.IN_PROGRESS
        if not started and slots_filled(slots, members):
            raise DomainError(
                "Every place needs an accepted developer before you choose a lead.",
                code=ErrorCode.INVALID_STATE,
            )
        if started and body.reason is None:
            raise DomainError(
                "Give a reason for changing the lead.",
                code=ErrorCode.VALIDATION_ERROR,
                fields={"reason": "required after the project started"},
            )
        target = next((m for m in members if m.id == body.member_id), None)
        if target is None or target.status != MemberStatus.ACTIVE:
            raise DomainError(
                "Only a developer who accepted can lead the team.", code=ErrorCode.INVALID_STATE
            )
        if target.lead_declined_at is not None:
            raise DomainError(
                "This developer declined the lead role.", code=ErrorCode.INVALID_STATE
            )
        previous = next((m for m in members if m.is_lead and m.id != target.id), None)
        if previous is not None:
            previous.is_lead = False
            await db.flush()  # one lead at a time (partial unique index)
        target.is_lead = True
        await db.execute(
            update(LeadChangeRequest)
            .where(LeadChangeRequest.team_id == team.id)
            .values(outgoing_member_id=None)
        )  # the exclusion ends with this choice
        project.version += 1
        names = dict(
            (
                await db.execute(
                    select(User.id, User.display_name).where(
                        User.id.in_([m.developer_id for m in members])
                    )
                )
            )
            .tuples()
            .all()
        )
        await notify(
            db,
            target.developer_id,
            "LEAD_CHOSEN",
            title="You are team lead",
            body=f"The client chose you as the team lead for “{project.title}”. You can decline "
            "the lead role (not the team).",
            link=_link_workspace(project.id) if started else "/dev",
        )
        await _email(
            db,
            target.developer_id,
            "team_lead",
            project=project.title,
            link=_link_workspace(project.id) if started else "/dev",
        )
        if started:
            lead_name = names.get(target.developer_id, "A teammate")
            for m in members:
                if m.status == MemberStatus.ACTIVE and m.id != target.id:
                    await notify(
                        db,
                        m.developer_id,
                        "LEAD_CHANGED",
                        title="New team lead",
                        body=f"{lead_name} is now the team lead for “{project.title}”.",
                        link=_link_workspace(project.id),
                    )
                    await _email(
                        db,
                        m.developer_id,
                        "lead_changed",
                        project=project.title,
                        lead=lead_name,
                        link=_link_workspace(project.id),
                    )
        await write_audit(
            db,
            action="team.lead_chosen",
            entity_type="team",
            entity_id=team.id,
            actor_id=ctx.uid,
            actor_role="CLIENT",
            before={"lead": str(previous.id) if previous else None},
            after={"lead": str(target.id), "reason": body.reason},
        )
        await db.commit()
    return ActionOut(status="LEAD_CHOSEN", message="Team lead chosen.")


async def decline_lead(ctx: Ctx, project_id: uuid.UUID) -> ActionOut:
    """§1.6 rule 3: the lead gives up the role (not the team), before or after start; the client
    is shown the next recommendation (D132)."""
    authorize(ctx.principal, "team.lead.decline")
    async with _system() as db:
        project = await _lock_project(db, project_id)
        team = await _team_of(db, project_id, lock=True)
        me = None
        if team is not None:
            me = await db.scalar(
                select(TeamMember)
                .where(
                    TeamMember.team_id == team.id,
                    TeamMember.developer_id == ctx.uid,
                    TeamMember.status == MemberStatus.ACTIVE,
                )
                .with_for_update()
            )
        if team is None or me is None:
            raise NotFoundError
        if not me.is_lead:
            raise DomainError("You aren't the team lead.", code=ErrorCode.INVALID_STATE)
        me.is_lead = False
        me.lead_declined_at = ctx.now
        project.version += 1
        await notify(
            db,
            project.client_id,
            "LEAD_DECLINED",
            title="Lead role declined",
            body=f"The team lead of “{project.title}” declined the role. Choose the next lead.",
            link=_link_team(project.id),
        )
        await write_audit(
            db,
            action="team.lead_declined",
            entity_type="team",
            entity_id=team.id,
            actor_id=ctx.uid,
            actor_role="DEVELOPER",
        )
        await db.commit()
    return ActionOut(status="LEAD_DECLINED", message="You are no longer the team lead.")


async def request_lead_change(
    ctx: Ctx, project_id: uuid.UUID, body: LeadChangeRequestIn
) -> LeadChangeRequestOut:
    """§1.6 rule 4: an ACTIVE member (not the lead) asks the client to change the lead (D132:
    one open request per member, at most 3 a week per member and project)."""
    authorize(ctx.principal, "team.lead.request")
    async with _system() as db:
        project = await _lock_project(db, project_id)
        team = await _team_of(db, project_id, lock=True)
        members = await _members(db, team.id) if team is not None else []
        me = next(
            (m for m in members if m.developer_id == ctx.uid and m.status == MemberStatus.ACTIVE),
            None,
        )
        if team is None or me is None:
            raise NotFoundError
        if project.status not in LIVE_PROJECT:
            raise InvalidStateTransition(project.status.value, [])
        if me.is_lead:
            raise DomainError(
                "You are the lead: decline the role instead.", code=ErrorCode.INVALID_STATE
            )
        if not any(m.is_lead and m.status == MemberStatus.ACTIVE for m in members):
            raise DomainError("The team has no lead to change.", code=ErrorCode.INVALID_STATE)
        if body.suggested_member_id is not None:
            sug = next((m for m in members if m.id == body.suggested_member_id), None)
            if sug is None or sug.status != MemberStatus.ACTIVE or sug.is_lead:
                raise DomainError(
                    "Suggest a teammate who accepted and isn't the lead.",
                    code=ErrorCode.VALIDATION_ERROR,
                    fields={"suggested_member_id": "not an active teammate"},
                )
        open_one = await db.scalar(
            select(func.count())
            .select_from(LeadChangeRequest)
            .where(
                LeadChangeRequest.team_id == team.id,
                LeadChangeRequest.requested_by == ctx.uid,
                LeadChangeRequest.status == LeadChangeStatus.PENDING,
            )
        )
        if open_one:
            raise DomainError(
                "You already have a request waiting for the client.", code=ErrorCode.LIMIT_REACHED
            )
        recent = await db.scalar(
            select(func.count())
            .select_from(LeadChangeRequest)
            .where(
                LeadChangeRequest.team_id == team.id,
                LeadChangeRequest.requested_by == ctx.uid,
                LeadChangeRequest.created_at > ctx.now - timedelta(days=7),
            )
        )
        if (recent or 0) >= MAX_LEAD_CHANGE_REQUESTS_PER_WEEK:
            raise DomainError(
                "You can ask for a lead change at most 3 times a week.",
                code=ErrorCode.LIMIT_REACHED,
            )
        req = LeadChangeRequest(
            team_id=team.id,
            requested_by=ctx.uid,
            reason=body.reason,
            suggested_member_id=body.suggested_member_id,
        )
        db.add(req)
        await db.flush()
        await notify(
            db,
            project.client_id,
            "LEAD_CHANGE_REQUESTED",
            title="Lead change requested",
            body=f"A member of “{project.title}” asked you to change the team lead.",
            link=_link_team(project.id),
        )
        await write_audit(
            db,
            action="team.lead_change_requested",
            entity_type="lead_change_request",
            entity_id=req.id,
            actor_id=ctx.uid,
            actor_role="DEVELOPER",
        )
        names = {ctx.uid: (await db.get(User, ctx.uid)).display_name}
        out = _lcr_out(req, names)
        await db.commit()
    return out


async def _own_request(
    db: AsyncSession, request_id: uuid.UUID
) -> tuple[LeadChangeRequest, Team, Project]:
    req = await db.scalar(select(LeadChangeRequest).where(LeadChangeRequest.id == request_id))
    team = await db.get(Team, req.team_id) if req is not None else None
    if req is None or team is None:
        raise NotFoundError
    project = await _lock_project(db, team.project_id)
    req = await db.scalar(
        select(LeadChangeRequest).where(LeadChangeRequest.id == request_id).with_for_update()
    )
    if req is None:  # found or locked above; fail closed
        raise NotFoundError
    return req, team, project


async def decide_lead_change(
    ctx: Ctx, request_id: uuid.UUID, *, approve: bool, reason: str | None
) -> ActionOut:
    """The client approves (the current lead becomes a normal member; the next recommendation
    excludes them and pre-selects a suggested member) or rejects with a reason (D132)."""
    authorize(ctx.principal, "team.lead.decide")
    async with _system() as db:
        req, team, project = await _own_request(db, request_id)
        if project.client_id != ctx.uid:
            raise NotFoundError
        if req.status != LeadChangeStatus.PENDING:
            raise InvalidStateTransition(req.status.value, [], "This request was already decided.")
        req.status = LeadChangeStatus.APPROVED if approve else LeadChangeStatus.REJECTED
        req.decided_by, req.decided_at = ctx.uid, ctx.now
        req.decision_reason = reason
        if approve:
            lead = await db.scalar(
                select(TeamMember)
                .where(
                    TeamMember.team_id == team.id,
                    TeamMember.is_lead.is_(True),
                    TeamMember.status == MemberStatus.ACTIVE,
                )
                .with_for_update()
            )
            if lead is not None:
                lead.is_lead = False
                req.outgoing_member_id = lead.id
                await notify(
                    db,
                    lead.developer_id,
                    "LEAD_CHANGED",
                    title="You are no longer team lead",
                    body=f"The client approved a lead change on “{project.title}”.",
                    link=_link_workspace(project.id),
                )
            project.version += 1
        await notify(
            db,
            req.requested_by,
            "LEAD_CHANGE_DECIDED",
            title="Lead change approved" if approve else "Lead change not approved",
            body=(
                f"The client approved your request on “{project.title}” and will choose the "
                "next lead."
            )
            if approve
            else f"The client's reason: {reason}",
            link=_link_workspace(project.id),
        )
        await write_audit(
            db,
            action="team.lead_change_" + ("approved" if approve else "rejected"),
            entity_type="lead_change_request",
            entity_id=req.id,
            actor_id=ctx.uid,
            actor_role="CLIENT",
        )
        await db.commit()
    return ActionOut(
        status=req.status.value, message="Request approved." if approve else "Request rejected."
    )


async def withdraw_lead_change(ctx: Ctx, request_id: uuid.UUID) -> ActionOut:
    authorize(ctx.principal, "team.lead.request")
    async with _system() as db:
        req, _team, _project = await _own_request(db, request_id)
        if req.requested_by != ctx.uid:
            raise NotFoundError
        if req.status != LeadChangeStatus.PENDING:
            raise InvalidStateTransition(req.status.value, [], "This request was already decided.")
        req.status = LeadChangeStatus.WITHDRAWN
        await db.commit()
    return ActionOut(status="WITHDRAWN", message="Request withdrawn.")


# ------------------------------------------------------------------------------- start


async def start_project(ctx: Ctx, project_id: uuid.UUID, if_match: int | None) -> ActionOut:
    """TEAM_PENDING → IN_PROGRESS (D118, D119), all or nothing."""
    authorize(ctx.principal, "project.start")
    async with _system() as db:
        project = await _lock_project(db, project_id)
        if project.client_id != ctx.uid:
            raise NotFoundError
        if project.status != ProjectStatus.TEAM_PENDING:
            raise InvalidStateTransition(
                project.status.value, [], "Only a project waiting for its team can start."
            )
        _check_version(project, if_match)
        team = await _team_of(db, project_id, lock=True)
        if team is None:
            raise NotFoundError
        members = await _members(db, team.id, lock=True)
        slots = list(await projrepo.load_slots(db, project_id))
        allowed = ["choose_lead"]
        if slots_filled(slots, members):
            raise InvalidStateTransition(
                "TEAM_PENDING",
                ["wait_for_answers", "repair"],
                "Every place needs a developer who accepted.",
            )
        if not any(m.is_lead and m.status == MemberStatus.ACTIVE for m in members):
            raise InvalidStateTransition("TEAM_PENDING", allowed, "Choose a team lead first.")
        today = _today(ctx.now)
        start = max(project.start_date or today, today)
        period = avail.Period(start, start + timedelta(days=project.deadline_days))
        active = [m for m in members if m.status == MemberStatus.ACTIVE]
        names = dict(
            (
                await db.execute(
                    select(User.id, User.display_name).where(
                        User.id.in_([m.developer_id for m in active])
                    )
                )
            )
            .tuples()
            .all()
        )
        for m in active:
            hours, committed = await free_hours(db, m.developer_id, project.id, period)
            bid = await db.get(Bid, m.bid_id)
            need = bid.hours_per_week_committed if bid is not None else 20
            if committed + need > hours:
                who = names.get(m.developer_id, "A member")
                raise DomainError(
                    f"{who} doesn't have enough free hours from {start:%d %b %Y}. Wait until they "
                    "free some hours, or use leave and team repair.",
                    code=ErrorCode.UNAVAILABLE,
                    extra={"member_id": str(m.id)},
                )
        for m in active:
            res = await _reservation(db, project.id, m.developer_id, lock=True)
            if res is not None:
                res.from_date, res.to_date = period.from_, period.to
                res.status = ReservationStatus.CONFIRMED
        project.start_date = start
        project.status = ProjectStatus.IN_PROGRESS
        project.version += 1
        team.status = TeamStatus.ACTIVE
        activated = await _activate_and_approve(db, project_id, start)
        await _start_notices(db, project, active)
        await write_audit(
            db,
            action="project.started",
            entity_type="project",
            entity_id=project.id,
            actor_id=ctx.uid,
            actor_role="CLIENT",
            after={
                "start_date": start.isoformat(),
                "milestones_active": activated,
                "members": len(active),
            },
        )
        await db.commit()
    return ActionOut(status="IN_PROGRESS", message="The project has started.")


async def _activate_and_approve(db: AsyncSession, project_id: uuid.UUID, start: date) -> int:
    """D118: root milestones ACTIVE from the start date; D119: the lead approves the baseline."""
    milestones = list(await projrepo.load_milestones(db, project_id))
    deps = await projrepo.load_dependencies(db, project_id)
    preds: dict[uuid.UUID, set[uuid.UUID]] = {m.id: set() for m in milestones}
    for d in deps:
        preds.setdefault(d.successor_id, set()).add(d.predecessor_id)
    activated = 0
    for m in milestones:
        if milestone_may_activate(m, preds.get(m.id, set())):
            m.status = MilestoneStatus.ACTIVE
            m.actual_start = start
            activated += 1
    baseline = await db.scalar(
        select(PlanBaseline)
        .where(PlanBaseline.project_id == project_id)
        .order_by(PlanBaseline.version.desc())
        .limit(1)
        .with_for_update()
    )
    if baseline is not None:
        baseline.approved_by_lead = True
    return activated


async def _start_notices(db: AsyncSession, project: Project, active: list[TeamMember]) -> None:
    """ "Project started" to the client and the team; "You are team lead" to the lead (§12)."""
    lead = next(m for m in active if m.is_lead)
    for user_id in [project.client_id, *(m.developer_id for m in active)]:
        link = _link_workspace(project.id)
        await notify(
            db,
            user_id,
            "PROJECT_STARTED",
            title="Project started",
            body=f"“{project.title}” has started. The team workspace is open.",
            link=link,
        )
        await _email(db, user_id, "project_started", project=project.title, link=link)
    await notify(
        db,
        lead.developer_id,
        "LEAD_CHOSEN",
        title="You are team lead",
        body=f"You lead the team of “{project.title}”.",
        link=_link_workspace(project.id),
    )
    await _email(
        db,
        lead.developer_id,
        "team_lead",
        project=project.title,
        link=_link_workspace(project.id),
    )


# ------------------------------------------------------------------- leave and removal


async def _depart(
    db: AsyncSession,
    project: Project,
    team: Team,
    member: TeamMember,
    *,
    status: MemberStatus,
    reason: str,
    now: datetime,
    settings: PlatformSettingsValues,
) -> RepairProposal | None:
    """Shared by leave and removal: member gone, reservation released, lead unset, the client
    told, repair queued (§9.9)."""
    member.status = status
    member.left_at = now
    member.left_reason = reason
    was_lead = member.is_lead
    member.is_lead = False
    res = await _reservation(db, project.id, member.developer_id, lock=True)
    if res is not None:
        res.status = ReservationStatus.RELEASED
    project.version += 1
    word = "left" if status == MemberStatus.LEFT else "was removed from"
    extra = " Choose a new team lead." if was_lead else ""
    await notify(
        db,
        project.client_id,
        "MEMBER_LEFT",
        title="A member left the team",
        body=f"A member {word} “{project.title}”. DevSync is looking for a replacement.{extra}",
        link=_link_team(project.id),
    )
    # Evidence (D149): who left and from which place — never the reason (private, D130).
    activity.record_system(
        db,
        project_id=project.id,
        type="member.left",
        entity_type="TEAM_MEMBER",
        entity_id=member.id,
        actor_id=None,
        subject_id=member.developer_id,
        data={
            "member_id": member.id,
            "slot_label": await _slot_label(db, member.slot_id),
            "how": "LEFT" if status == MemberStatus.LEFT else "REMOVED",
        },
        at=now,
    )
    await _unassign_tasks(db, project, team, member, now=now)
    return await repair_svc.open_repair(db, project, team, member, now=now, settings=settings)


async def _slot_label(db: AsyncSession, slot_id: uuid.UUID) -> str:
    slot = await db.get(ProjectSlot, slot_id)
    if slot is None:
        return "Role"
    if slot.label:
        return slot.label
    return (await _skill_names(db, [slot.skill_id])).get(slot.skill_id, "Role")


async def _unassign_tasks(
    db: AsyncSession, project: Project, team: Team, member: TeamMember, *, now: datetime
) -> None:
    """A departing member's unfinished tasks become unassigned and the lead is told (D143)."""
    result = await db.execute(
        update(Task)
        .where(
            Task.project_id == project.id,
            Task.assignee_id == member.developer_id,
            Task.status != TaskStatus.DONE,
        )
        .values(assignee_id=None, version=Task.version + 1, updated_at=now)
        .returning(Task.id)
    )
    count = len(result.all())
    lead = await db.scalar(
        select(TeamMember.developer_id).where(
            TeamMember.team_id == team.id,
            TeamMember.is_lead.is_(True),
            TeamMember.status == MemberStatus.ACTIVE,
        )
    )
    if count and lead is not None:
        await notify(
            db,
            lead,
            "TASKS_UNASSIGNED",
            title=f"{count} {'task needs' if count == 1 else 'tasks need'} a new assignee",
            body=f"A member left “{project.title}”; their unfinished tasks are unassigned.",
            link=f"/w/{project.id}/tasks",
        )


async def leave(ctx: Ctx, member_id: uuid.UUID, body: LeaveIn) -> ActionOut:
    """A member leaves (reason required); if they led, the next lead is recommended (§1.6 rule 5)
    in parallel with repair."""
    authorize(ctx.principal, "team.leave")
    settings = await active_settings(ctx.db)
    async with _system() as db:
        found = await db.get(TeamMember, member_id)
        if found is None or found.developer_id != ctx.uid:
            raise NotFoundError
        team = await db.get(Team, found.team_id)
        if team is None:  # found or locked above; fail closed
            raise NotFoundError
        project = await _lock_project(db, team.project_id)
        team = await _team_of(db, project.id, lock=True)
        member = await db.scalar(
            select(TeamMember).where(TeamMember.id == member_id).with_for_update()
        )
        if team is None:  # found or locked above; fail closed
            raise NotFoundError
        if member is None:  # found or locked above; fail closed
            raise NotFoundError
        if member.status != MemberStatus.ACTIVE or project.status not in LIVE_PROJECT:
            raise InvalidStateTransition(
                member.status.value, [], "Only an active member can leave a live project."
            )
        proposal = await _depart(
            db,
            project,
            team,
            member,
            status=MemberStatus.LEFT,
            reason=body.reason,
            now=ctx.now,
            settings=settings,
        )
        await write_audit(
            db,
            action="team.member_left",
            entity_type="team_member",
            entity_id=member.id,
            actor_id=ctx.uid,
            actor_role="DEVELOPER",
        )
        await db.commit()
    repair_svc.queue(proposal)
    return ActionOut(status="LEFT", message="You left the team.")


async def request_removal(
    ctx: Ctx, member_id: uuid.UUID, body: RemovalRequestIn
) -> RemovalRequestOut:
    """The client asks an admin to remove a member (§8, D121). A basis is required: inactivity
    ≥ `alerts.repair_days` (no signal until Phase 9 → 409) or a dispute (Phase 12 → 409)."""
    authorize(ctx.principal, "team.removal.request")
    settings = await active_settings(ctx.db)
    async with _system() as db:
        member = await db.get(TeamMember, member_id)
        team = await db.get(Team, member.team_id) if member is not None else None
        project = await db.get(Project, team.project_id) if team is not None else None
        if member is None or project is None or project.client_id != ctx.uid:
            raise NotFoundError
        if member.status != MemberStatus.ACTIVE or project.status != ProjectStatus.IN_PROGRESS:
            raise InvalidStateTransition(
                member.status.value,
                [],
                "Only an active member of a started project can be removed.",
            )
        if body.basis == RemovalBasis.DISPUTE.value:
            raise DomainError(
                "Removal after a dispute arrives with disputes in Phase 12.",
                code=ErrorCode.INVALID_STATE,
            )
        days = await member_inactive_days(db, member, ctx.now)
        if days is None:  # never became ACTIVE: nothing to measure
            raise DomainError(
                "This member hasn't started on the project, so inactivity can't be measured.",
                code=ErrorCode.INVALID_STATE,
            )
        if days < settings.alerts.repair_days:
            raise DomainError(
                f"The member was active {days} days ago; removal needs "
                f"{settings.alerts.repair_days} days without activity.",
                code=ErrorCode.INVALID_STATE,
            )
        pending = await db.scalar(
            select(func.count())
            .select_from(MemberRemovalRequest)
            .where(
                MemberRemovalRequest.team_member_id == member.id,
                MemberRemovalRequest.status == RemovalStatus.PENDING,
            )
        )
        if pending:
            raise DomainError(
                "A removal request for this member is already waiting.",
                code=ErrorCode.LIMIT_REACHED,
            )
        req = MemberRemovalRequest(
            team_member_id=member.id,
            requested_by=ctx.uid,
            reason=body.reason,
            basis=RemovalBasis(body.basis),
        )
        db.add(req)
        await db.flush()
        await write_audit(
            db,
            action="team.removal_requested",
            entity_type="member_removal_request",
            entity_id=req.id,
            actor_id=ctx.uid,
            actor_role="CLIENT",
        )
        name = (await db.get(User, member.developer_id)).display_name
        out = RemovalRequestOut(
            id=req.id,
            team_member_id=member.id,
            member_name=name,
            reason=req.reason,
            basis=req.basis.value,
            status="PENDING",
            decision_reason=None,
            created_at=req.created_at,
        )
        await db.commit()
    return out


async def admin_removals(ctx: Ctx) -> list[RemovalRequestOut]:
    authorize(ctx.principal, "admin.access")
    async with _system() as db:
        rows = (
            (
                await db.execute(
                    select(MemberRemovalRequest, User.display_name)
                    .join(TeamMember, TeamMember.id == MemberRemovalRequest.team_member_id)
                    .join(User, User.id == TeamMember.developer_id)
                    .order_by(
                        (MemberRemovalRequest.status == RemovalStatus.PENDING).desc(),
                        MemberRemovalRequest.created_at.desc(),
                    )
                    .limit(100)
                )
            )
            .tuples()
            .all()
        )
        # Built inside the session: the rows expire when it closes.
        return [
            RemovalRequestOut(
                id=r.id,
                team_member_id=r.team_member_id,
                member_name=name,
                reason=r.reason,
                basis=r.basis.value,
                status=r.status.value,
                decision_reason=r.decision_reason,
                created_at=r.created_at,
            )
            for r, name in rows
        ]


async def decide_removal(
    ctx: Ctx, request_id: uuid.UUID, *, approve: bool, reason: str
) -> ActionOut:
    """Admin (step-up): approve → member REMOVED with the same follow-ups as leaving; reject."""
    authorize(ctx.principal, "admin.access")
    if not ctx.principal.has_step_up(ctx.now):
        raise DomainError(code=ErrorCode.STEP_UP_REQUIRED)
    settings = await active_settings(ctx.db)
    proposal = None
    async with _system() as db:
        req = await db.get(MemberRemovalRequest, request_id)
        member = await db.get(TeamMember, req.team_member_id) if req is not None else None
        team = await db.get(Team, member.team_id) if member is not None else None
        if req is None or member is None or team is None:
            raise NotFoundError
        project = await _lock_project(db, team.project_id)
        team = await _team_of(db, project.id, lock=True)
        member = await db.scalar(
            select(TeamMember).where(TeamMember.id == member.id).with_for_update()
        )
        req = await db.scalar(
            select(MemberRemovalRequest)
            .where(MemberRemovalRequest.id == request_id)
            .with_for_update()
        )
        if team is None:  # found or locked above; fail closed
            raise NotFoundError
        if member is None:  # found or locked above; fail closed
            raise NotFoundError
        if req is None:  # found or locked above; fail closed
            raise NotFoundError
        if req.status != RemovalStatus.PENDING:
            raise InvalidStateTransition(req.status.value, [], "This request was already decided.")
        req.status = RemovalStatus.APPROVED if approve else RemovalStatus.REJECTED
        req.decided_by, req.decided_at, req.decision_reason = ctx.uid, ctx.now, reason
        if approve:
            if member.status != MemberStatus.ACTIVE:
                raise InvalidStateTransition(member.status.value, [], "The member already left.")
            proposal = await _depart(
                db,
                project,
                team,
                member,
                status=MemberStatus.REMOVED,
                reason=reason,
                now=ctx.now,
                settings=settings,
            )
            await notify(
                db,
                member.developer_id,
                "MEMBER_REMOVED",
                title="Removed from the team",
                body=f"An admin removed you from “{project.title}”: {reason}",
                link="/dev",
            )
        await notify(
            db,
            project.client_id,
            "REMOVAL_DECIDED",
            title="Removal approved" if approve else "Removal not approved",
            body=f"An admin decided your removal request on “{project.title}”: {reason}",
            link=_link_team(project.id),
        )
        await write_audit(
            db,
            action="team.removal_" + ("approved" if approve else "rejected"),
            entity_type="member_removal_request",
            entity_id=req.id,
            actor_id=ctx.uid,
            actor_role="ADMIN",
        )
        await db.commit()
    repair_svc.queue(proposal)
    return ActionOut(status=req.status.value, message="Decided.")


# ------------------------------------------------------------------------------ cancel


async def cancel_team(db: AsyncSession, project: Project, now: datetime) -> list[uuid.UUID]:
    """D135: a TEAM_PENDING project was cancelled (free): team CANCELLED, open invitations
    closed, every reservation RELEASED, open repairs CANCELLED. Returns the members to tell.
    Called by `projects.cancel` in a SYSTEM session."""
    team = await _team_of(db, project.id, lock=True)
    if team is None:
        return []
    team.status = TeamStatus.CANCELLED
    members = await _members(db, team.id, lock=True)
    invs = await _invitations(db, [m.id for m in members])
    told = []
    for m in members:
        inv = invs.get(m.id)
        if inv is not None and inv.response is None:
            inv.response = InvitationResponse.EXPIRED
            inv.responded_at = now
        if m.status == MemberStatus.INVITED:
            m.status = MemberStatus.EXPIRED
        if m.status in (MemberStatus.INVITED, MemberStatus.ACTIVE, MemberStatus.EXPIRED):
            told.append(m.developer_id)
        m.is_lead = False
    await db.execute(
        update(AvailabilityReservation)
        .where(AvailabilityReservation.project_id == project.id)
        .values(status=ReservationStatus.RELEASED)
    )
    await db.execute(
        update(RepairProposal)
        .where(RepairProposal.team_id == team.id, RepairProposal.status.in_(OPEN_REPAIR))
        .values(status=RepairStatus.CANCELLED)
    )
    return told


# ------------------------------------------------------------------------ my views


async def my_invitations(ctx: Ctx) -> MyInvitationsOut:
    """The developer's invitations (pending, and answered in the last 30 days) and current
    memberships, for the dashboard banners and started-project cards (screen 9)."""
    authorize(ctx.principal, "invitation.respond")
    async with _system() as db:
        rows = (
            (
                await db.execute(
                    select(Invitation, TeamMember, Project)
                    .join(TeamMember, TeamMember.id == Invitation.team_member_id)
                    .join(Team, Team.id == TeamMember.team_id)
                    .join(Project, Project.id == Team.project_id)
                    .where(TeamMember.developer_id == ctx.uid, Invitation.sent_at.is_not(None))
                    .order_by(Invitation.sent_at.desc())
                    .limit(50)
                )
            )
            .tuples()
            .all()
        )
        slot_ids = {m.slot_id for _i, m, _p in rows}
        slots = (
            {
                s.id: s
                for s in (
                    await db.scalars(select(ProjectSlot).where(ProjectSlot.id.in_(slot_ids)))
                ).all()
            }
            if slot_ids
            else {}
        )
        names = await _skill_names(db, [s.skill_id for s in slots.values()])
        invitations = []
        for inv, m, p in rows:
            if inv.responded_at is not None and inv.responded_at < ctx.now - RECENT_ANSWERS:
                continue
            slot = slots.get(m.slot_id)
            invitations.append(
                MyInvitationOut(
                    id=inv.id,
                    member_id=m.id,
                    project_id=p.id,
                    project_title=p.title,
                    slot_label=(slot.label or names.get(slot.skill_id, "Role")) if slot else "Role",
                    price_paisa=m.price_paisa,
                    days_needed=m.days_needed,
                    state=invitation_state(inv, ctx.now),
                    sent_at=inv.sent_at,
                    expires_at=inv.expires_at,
                    responded_at=inv.responded_at,
                    is_replacement=inv.is_replacement,
                )
            )
        memberships = (
            (
                await db.execute(
                    select(TeamMember, Project)
                    .join(Team, Team.id == TeamMember.team_id)
                    .join(Project, Project.id == Team.project_id)
                    .where(
                        TeamMember.developer_id == ctx.uid,
                        TeamMember.status.in_([MemberStatus.INVITED, MemberStatus.ACTIVE]),
                        Team.status.in_([TeamStatus.PENDING, TeamStatus.ACTIVE]),
                    )
                    .order_by(Project.title)
                )
            )
            .tuples()
            .all()
        )
        return MyInvitationsOut(
            invitations=invitations,
            memberships=[
                MyMembershipOut(
                    member_id=m.id,
                    project_id=p.id,
                    project_title=p.title,
                    project_status=p.status.value,
                    status=m.status.value,
                    is_lead=m.is_lead and m.status == MemberStatus.ACTIVE,
                )
                for m, p in memberships
            ],
        )


async def client_teams(ctx: Ctx) -> list[ClientTeamCard]:
    """`/client/teams`: one card per project with a team (D110, D134)."""
    authorize(ctx.principal, "team.list")
    out = []
    async with _system() as db:
        rows = (
            (
                await db.execute(
                    select(Team, Project)
                    .join(Project, Project.id == Team.project_id)
                    .where(Project.client_id == ctx.uid)
                    .order_by(Team.created_at.desc())
                )
            )
            .tuples()
            .all()
        )
        for team, project in rows:
            members = await _members(db, team.id)
            invs = await _invitations(db, [m.id for m in members])
            slots = list(await projrepo.load_slots(db, project.id))
            lead = next((m for m in members if m.is_lead and m.status == MemberStatus.ACTIVE), None)
            lead_name = (await db.get(User, lead.developer_id)).display_name if lead else None
            attention = []
            live = project.status in LIVE_PROJECT and team.status != TeamStatus.CANCELLED
            if live:
                open_repair = await db.scalar(
                    select(func.count())
                    .select_from(RepairProposal)
                    .where(
                        RepairProposal.team_id == team.id, RepairProposal.status.in_(OPEN_REPAIR)
                    )
                )
                if open_repair:
                    attention.append("REPAIR_OPEN")
                soon = ctx.now + timedelta(hours=6)
                if any(
                    invitation_state(i, ctx.now) == "PENDING"
                    and i.expires_at is not None
                    and i.expires_at <= soon
                    for i in invs.values()
                ):
                    attention.append("INVITATION_EXPIRING")
                if await _fully_booked(db, project, members, invs, ctx.now):
                    attention.append("FULLY_BOOKED")
                if lead is None and not slots_filled(slots, members):
                    attention.append("CHOOSE_LEAD")
            out.append(
                ClientTeamCard(
                    project_id=project.id,
                    project_title=project.title,
                    project_status=project.status.value,
                    team_id=team.id,
                    team_status=team.status.value,
                    accepted=sum(m.status == MemberStatus.ACTIVE for m in members),
                    places=sum(s.count for s in slots),
                    lead_name=lead_name,
                    needs_attention=attention,
                )
            )
    return out
