"""Row-level security of the Phase 8 team tables and the changed team visibility (spec §14.15,
§14.13 row 8; migration 0015; DECISIONS D128, D130). Queries run directly as the web role:

- a developer who declined (or expired, left, was removed) no longer sees the team or the other
  members, only their own member row and invitation (D130);
- lead-change requests: the team's client and its ACTIVE members (not INVITED ones, not
  outsiders), admins;
- repair proposals: the team's client and admins only — never a developer (sealed bids); their
  inputs are immutable even for SYSTEM and they are never deleted (D128);
- removal requests: the team's client and admins only;
- no web session can write any of them, even claiming SYSTEM.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import Environment
from app.db.context import DbContext
from app.db.session import open_session
from app.models.formation import (
    Invitation,
    LeadChangeRequest,
    MemberRemovalRequest,
    MemberStatus,
    RemovalBasis,
    RepairProposal,
    Team,
    TeamMember,
)
from tests.helpers import stack_available
from tests.integration.test_rls_bids import make_user
from tests.integration.test_rls_formation import _sees, _world

pytestmark = pytest.mark.integration
DbErrors = (ProgrammingError, DBAPIError)
REASON = "The lead hasn't answered questions for a week."


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


async def _status(member_id: uuid.UUID, status: MemberStatus) -> None:
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(TeamMember).where(TeamMember.id == member_id).values(status=status))
        await db.commit()


async def _lifecycle(w: dict[str, Any]) -> dict[str, uuid.UUID]:
    """dev_a ACTIVE with a lead-change request; dev_b DECLINED with a repair proposal for their
    place and a removal request against dev_a."""
    member_b = await _member_of(w["dev_b"], w["team"])
    await _status(w["member_a"], MemberStatus.ACTIVE)
    await _status(member_b, MemberStatus.DECLINED)
    async with open_session(DbContext.system(), job=True) as db:
        lcr = LeadChangeRequest(team_id=w["team"], requested_by=w["dev_a"], reason=REASON)
        repair = RepairProposal(team_id=w["team"], departed_member_id=member_b,
                                settings_version=5, seed=7, params={"k": 1},
                                candidate_snapshot={"candidates": []})  # fmt: skip
        removal = MemberRemovalRequest(team_member_id=w["member_a"], requested_by=w["client"],
                                       reason=REASON, basis=RemovalBasis.INACTIVITY)  # fmt: skip
        db.add_all([lcr, repair, removal])
        await db.flush()
        ids = {"lcr": lcr.id, "repair": repair.id, "removal": removal.id, "member_b": member_b}
        await db.commit()
    return ids


async def _member_of(dev: uuid.UUID, team: uuid.UUID) -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        found = await db.scalar(
            select(TeamMember.id).where(TeamMember.team_id == team, TeamMember.developer_id == dev)
        )
    assert found is not None
    return found


async def test_a_developer_who_declined_sees_only_their_own_row() -> None:
    w = await _world()
    ids = await _lifecycle(w)
    assert not await _sees(w["dev_b"], "DEVELOPER", Team, w["team"])
    assert not await _sees(w["dev_b"], "DEVELOPER", TeamMember, w["member_a"])
    assert await _sees(w["dev_b"], "DEVELOPER", TeamMember, ids["member_b"])  # own row
    # Still visible to the active member and the client.
    assert await _sees(w["dev_a"], "DEVELOPER", Team, w["team"])
    assert await _sees(w["client"], "CLIENT", TeamMember, ids["member_b"])


@pytest.mark.parametrize("status", [MemberStatus.EXPIRED, MemberStatus.LEFT, MemberStatus.REMOVED])
async def test_former_members_lose_sight_of_the_team(status: MemberStatus) -> None:
    w = await _world()
    await _status(w["member_a"], status)
    assert not await _sees(w["dev_a"], "DEVELOPER", Team, w["team"])
    assert await _sees(w["dev_a"], "DEVELOPER", TeamMember, w["member_a"])
    assert await _sees(w["dev_a"], "DEVELOPER", Invitation, w["invitation"])  # own invitation


async def test_lead_change_requests_for_client_and_active_members() -> None:
    w = await _world()
    ids = await _lifecycle(w)
    assert await _sees(w["client"], "CLIENT", LeadChangeRequest, ids["lcr"])
    assert await _sees(w["dev_a"], "DEVELOPER", LeadChangeRequest, ids["lcr"])  # ACTIVE
    assert await _sees(w["admin"], "ADMIN", LeadChangeRequest, ids["lcr"])
    assert not await _sees(w["dev_b"], "DEVELOPER", LeadChangeRequest, ids["lcr"])  # declined
    assert not await _sees(w["outsider"], "DEVELOPER", LeadChangeRequest, ids["lcr"])
    assert not await _sees(w["other_client"], "CLIENT", LeadChangeRequest, ids["lcr"])


async def test_an_invited_member_does_not_see_lead_change_requests() -> None:
    w = await _world()
    ids = await _lifecycle(w)
    await _status(w["member_a"], MemberStatus.INVITED)
    assert not await _sees(w["dev_a"], "DEVELOPER", LeadChangeRequest, ids["lcr"])


async def test_repair_proposals_and_removals_are_for_the_client_and_admins() -> None:
    w = await _world()
    ids = await _lifecycle(w)
    for model, key in ((RepairProposal, "repair"), (MemberRemovalRequest, "removal")):
        assert await _sees(w["client"], "CLIENT", model, ids[key])
        assert await _sees(w["admin"], "ADMIN", model, ids[key])
        assert not await _sees(w["dev_a"], "DEVELOPER", model, ids[key])  # active member
        assert not await _sees(w["dev_b"], "DEVELOPER", model, ids[key])
        assert not await _sees(w["other_client"], "CLIENT", model, ids[key])


async def test_web_sessions_cannot_write_even_claiming_system() -> None:
    w = await _world()
    ids = await _lifecycle(w)
    for ctx in (DbContext(user_id=w["dev_a"], role="DEVELOPER"),
                DbContext(user_id=w["client"], role="SYSTEM")):  # fmt: skip
        async with open_session(ctx) as db:
            db.add(
                LeadChangeRequest(team_id=w["team"], requested_by=w["dev_a"], reason=REASON + "!")
            )
            with pytest.raises(DbErrors):
                await db.flush()
        for model, key in ((RepairProposal, "repair"), (MemberRemovalRequest, "removal"),
                           (LeadChangeRequest, "lcr")):  # fmt: skip
            async with open_session(ctx) as db:
                result = await db.execute(
                    update(model).where(model.id == ids[key]).values(updated_at=model.updated_at)
                )
                assert result.rowcount == 0  # RLS hides the row from the UPDATE


async def test_repair_inputs_are_immutable_and_never_deleted() -> None:
    w = await _world()
    ids = await _lifecycle(w)
    changes: list[dict[str, Any]] = [
        {"seed": 8},
        {"params": {"k": 2}},
        {"candidate_snapshot": {"candidates": ["forged"]}},
        {"settings_version": 9},
        {"departed_member_id": w["member_a"]},
    ]
    for change in changes:
        async with open_session(DbContext.system(), job=True) as db:
            with pytest.raises(DbErrors):
                await db.execute(
                    update(RepairProposal)
                    .where(RepairProposal.id == ids["repair"])
                    .values(**change)
                )
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(RepairProposal).where(RepairProposal.id == ids["repair"])
                         .values(candidates=[], reasons=["NO_BIDS_FOR_SLOT"]))  # fmt: skip
        await db.commit()  # the result side is writable by SYSTEM
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(delete(RepairProposal).where(RepairProposal.id == ids["repair"]))


async def test_one_open_proposal_and_one_pending_request_per_member() -> None:
    w = await _world()
    ids = await _lifecycle(w)
    async with open_session(DbContext.system(), job=True) as db:
        duplicate = RepairProposal(
            team_id=w["team"],
            departed_member_id=ids["member_b"],
            settings_version=5,
            seed=1,
            params={},
            candidate_snapshot={},
        )
        db.add(duplicate)
        with pytest.raises(DbErrors):
            await db.flush()
    async with open_session(DbContext.system(), job=True) as db:
        db.add(LeadChangeRequest(team_id=w["team"], requested_by=w["dev_a"], reason=REASON))
        with pytest.raises(DbErrors):
            await db.flush()
    other = await make_user("DEVELOPER")
    async with open_session(DbContext.system(), job=True) as db:
        db.add(LeadChangeRequest(team_id=w["team"], requested_by=other, reason="too short"))
        with pytest.raises(DbErrors):  # reasons 20–500 characters (D132)
            await db.flush()
