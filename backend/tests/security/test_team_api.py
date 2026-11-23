"""Team lifecycle over HTTP (spec §1.6, §8, §9.9, §9.17, §10.2 Team, §14.13 row 8; D118–D138).

The Phase 7 world: a FORMING project with one slot for two developers and five bidders (one a
newcomer). A run with the dial at 1 forms a team of two and confirm sends both invitations
(D123). Jobs run here directly (the test stack has no worker). FR-INV-1..5 are in the names.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import team as team_svc
from tests.helpers import Api, SeededUser
from tests.helpers import wait_for_next_totp_window as next_totp
from tests.security.formation_world import BASE, UNKNOWN, _code, _sql
from tests.security.test_formation_api import _run

pytestmark = [pytest.mark.security, pytest.mark.api]
REASON = "I can't keep working on this project any more."  # 46 characters


def _reset(api: Api) -> None:
    assert api.get(f"{BASE}/__test__/ratelimits/reset").status_code == 204


def confirmed(api: Api, world: dict[str, Any]) -> dict[str, Any]:
    """Run (dial 1) and confirm; returns the run with its team bid ids."""
    run = _run(api, world["pid"], min_newcomers=1)
    r = api.post(f"{BASE}/formation-runs/{run['id']}/confirm")
    assert r.status_code == 200, r.text
    run["team_bids"] = [m["bid_id"] for m in run["result"]["team"]]
    return run


def bidder_of(world: dict[str, Any], bid_id: str) -> SeededUser:
    return next(u for u, b in world["bidders"] if b == bid_id)


def as_dev(api: Api, user: SeededUser) -> None:
    _reset(api)
    assert api.login(user).status_code == 200


def my_invitation(api: Api, project_id: str) -> dict[str, Any]:
    r = api.get(f"{BASE}/me/invitations")
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["invitations"] if i["project_id"] == project_id)


def accept_all(api2: Api, world: dict[str, Any], run: dict[str, Any]) -> None:
    for bid in run["team_bids"]:
        as_dev(api2, bidder_of(world, bid))
        inv = my_invitation(api2, world["pid"])
        r = api2.post(f"{BASE}/invitations/{inv['id']}/accept")
        assert r.status_code == 200, r.text


def team(api: Api, pid: str) -> dict[str, Any]:
    r = api.get(f"{BASE}/projects/{pid}/team")
    assert r.status_code == 200, r.text
    return dict(r.json())


# ------------------------------------------------------------------------------ invitations


def test_FR_INV_1_confirm_sends_invitations_with_a_48h_clock(  # noqa: N802
    api: Api, api2: Api, world: dict[str, Any]
) -> None:
    run = confirmed(api, world)
    as_dev(api2, bidder_of(world, run["team_bids"][0]))
    inv = my_invitation(api2, world["pid"])
    assert inv["state"] == "PENDING"
    sent, expires = (datetime.fromisoformat(inv[k]) for k in ("sent_at", "expires_at"))
    assert expires - sent == timedelta(hours=48)  # invite.expiry_hours
    notes = api2.get(f"{BASE}/notifications").json()["items"]
    assert any(n["type"] == "INVITATION_SELECTED" and n["link_path"] == "/dev" for n in notes)


def test_FR_INV_2_answer_rules(  # noqa: N802
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = confirmed(api, world)
    first, second = (bidder_of(world, b) for b in run["team_bids"])
    as_dev(api2, first)
    inv = my_invitation(api2, world["pid"])
    # Someone else's invitation is 404; an unknown one too.
    as_dev(api2, second)
    assert api2.post(f"{BASE}/invitations/{inv['id']}/accept").status_code == 404
    assert api2.post(f"{BASE}/invitations/{UNKNOWN}/accept").status_code == 404
    as_dev(api2, first)
    assert api2.post(f"{BASE}/invitations/{inv['id']}/accept").status_code == 200
    again = api2.post(f"{BASE}/invitations/{inv['id']}/accept")
    assert (again.status_code, _code(again)) == (409, "INVALID_STATE")
    late = api2.post(f"{BASE}/invitations/{inv['id']}/decline", json={})
    assert late.status_code == 409  # decline after accept
    # The second invitation: expired one second ago → refused, and the job expires it.
    as_dev(api2, second)
    other = my_invitation(api2, world["pid"])
    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    assert (
        api.post(
            f"{BASE}/__test__/invitations/{other['id']}/expiry", json={"expires_at": past}
        ).status_code
        == 204
    )
    r = api2.post(f"{BASE}/invitations/{other['id']}/accept")
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")
    counts = api.post(f"{BASE}/__test__/lifecycle/expire").json()
    assert counts["invitations_expired"] >= 1
    assert api.post(f"{BASE}/__test__/lifecycle/expire").json()["invitations_expired"] == 0
    assert my_invitation(api2, world["pid"])["state"] == "EXPIRED"
    statuses = dict(
        _sql(
            migration_url,
            "SELECT b.id::text, b.status::text FROM bids b WHERE b.project_id = :pid",
            pid=world["pid"],
        )
    )
    assert statuses[run["team_bids"][1]] == "EXPIRED"
    assert statuses[run["team_bids"][0]] == "ACCEPTED"


def test_an_unsent_invitation_cannot_be_answered_and_is_sent_by_the_job(
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = confirmed(api, world)
    _sql(
        migration_url,
        "UPDATE invitations i SET sent_at = NULL, expires_at = NULL FROM "
        "team_members m JOIN teams t ON t.id = m.team_id WHERE i.team_member_id = m.id "
        "AND t.project_id = :pid",
        pid=world["pid"],
    )
    as_dev(api2, bidder_of(world, run["team_bids"][0]))
    rows = api2.get(f"{BASE}/me/invitations").json()["invitations"]
    assert all(i["project_id"] != world["pid"] for i in rows)  # unsent: not on the dashboard
    inv_id = _sql(
        migration_url,
        "SELECT i.id::text FROM invitations i JOIN team_members m ON "
        "m.id = i.team_member_id WHERE m.bid_id = :b",
        b=run["team_bids"][0],
    )[0][0]
    r = api2.post(f"{BASE}/invitations/{inv_id}/accept")
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")
    counts = api.post(f"{BASE}/__test__/lifecycle/expire").json()
    assert counts["invitations_sent"] == 2 and counts["invitations_expired"] == 0  # noqa: PT018
    assert my_invitation(api2, world["pid"])["state"] == "PENDING"


def test_FR_INV_3_accept_rechecks_free_hours_at_the_boundary(  # noqa: N802
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    """D124: committed elsewhere 10 h + this 20 h = 30 h fits a 30 h profile, not a 29 h one."""
    run = confirmed(api, world)
    dev = bidder_of(world, run["team_bids"][0])
    other = _sql(
        migration_url,
        "SELECT id::text FROM projects WHERE status <> 'DRAFT' AND id <> :pid LIMIT 1",
        pid=world["pid"],
    )
    assert other, "needs another project for a confirmed reservation"
    _sql(
        migration_url,
        "INSERT INTO availability_reservations (id, developer_id, project_id, "
        "hours_per_week, from_date, to_date, status) VALUES (gen_random_uuid(), :d, :p, 10, "
        "current_date - 30, current_date + 400, 'CONFIRMED')",
        d=dev.user_id,
        p=other[0][0],
    )
    hours = _sql(
        migration_url,
        "SELECT hours_per_week_committed FROM bids WHERE id = :b",
        b=run["team_bids"][0],
    )[0][0]
    as_dev(api2, dev)
    # The developer sets their weekly hours in their profile (one short of what's needed).
    r = api2.patch(f"{BASE}/me/developer-profile", json={"hours_per_week": 10 + hours - 1})
    assert r.status_code == 200, r.text
    inv = my_invitation(api2, world["pid"])
    r = api2.post(f"{BASE}/invitations/{inv['id']}/accept")
    assert (r.status_code, _code(r)) == (409, "UNAVAILABLE")
    assert r.json()["error"]["free_hours"] == hours - 1
    client_view = team(api, world["pid"])
    me = next(m for m in client_view["members"] if m["developer_id"] == dev.user_id)
    assert me["fully_booked"] is True
    r = api2.patch(f"{BASE}/me/developer-profile", json={"hours_per_week": 10 + hours})
    assert r.status_code == 200, r.text
    assert api2.post(f"{BASE}/invitations/{inv['id']}/accept").status_code == 200
    res = _sql(
        migration_url,
        "SELECT status::text FROM availability_reservations WHERE "
        "developer_id = :d AND project_id = :p",
        d=dev.user_id,
        p=world["pid"],
    )
    assert [r[0] for r in res] == ["CONFIRMED"]


# -------------------------------------------------------------------- decline and repair


def test_FR_INV_4_decline_opens_a_repair_the_client_can_follow(  # noqa: N802
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = confirmed(api, world)
    keep, leave_bid = run["team_bids"]
    as_dev(api2, bidder_of(world, keep))
    assert (
        api2.post(
            f"{BASE}/invitations/{my_invitation(api2, world['pid'])['id']}/accept"
        ).status_code
        == 200
    )
    as_dev(api2, bidder_of(world, leave_bid))
    inv = my_invitation(api2, world["pid"])
    assert (
        api2.post(
            f"{BASE}/invitations/{inv['id']}/decline", json={"reason": "Booked elsewhere"}
        ).status_code
        == 200
    )
    # The decliner no longer sees the team (D130).
    assert api2.get(f"{BASE}/projects/{world['pid']}/team").status_code == 404
    assert (
        api2.get(f"{BASE}/projects/{world['pid']}/repair").status_code == 403
    )  # developers: never
    rep = api.get(f"{BASE}/projects/{world['pid']}/repair").json()
    assert rep["status"] == "COMPUTING"
    job = rep["job_id"]
    assert api.get(f"{BASE}/jobs/{job}").status_code == 200  # requested_by = the client (D128)
    assert api2.get(f"{BASE}/jobs/{job}").status_code == 404
    assert _job_status(api, rep["id"]) == "READY"
    rep = api.get(f"{BASE}/projects/{world['pid']}/repair").json()
    assert rep["status"] == "READY"
    cands = rep["candidates"]
    assert 1 <= len(cands) <= 3
    assert [c["fitness"] for c in cands] == sorted((c["fitness"] for c in cands), reverse=True)
    assert all(c["bid_id"] not in run["team_bids"] for c in cands)
    assert "budget_delta_paisa" in cands[0]["impact"]
    # Choosing one invites the replacement and moves the bid NOT_SELECTED → SELECTED (D128).
    pick = cands[0]["bid_id"]
    bad = api.post(f"{BASE}/repair-proposals/{rep['id']}/choose", json={"bid_id": UNKNOWN})
    assert bad.status_code == 422
    r = api.post(f"{BASE}/repair-proposals/{rep['id']}/choose", json={"bid_id": pick})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CHOSEN"
    again = api.post(f"{BASE}/repair-proposals/{rep['id']}/choose", json={"bid_id": pick})
    assert again.status_code == 409
    status = _sql(migration_url, "SELECT status::text FROM bids WHERE id = :b", b=pick)[0][0]
    assert status == "SELECTED"
    replacement = bidder_of(world, pick)
    as_dev(api2, replacement)
    inv = my_invitation(api2, world["pid"])
    assert inv["is_replacement"] is True
    assert api2.post(f"{BASE}/invitations/{inv['id']}/accept").status_code == 200
    view = team(api, world["pid"])
    active = [m for m in view["members"] if m["status"] == "ACTIVE"]
    assert len(active) == 2
    assert view["recommendation"] is not None  # every place accepted → a lead is recommended


def _job_status(api: Api, proposal_id: str) -> str:
    r = api.post(f"{BASE}/__test__/repair-proposals/{proposal_id}/execute")
    assert r.status_code == 200, r.text
    return str(r.json()["status"])


# ------------------------------------------------------------------------- lead and start


def test_FR_INV_5_lead_choice_decline_and_start(  # noqa: N802
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = confirmed(api, world)
    view = team(api, world["pid"])
    assert view["can_start"] is False
    assert view["recommendation"] is None  # not every place accepted yet
    early = api.post(f"{BASE}/projects/{world['pid']}/start")
    assert (early.status_code, _code(early)) == (409, "INVALID_STATE")
    accept_all(api2, world, run)
    view = team(api, world["pid"])
    rec = view["recommendation"]
    assert rec is not None
    assert rec["reason"].startswith("Highest teamwork capacity")
    assert view["start_blockers"] == ["Choose a team lead."]
    other = next(m for m in view["members"] if m["id"] != rec["member_id"])
    version = view["project_version"]
    # The client may pick a non-recommended accepted member.
    stale = api.post(
        f"{BASE}/projects/{world['pid']}/team/lead",
        json={"member_id": other["id"]},
        headers={"If-Match": str(version - 1)},
    )
    assert (stale.status_code, _code(stale)) == (409, "VERSION_CONFLICT")
    assert (
        api.post(
            f"{BASE}/projects/{world['pid']}/team/lead", json={"member_id": other["id"]}
        ).status_code
        == 200
    )
    # That member declines the role: the next by the ranking is recommended (skipping them).
    as_dev(
        api2,
        bidder_of(
            world, next(b for b in run["team_bids"] if _member_bid(migration_url, other["id"]) == b)
        ),
    )
    assert api2.post(f"{BASE}/projects/{world['pid']}/team/lead/decline").status_code == 200
    again = api2.post(f"{BASE}/projects/{world['pid']}/team/lead/decline")
    assert again.status_code == 409  # not the lead any more
    view = team(api, world["pid"])
    assert view["lead_member_id"] is None
    assert view["recommendation"]["member_id"] != other["id"]
    refused = api.post(f"{BASE}/projects/{world['pid']}/team/lead", json={"member_id": other["id"]})
    assert refused.status_code == 409  # declined the role
    nxt = view["recommendation"]["member_id"]
    assert (
        api.post(f"{BASE}/projects/{world['pid']}/team/lead", json={"member_id": nxt}).status_code
        == 200
    )
    # Start: D118/D119.
    r = api.post(f"{BASE}/projects/{world['pid']}/start")
    assert r.status_code == 200, r.text
    project = api.get(f"{BASE}/projects/{world['pid']}").json()
    assert project["status"] == "IN_PROGRESS"
    assert project["start_date"] is not None
    ms = _sql(
        migration_url,
        "SELECT m.name, m.status::text, m.actual_start IS NOT NULL FROM "
        "milestones m WHERE m.project_id = :p ORDER BY m.position",
        p=world["pid"],
    )
    # D118: "Design" has no predecessors and starts; "Build" (after Design) stays PLANNED.
    assert [tuple(r) for r in ms] == [("Design", "ACTIVE", True), ("Build", "PLANNED", False)]
    assert (
        _sql(
            migration_url,
            "SELECT bool_and(approved_by_lead) FROM plan_baselines WHERE project_id = :p",
            p=world["pid"],
        )[0][0]
        is True
    )
    res = _sql(
        migration_url,
        "SELECT DISTINCT status::text FROM availability_reservations WHERE project_id = :p",
        p=world["pid"],
    )
    assert [r[0] for r in res] == ["CONFIRMED"]
    assert api.post(f"{BASE}/projects/{world['pid']}/start").status_code == 409
    cancel = api.post(f"{BASE}/projects/{world['pid']}/cancel", json={"reason": "No longer needed"})
    assert cancel.status_code == 409  # IN_PROGRESS isn't cancellable yet (D135)
    # After start the lead can change, with a reason.
    plain = api.post(f"{BASE}/projects/{world['pid']}/team/lead", json={"member_id": other["id"]})
    assert plain.status_code in (409, 422)
    members = team(api, world["pid"])["members"]
    target = next(m for m in members if not m["is_lead"] and m["status"] == "ACTIVE")
    if target["lead_declined"]:
        return
    r = api.post(
        f"{BASE}/projects/{world['pid']}/team/lead",
        json={"member_id": target["id"], "reason": "Better placed to lead the release."},
    )
    assert r.status_code == 200, r.text


def _member_bid(url: str, member_id: str) -> str:
    return str(_sql(url, "SELECT bid_id::text FROM team_members WHERE id = :m", m=member_id)[0][0])


def test_lead_change_requests_and_role_shaped_views(
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = confirmed(api, world)
    accept_all(api2, world, run)
    view = team(api, world["pid"])
    lead_id = view["recommendation"]["member_id"]
    api.post(f"{BASE}/projects/{world['pid']}/team/lead", json={"member_id": lead_id})
    member_bid = next(b for b in run["team_bids"] if _member_bid(migration_url, lead_id) != b)
    as_dev(api2, bidder_of(world, member_bid))
    mine = team(api2, world["pid"])
    assert mine["view"] == "member"
    text = json.dumps(mine)
    assert "price_paisa" not in text and "days_needed" not in text  # noqa: PT018 - sealed (D130)
    short = api2.post(
        f"{BASE}/projects/{world['pid']}/lead-change-requests", json={"reason": "x" * 19}
    )
    assert short.status_code == 422
    long = api2.post(
        f"{BASE}/projects/{world['pid']}/lead-change-requests", json={"reason": "x" * 501}
    )
    assert long.status_code == 422
    nul = api2.post(
        f"{BASE}/projects/{world['pid']}/lead-change-requests",
        json={"reason": "The lead is unreachable\x00 lately."},
    )
    assert nul.status_code == 422
    r = api2.post(f"{BASE}/projects/{world['pid']}/lead-change-requests", json={"reason": "x" * 20})
    assert r.status_code == 201, r.text
    req = r.json()
    dup = api2.post(
        f"{BASE}/projects/{world['pid']}/lead-change-requests", json={"reason": "y" * 30}
    )
    assert (dup.status_code, _code(dup)) == (409, "LIMIT_REACHED")
    # The lead can't request a change (they decline the role instead).
    as_dev(api2, bidder_of(world, _member_bid(migration_url, lead_id)))
    assert (
        api2.post(
            f"{BASE}/projects/{world['pid']}/lead-change-requests", json={"reason": "z" * 30}
        ).status_code
        == 409
    )
    assert api2.post(f"{BASE}/lead-change-requests/{req['id']}/approve").status_code == 403
    # The client approves: the lead is cleared and excluded from the next recommendation.
    assert api.post(f"{BASE}/lead-change-requests/{req['id']}/approve").status_code == 200
    view = team(api, world["pid"])
    assert view["lead_member_id"] is None
    assert view["recommendation"]["member_id"] != lead_id
    assert (
        api.post(
            f"{BASE}/lead-change-requests/{req['id']}/reject",
            json={"reason": "Already decided earlier."},
        ).status_code
        == 409
    )


def test_mass_assignment_is_refused(api: Api, api2: Api, world: dict[str, Any]) -> None:
    run = confirmed(api, world)
    as_dev(api2, bidder_of(world, run["team_bids"][0]))
    inv = my_invitation(api2, world["pid"])
    for body in (
        {"status": "ACCEPTED"},
        {"expires_at": "2030-01-01T00:00:00Z"},
        {"is_replacement": True},
        {"team_id": UNKNOWN},
    ):
        assert api2.post(f"{BASE}/invitations/{inv['id']}/decline", json=body).status_code == 422
    for body in ({"member_id": UNKNOWN, "is_lead": True}, {"member_id": UNKNOWN, "price_paisa": 1}):
        assert api.post(f"{BASE}/projects/{world['pid']}/team/lead", json=body).status_code == 422
    assert (
        api.post(
            f"{BASE}/projects/{world['pid']}/budget", json={"budget_paisa": 10**11}
        ).status_code
        == 422
    )


# ------------------------------------------------------------------- leave, removal, cancel


def test_leave_removal_and_cancel(
    api: Api,
    api2: Api,
    api3: Api,
    *,
    world: dict[str, Any],
    migration_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = confirmed(api, world)
    accept_all(api2, world, run)
    view = team(api, world["pid"])
    lead_id = view["recommendation"]["member_id"]
    api.post(f"{BASE}/projects/{world['pid']}/team/lead", json={"member_id": lead_id})
    assert api.post(f"{BASE}/projects/{world['pid']}/start").status_code == 200
    members = team(api, world["pid"])["members"]
    other = next(m for m in members if m["id"] != lead_id)
    # Removal needs an activity signal (Phase 9): refused now.
    r = api.post(
        f"{BASE}/team-members/{other['id']}/removal-requests",
        json={"reason": "No updates for twelve days.", "basis": "INACTIVITY"},
    )
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")
    assert "Phase 9" in r.json()["error"]["message"]

    async def twelve_days(_db: object, _m: object) -> int:
        return 12

    monkeypatch.setattr(team_svc, "member_inactive_days", twelve_days)
    r = api.post(
        f"{BASE}/team-members/{other['id']}/removal-requests",
        json={"reason": "No updates for twelve days.", "basis": "INACTIVITY"},
    )
    assert r.status_code == 201, r.text
    removal = r.json()
    as_dev(api2, bidder_of(world, _member_bid(migration_url, other["id"])))
    assert api2.get(f"{BASE}/admin/removal-requests").status_code == 404  # non-admin
    admin = api3.sign_in_as("ADMIN")
    path = f"{BASE}/admin/removal-requests/{removal['id']}/approve"
    body = {"reason": "Confirmed: no activity for twelve days."}
    first = api3.post(path, json=body)
    assert (first.status_code, _code(first)) == (403, "STEP_UP_REQUIRED")
    assert (
        api3.post(
            f"{BASE}/auth/step-up", json={"code": next_totp(admin.totp_secret or "")}
        ).status_code
        == 204
    )
    assert api3.post(path, json=body).status_code == 200
    gone = _sql(migration_url, "SELECT status::text FROM team_members WHERE id = :m", m=other["id"])
    assert gone[0][0] == "REMOVED"
    assert api.get(f"{BASE}/projects/{world['pid']}/repair").json()["status"] == "COMPUTING"
    # The lead leaves: reason bounds, then a recommendation is needed again (§1.6 rule 5).
    as_dev(api2, bidder_of(world, _member_bid(migration_url, lead_id)))
    for reason in ("x" * 19, "x" * 501):
        assert (
            api2.post(f"{BASE}/team-members/{lead_id}/leave", json={"reason": reason}).status_code
            == 422
        )
    assert (
        api2.post(f"{BASE}/team-members/{other['id']}/leave", json={"reason": REASON}).status_code
        == 404
    )  # not yours
    assert (
        api2.post(f"{BASE}/team-members/{lead_id}/leave", json={"reason": "x" * 500}).status_code
        == 200
    )
    assert team(api, world["pid"])["lead_member_id"] is None


def test_cancelling_a_pending_team_releases_everything(
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = confirmed(api, world)
    as_dev(api2, bidder_of(world, run["team_bids"][0]))
    api2.post(f"{BASE}/invitations/{my_invitation(api2, world['pid'])['id']}/accept")
    r = api.post(f"{BASE}/projects/{world['pid']}/cancel", json={"reason": "Plans changed."})
    assert r.status_code == 200, r.text
    rows = _sql(
        migration_url,
        "SELECT t.status::text, (SELECT count(*) FROM "
        "availability_reservations WHERE project_id = :p AND status <> 'RELEASED'), "
        "(SELECT count(*) FROM invitations i JOIN team_members m ON m.id = "
        "i.team_member_id WHERE m.team_id = t.id AND i.responded_at IS NULL) FROM teams t "
        "WHERE t.project_id = :p",
        p=world["pid"],
    )
    assert tuple(rows[0]) == ("CANCELLED", 0, 0)
    assert my_invitation(api2, world["pid"])["state"] in ("ACCEPTED", "EXPIRED")


# ------------------------------------------------------------- snapshot cap and notifications


def test_ten_pending_invitations_exclude_a_bidder_and_nine_do_not(
    api: Api, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch, migration_url: str
) -> None:
    """D125 at the boundary: the formation snapshot skips a developer with 10 pending answers."""
    busy = world["bidders"][0][0]
    calm = world["bidders"][1][0]
    original = team_svc.pending_invitations

    async def fake(db: Any, ids: Any, now: Any) -> dict[uuid.UUID, int]:
        out = await original(db, ids, now)
        out[uuid.UUID(busy.user_id)] = team_svc.MAX_PENDING_INVITATIONS
        out[uuid.UUID(calm.user_id)] = team_svc.MAX_PENDING_INVITATIONS - 1
        return out

    monkeypatch.setattr(team_svc, "pending_invitations", fake)
    run = _run(api, world["pid"], min_newcomers=0)
    snap = dict(
        _sql(
            migration_url,
            "SELECT candidate_snapshot FROM formation_runs WHERE id = :r",
            r=run["id"],
        )[0][0]
    )
    bids = {c["developer_id"] for c in snap["candidates"]}
    assert busy.user_id not in bids
    assert calm.user_id in bids
    assert any(code == "TOO_MANY_PENDING_INVITATIONS" for _b, code in snap["rejected"])


def test_notifications_are_your_own(api: Api, api2: Api, world: dict[str, Any]) -> None:
    run = confirmed(api, world)
    as_dev(api2, bidder_of(world, run["team_bids"][0]))
    items = api2.get(f"{BASE}/notifications").json()["items"]
    assert items
    count = api2.get(f"{BASE}/notifications/unread-count").json()["unread"]
    assert count >= 1
    first = items[0]
    assert api.post(f"{BASE}/notifications/{first['id']}/read").status_code == 404  # not yours
    r = api2.post(f"{BASE}/notifications/{first['id']}/read")
    assert r.status_code == 200
    assert r.json()["read_at"] is not None
    assert api2.get(f"{BASE}/notifications/unread-count").json()["unread"] == count - 1
    client_before = api.get(f"{BASE}/notifications/unread-count").json()["unread"]
    assert api2.post(f"{BASE}/notifications/read-all").json()["marked"] == count - 1
    assert api2.get(f"{BASE}/notifications/unread-count").json()["unread"] == 0
    assert api.get(f"{BASE}/notifications/unread-count").json()["unread"] == client_before
    assert api2.get(f"{BASE}/notifications?cursor=bad").status_code == 422
    assert all(n["link_path"] is None or n["link_path"].startswith("/") for n in items)


# ------------------------------------------------------------------- reopen and raise budget


def _decline_one_with_no_candidates(
    api: Api, api2: Api, world: dict[str, Any], migration_url: str, *, price: int | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Confirm, then make the other bidders unusable — withdrawn, or priced so each passes
    Algorithm 1 alone (≤ the budget after fee) but no longer fits next to the remaining member —
    and let one member decline: the repair finds nobody."""
    run = confirmed(api, world)
    others = [b for _u, b in world["bidders"] if b not in run["team_bids"]]
    if price is None:
        _sql(
            migration_url,
            "UPDATE bids SET status = 'WITHDRAWN' WHERE id = ANY(:ids)",
            ids=[uuid.UUID(b) for b in others],
        )
    else:
        _sql(
            migration_url,
            "UPDATE bids SET price_paisa = :p WHERE id = ANY(:ids)",
            p=price,
            ids=[uuid.UUID(b) for b in others],
        )
    leaver = run["team_bids"][1]
    as_dev(api2, bidder_of(world, leaver))
    inv = my_invitation(api2, world["pid"])
    assert api2.post(f"{BASE}/invitations/{inv['id']}/decline", json={}).status_code == 200
    rep = api.get(f"{BASE}/projects/{world['pid']}/repair").json()
    assert _job_status(api, rep["id"]) == "NO_CANDIDATES"
    return run, api.get(f"{BASE}/projects/{world['pid']}/repair").json()


