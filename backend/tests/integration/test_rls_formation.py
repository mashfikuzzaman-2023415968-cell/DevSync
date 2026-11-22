"""Row-level security and integrity of the team formation tables (spec §14.15, §14.13 row 7;
migration 0014). Queries run directly as the web role, bypassing the services:

- a run is visible to its project's client and admins only, written only by SYSTEM, and its
  inputs (params, seed, snapshot) can't change after insert — not even by SYSTEM; runs are never
  deleted;
- an explanation is visible to the bidder and admins only (sealed bids);
- a team and its members are visible to the project's client and the team's members; an
  invitation to its invitee and the client, not to other members;
- no web session can write any of them, even claiming SYSTEM.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import Environment
from app.db.context import DbContext
from app.db.session import open_session
from app.models.bidding import Bid, BidStatus
from app.models.formation import (
    BidExplanation,
    FormationRun,
    Invitation,
    MemberStatus,
    Team,
    TeamMember,
)
from tests.helpers import stack_available
from tests.integration.test_rls_bids import as_user, make_bidding_project, make_user

pytestmark = pytest.mark.integration
DbErrors = (ProgrammingError, DBAPIError)
NOW = datetime(2026, 11, 22, 6, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


async def _bid(dev: uuid.UUID, pid: uuid.UUID, sid: uuid.UUID) -> uuid.UUID:
    async with as_user(dev, "DEVELOPER") as db:
        bid = Bid(project_id=pid, developer_id=dev, slot_id=sid, price_paisa=500_000,
                  days_needed=10, hours_per_week_committed=20, status=BidStatus.ACTIVE)  # fmt: skip
        db.add(bid)
        await db.flush()
        bid_id = bid.id
        await db.commit()
    return bid_id


async def _world() -> dict[str, Any]:
    """A client's project with two bidders; a SYSTEM-written run, explanation, team, member and
    invitation for bidder A."""
    client, other_client = await make_user("CLIENT"), await make_user("CLIENT")
    dev_a, dev_b, outsider = [await make_user("DEVELOPER") for _ in range(3)]
    admin = await make_user("ADMIN")
    pid, sid = await make_bidding_project(client)
    bid_a, bid_b = await _bid(dev_a, pid, sid), await _bid(dev_b, pid, sid)
    async with open_session(DbContext.system(), job=True) as db:
        run = FormationRun(
            project_id=pid,
            requested_by=client,
            settings_version=5,
            seed=42,
            params={"preset": "balanced"},
            candidate_snapshot={"candidates": []},
        )
        db.add(run)
        await db.flush()
        db.add(BidExplanation(bid_id=bid_b, run_id=run.id, reasons={"codes": ["GAP"]}))
        team = Team(project_id=pid, run_id=run.id, confirmed_at=NOW)
        db.add(team)
        await db.flush()
        member_a = TeamMember(team_id=team.id, developer_id=dev_a, bid_id=bid_a, slot_id=sid,
                              price_paisa=500_000, days_needed=10)  # fmt: skip
        member_b = TeamMember(team_id=team.id, developer_id=dev_b, bid_id=bid_b, slot_id=sid,
                              price_paisa=500_000, days_needed=10)  # fmt: skip
        db.add_all([member_a, member_b])
        await db.flush()
        invitation = Invitation(team_member_id=member_a.id)
        db.add(invitation)
        await db.flush()
        ids = {"run": run.id, "team": team.id, "member_a": member_a.id, "invitation": invitation.id}
        await db.commit()
    return {"client": client, "other_client": other_client, "dev_a": dev_a, "dev_b": dev_b,
            "outsider": outsider, "admin": admin, "pid": pid, "bid_b": bid_b, **ids}  # fmt: skip


async def _sees(uid: uuid.UUID, role: str, model: Any, row_id: uuid.UUID) -> bool:
    async with as_user(uid, role) as db:
        return await db.scalar(select(model.id).where(model.id == row_id)) is not None


async def test_runs_are_visible_to_the_projects_client_and_admins_only() -> None:
    w = await _world()
    assert await _sees(w["client"], "CLIENT", FormationRun, w["run"])
    assert await _sees(w["admin"], "ADMIN", FormationRun, w["run"])
    assert not await _sees(w["other_client"], "CLIENT", FormationRun, w["run"])
    assert not await _sees(w["dev_a"], "DEVELOPER", FormationRun, w["run"])


async def test_explanations_are_sealed_to_the_bidder() -> None:
    w = await _world()
    rows = select(BidExplanation.id).where(BidExplanation.bid_id == w["bid_b"])
    for uid, role, visible in (
        (w["dev_b"], "DEVELOPER", True), (w["admin"], "ADMIN", True),
        (w["dev_a"], "DEVELOPER", False), (w["client"], "CLIENT", False),
        (w["outsider"], "DEVELOPER", False),
    ):  # fmt: skip
        async with as_user(uid, role) as db:
            assert (await db.scalar(rows) is not None) is visible, (role, visible)


async def test_team_and_members_visible_to_client_and_members_only() -> None:
    w = await _world()
    for uid, role in (
        (w["client"], "CLIENT"),
        (w["dev_a"], "DEVELOPER"),
        (w["dev_b"], "DEVELOPER"),
    ):
        assert await _sees(uid, role, Team, w["team"])
        assert await _sees(uid, role, TeamMember, w["member_a"])
    assert not await _sees(w["outsider"], "DEVELOPER", Team, w["team"])
    assert not await _sees(w["outsider"], "DEVELOPER", TeamMember, w["member_a"])
    assert not await _sees(w["other_client"], "CLIENT", Team, w["team"])


async def test_an_invitation_is_visible_to_its_invitee_and_the_client_only() -> None:
    w = await _world()
    assert await _sees(w["dev_a"], "DEVELOPER", Invitation, w["invitation"])
    assert await _sees(w["client"], "CLIENT", Invitation, w["invitation"])
    assert not await _sees(w["dev_b"], "DEVELOPER", Invitation, w["invitation"])  # teammate
    assert not await _sees(w["outsider"], "DEVELOPER", Invitation, w["invitation"])


async def test_web_sessions_cannot_write_even_claiming_system() -> None:
    w = await _world()
    for ctx in (DbContext(user_id=w["client"], role="CLIENT"),
                DbContext(user_id=w["client"], role="SYSTEM")):  # fmt: skip
        async with open_session(ctx) as db:
            db.add(FormationRun(project_id=w["pid"], requested_by=w["client"], settings_version=5,
                                seed=1, params={}, candidate_snapshot={}))  # fmt: skip
            with pytest.raises(DbErrors):
                await db.flush()
        async with open_session(ctx) as db:
            result = await db.execute(
                update(TeamMember).where(TeamMember.id == w["member_a"]).values(is_lead=True)
            )
            assert result.rowcount == 0  # RLS hides the row from the UPDATE


async def test_a_runs_inputs_are_immutable_even_for_system() -> None:
    w = await _world()
    changes: list[dict[str, Any]] = [
        {"params": {"preset": "budget"}},
        {"seed": 7},
        {"candidate_snapshot": {"candidates": ["forged"]}},
        {"settings_version": 9},
    ]
    for change in changes:
        async with open_session(DbContext.system(), job=True) as db:
            with pytest.raises(DbErrors):
                await db.execute(
                    update(FormationRun).where(FormationRun.id == w["run"]).values(**change)
                )
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(FormationRun).where(FormationRun.id == w["run"]).values(result={"ok": True})
        )
        await db.commit()  # the result side is writable by SYSTEM


async def test_runs_are_never_deleted() -> None:
    w = await _world()
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(delete(FormationRun).where(FormationRun.id == w["run"]))


async def test_one_active_lead_per_team_and_invitation_consistency() -> None:
    """Two active leads in one team break the partial unique index (§7.9); an invitation marked
    sent without an expiry breaks `expiry_iff_sent` (D108)."""
    w = await _world()
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(
                update(TeamMember)
                .where(TeamMember.team_id == w["team"])
                .values(status=MemberStatus.ACTIVE, is_lead=True)
            )
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(
                update(Invitation).where(Invitation.id == w["invitation"]).values(sent_at=NOW)
            )
