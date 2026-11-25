"""Phase 8 gate check: team repair works on the demo data (§17 Phase 8, §9.9, D128).

On the stage-2 seed:

1. the seeded "Clinic appointment booking" is TEAM_PENDING with one declined invitation and a
   READY repair proposal with at least one ranked replacement (the seed built it through the real
   services);
2. scripted on the "Online ordering system" (FORMING, D116): a formation run with a fixed seed →
   the client confirms (invitations sent) → one member declines → the repair job ranks at least
   one replacement for that place, every candidate on the open slot and none already in the team.

It changes the seeded ordering project (its team is confirmed), so it runs after the Phase 7 check
and nothing later in the gate reads the seed. Exits non-zero on any difference.

    python scripts/repair_check.py
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.authz import Principal
from app.core.clock import get_clock
from app.core.config import get_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import Bid
from app.models.formation import (
    FormationRun,
    Invitation,
    MemberStatus,
    RepairProposal,
    RepairStatus,
    Team,
    TeamMember,
)
from app.models.identity import User
from app.models.projects import Project, ProjectStatus
from app.schemas.formation import FormationRunCreate
from app.schemas.team import DeclineIn
from app.services import formation as formation_svc
from app.services import formation_runner, platform_settings
from app.services import team as team_svc
from app.services.context import Ctx

SEED = 20261207
CLIENT_EMAIL = "rahim@devsync.local"
ORDERING = "Online ordering system"
REPAIR_DEMO = "Clinic appointment booking"


def fail(message: str) -> None:
    raise SystemExit(f"repair-check: {message}")


async def act(user_id: uuid.UUID, role: str, fn: Any) -> Any:
    """Call a service as that person, the way a signed-in request would."""
    principal = Principal(user_id=user_id, role=role, status="ACTIVE", session_id=uuid.uuid4(),
                          totp_verified=False, step_up_until=None)  # fmt: skip
    async with open_session(DbContext(user_id=user_id, role=role)) as db:
        ctx = Ctx(db=db, settings=get_settings(), principal=principal, now=get_clock().now())
        return await fn(ctx)


async def project_of(title: str) -> tuple[uuid.UUID, ProjectStatus, uuid.UUID]:
    """(id, status, client id) of the seeded project with that title."""
    async with open_session(DbContext.system(), job=True) as db:
        client = await db.scalar(select(User.id).where(User.email == CLIENT_EMAIL))
        row = (await db.execute(
            select(Project.id, Project.status, Project.client_id)
            .where(Project.client_id == client, Project.title == title)
        )).one_or_none()  # fmt: skip
    if row is None:
        fail(f"the seeded “{title}” is missing")
    assert row is not None  # noqa: S101 - narrowed by fail()
    return row[0], row[1], row[2]


async def latest_proposal(project_id: uuid.UUID) -> tuple[str, list[dict[str, Any]], uuid.UUID]:
    async with open_session(DbContext.system(), job=True) as db:
        row = await db.scalar(
            select(RepairProposal).join(Team, Team.id == RepairProposal.team_id)
            .where(Team.project_id == project_id).order_by(RepairProposal.created_at.desc())
            .limit(1)
        )  # fmt: skip
        if row is None:
            fail("no repair proposal was opened")
        assert row is not None  # noqa: S101 - narrowed by fail()
        return row.status.value, list(row.candidates or []), row.id


async def check_seeded() -> int:
    project_id, status, _client = await project_of(REPAIR_DEMO)
    if status != ProjectStatus.TEAM_PENDING:
        fail(f"“{REPAIR_DEMO}” is {status.value}, want TEAM_PENDING")
    async with open_session(DbContext.system(), job=True) as db:
        declined = await db.scalar(
            select(func.count()).select_from(TeamMember).join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == project_id, TeamMember.status == MemberStatus.DECLINED)
        )  # fmt: skip
    if declined != 1:
        fail(f"“{REPAIR_DEMO}” has {declined} declined invitations, want 1")
    state, candidates, _pid = await latest_proposal(project_id)
    if state != RepairStatus.READY.value or not candidates:
        fail(f"the seeded repair is {state} with {len(candidates)} candidates, want READY with ≥ 1")
    return len(candidates)


async def check_scripted() -> tuple[str, int]:
    project_id, status, client_id = await project_of(ORDERING)
    if status != ProjectStatus.FORMING:
        fail(f"“{ORDERING}” is {status.value}, want FORMING (D116)")
    async with open_session(DbContext.system(), job=True) as db:
        project = await db.get(Project, project_id)
        assert project is not None  # noqa: S101 - just read
        version, settings = await platform_settings.get_active(db)
        snapshot, params = await formation_svc.build_snapshot(
            db, get_clock().now().date(), project, settings, FormationRunCreate()
        )
        run = FormationRun(project_id=project_id, requested_by=client_id,
                           settings_version=version, seed=SEED, params=params,
                           candidate_snapshot=snapshot)  # fmt: skip
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()
    await formation_runner.execute_run(run_id)
    await act(client_id, "CLIENT", lambda ctx: formation_svc.confirm(ctx, run_id))
    async with open_session(DbContext.system(), job=True) as db:
        first = (await db.execute(
            select(Invitation.id, TeamMember.developer_id, TeamMember.slot_id, User.display_name)
            .join(TeamMember, TeamMember.id == Invitation.team_member_id)
            .join(Team, Team.id == TeamMember.team_id)
            .join(User, User.id == TeamMember.developer_id)
            .where(Team.project_id == project_id).order_by(User.display_name).limit(1)
        )).one_or_none()  # fmt: skip
        if first is None:
            fail("confirming the ordering team sent no invitations")
        assert first is not None  # noqa: S101 - narrowed by fail()
        inv_id, developer_id, slot_id, name = first
        members = set(
            (await db.scalars(
                select(TeamMember.developer_id).join(Team, Team.id == TeamMember.team_id)
                .where(Team.project_id == project_id)
            )).all()
        )  # fmt: skip
    await act(developer_id, "DEVELOPER", lambda ctx: team_svc.decline(
        ctx, inv_id, DeclineIn(reason="The gate's scripted decline.")))  # fmt: skip
    _state, _c, proposal_id = await latest_proposal(project_id)
    await formation_runner.execute_repair(proposal_id)
    state, candidates, _pid = await latest_proposal(project_id)
    if state != RepairStatus.READY.value or not candidates:
        fail(f"the scripted repair is {state} with {len(candidates)} candidates, want ≥ 1")
    async with open_session(DbContext.system(), job=True) as db:
        bids = (await db.execute(
            select(Bid.id, Bid.slot_id, Bid.developer_id)
            .where(Bid.id.in_([uuid.UUID(str(c["bid_id"])) for c in candidates]))
        )).all()  # fmt: skip
    for _bid, bid_slot, bid_dev in bids:
        if bid_slot != slot_id:
            fail("a replacement candidate bid on another slot")
        if bid_dev in members:
            fail("a replacement candidate is already in the team")
    if len(bids) != len(candidates):
        fail("a replacement candidate's bid doesn't exist")
    return name, len(candidates)


async def main() -> None:
    seeded = await check_seeded()
    name, found = await check_scripted()
    print(f"repair-check: seeded repair READY with {seeded} candidate(s); scripted decline by "
          f"{name} → {found} ranked replacement(s) on the same slot")  # fmt: skip


if __name__ == "__main__":
    asyncio.run(main())