def test_reopened_place_takes_bids_for_that_place_only(
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    run, rep = _decline_one_with_no_candidates(api, api2, world, migration_url)
    codes = [r["code"] for r in rep["reasons"]]
    assert "NO_BIDS_FOR_SLOT" in codes
    assert set(codes) <= {"NO_BIDS_FOR_SLOT", "NEWCOMER_MINIMUM_RELAXED"}
    slot = world["slot"]
    r = api.post(f"{BASE}/projects/{world['pid']}/slots/{slot}/reopen")
    assert r.status_code == 200, r.text
    again = api.post(f"{BASE}/projects/{world['pid']}/slots/{slot}/reopen")
    assert again.status_code == 409  # already open
    # The project shows one open place in search, without any bid data.
    found = api2.get(f"{BASE}/projects/search?q=ordering").json()["items"]
    card = next(c for c in found if c["id"] == world["pid"])
    assert card["open_places"] >= 1
    assert card["open_for_bids"] is True
    assert "price_paisa" not in json.dumps(card)
    # A developer who already bid on the project can't bid again (D137).
    decliner = bidder_of(world, run["team_bids"][1])
    as_dev(api2, decliner)
    r = api2.post(
        f"{BASE}/projects/{world['pid']}/bids",
        json={"slot_id": slot, "price_paisa": 1_000_000, "days_needed": 10},
    )
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")
    # A new developer can, for that place.
    fresh = api2.sign_in_as("DEVELOPER")
    skill = api2.get(f"{BASE}/skills").json()[0]
    api2.put(
        f"{BASE}/me/skills",
        json={"skills": [{"skill_id": skill.get("skill_id") or skill["id"], "self_level": 4}]},
    )
    _sql(
        migration_url,
        "INSERT INTO reputation_snapshots (id, developer_id, omega, x, xm, beta, "
        "mu, t, c, p, completed_projects, distinct_clients) VALUES (gen_random_uuid(), :d, 0.6, "
        "0.7, 0.66, 0.8, 0.7, 0.8, 0.7, 0.75, 6, 4)",
        d=fresh.user_id,
    )
    r = api2.post(
        f"{BASE}/projects/{world['pid']}/bids",
        json={"slot_id": slot, "price_paisa": 1_500_000, "days_needed": 15},
    )
    assert r.status_code == 201, r.text
    # Closing the window queues a new repair that sees the new bid.
    _sql(
        migration_url,
        "UPDATE project_slots SET reopened_until = now() - interval '1 minute' WHERE id = :s",
        s=slot,
    )
    assert api.post(f"{BASE}/__test__/lifecycle/expire").json()["slots_closed"] == 1
    rep = api.get(f"{BASE}/projects/{world['pid']}/repair").json()
    assert rep["status"] == "COMPUTING"
    assert _job_status(api, rep["id"]) == "READY"
    # A third reopen is refused (at most two per place).
    _sql(migration_url, "UPDATE project_slots SET reopen_count = 2 WHERE id = :s", s=slot)
    r = api.post(f"{BASE}/projects/{world['pid']}/slots/{slot}/reopen")
    assert r.status_code == 409


def test_raising_the_budget_covers_the_shortfall(
    api: Api, api2: Api, world: dict[str, Any], migration_url: str
) -> None:
    _, rep = _decline_one_with_no_candidates(api, api2, world, migration_url, price=9_500_000)
    reason = next(r for r in rep["reasons"] if r["code"] == "REMAINING_BUDGET_TOO_LOW")
    assert reason["shortfall_paisa"] > 0
    project = api.get(f"{BASE}/projects/{world['pid']}").json()
    budget, version = project["budget_paisa"], project["version"]
    low = api.post(
        f"{BASE}/projects/{world['pid']}/budget",
        json={"budget_paisa": budget + 1},
        headers={"If-Match": str(version)},
    )
    assert (low.status_code, _code(low)) == (422, "VALIDATION_ERROR")
    new = budget + reason["shortfall_paisa"] * 2
    stale = api.post(
        f"{BASE}/projects/{world['pid']}/budget",
        json={"budget_paisa": new},
        headers={"If-Match": str(version - 1)},
    )
    assert (stale.status_code, _code(stale)) == (409, "VERSION_CONFLICT")
    ok = api.post(
        f"{BASE}/projects/{world['pid']}/budget",
        json={"budget_paisa": new},
        headers={"If-Match": str(version)},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "COMPUTING"
    assert api.get(f"{BASE}/projects/{world['pid']}").json()["budget_paisa"] == new
    audit = _sql(
        migration_url,
        "SELECT before, after FROM audit_log WHERE action = "
        "'project.budget_raised' AND entity_id = :p",
        p=world["pid"],
    )
    assert audit[0][0]["budget_paisa"] == budget
    assert audit[0][1]["budget_paisa"] == new
    # Only from a "budget too low" repair: with a READY one it's refused.
    assert _job_status(api, ok.json()["id"]) in ("READY", "NO_CANDIDATES")
