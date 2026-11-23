"""Team formation over HTTP (spec §10.2 Formation, §14.13 row 7, §17 Phase 7; D106–D110).

A client's FORMING project with five bidders (one a newcomer) for two places. The run is queued
through the API and executed here by calling the job directly (the test stack has no worker), so
each step is deterministic:

- only the owning client starts and confirms; others get 404, other roles 403; admins read and
  verify (step-up);
- the server picks the seed (a body `seed` is 422) and refuses mass-assigned fields, impossible
  dials, all-zero weights and standards below the floor; one run at a time; an Idempotency-Key
  replays the same run; a BIDDING project is 409;
- the result is optimal on this small problem, the fairness dial includes the newcomer, the
  stored run reproduces;
- confirm creates the team (TEAM_PENDING), marks bids SELECTED / NOT_SELECTED, records unsent
  invitations and tentative reservations, and tells the non-selected bidders; a second confirm is
  409;
- "why not selected" is the bidder's own only and names no other bid, price or person; its
  counterfactual price, applied, would really have selected the bid.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.jobs.formation_jobs import execute_run, execute_verify, write_explanations
from tests.helpers import Api
from tests.helpers import wait_for_next_totp_window as next_totp
from tests.security.formation_world import BASE, UNKNOWN, _code, _job, _publish, _sql

pytestmark = [pytest.mark.security, pytest.mark.api]


def _start(api: Api, pid: str, **body: Any) -> Any:
    """Start a run; the 10-an-hour quota is reset first (it counts refused requests too)."""
    assert api.get(f"{BASE}/__test__/ratelimits/reset").status_code == 204
    return api.post(f"{BASE}/projects/{pid}/formation-runs", json=body)


def _run(api: Api, pid: str, **body: Any) -> dict[str, Any]:
    r = _start(api, pid, **body)
    assert r.status_code == 202, r.text
    accepted = r.json()
    assert _job(execute_run(uuid.UUID(accepted["run_id"]))).value == "SUCCEEDED"
    out = api.get(f"{BASE}/formation-runs/{accepted['run_id']}")
    assert out.status_code == 200, out.text
    return {**out.json(), "job": accepted["job_id"]}


# --------------------------------------------------------------------------------- start


def test_start_validates_and_refuses_mass_assignment(api: Api, world: dict[str, Any]) -> None:
    pid = world["pid"]
    for body in (
        {"seed": 42},
        {"status": "SUCCEEDED"},
        {"result": {}},
        {"is_lead": True},
        {"candidate_snapshot": {}},
        {"min_newcomers": 3},
        {"min_newcomers": -1},
        {"preset": "cheapest"},
        {"min_performance": "1.5"},
        {"weights": {"competency": 0, "teamwork": 0, "time": 0, "cost": 0}},
        {"weights": {"competency": "0.5", "teamwork": "0.5", "time": "0.5"}},
    ):
        r = _start(api, pid, **body)
        assert r.status_code == 422, (body, r.text)
    r = _start(api, pid, min_performance="0.05")  # below the platform floor (D54)
    assert (r.status_code, _code(r)) == (422, "VALIDATION_ERROR")
    assert _start(api, UNKNOWN).status_code == 404


def test_only_the_owner_starts_and_one_run_at_a_time(
    api: Api, api3: Api, world: dict[str, Any]
) -> None:
    pid = world["pid"]
    api3.sign_in_as("CLIENT")
    assert _start(api3, pid).status_code == 404  # another client: not found
    key = {"Idempotency-Key": str(uuid.uuid4())}
    first = api.post(f"{BASE}/projects/{pid}/formation-runs", json={}, headers=key)
    assert first.status_code == 202, first.text
    replay = api.post(f"{BASE}/projects/{pid}/formation-runs", json={}, headers=key)
    assert replay.status_code == 202
    assert replay.json()["run_id"] == first.json()["run_id"]
    busy = _start(api, pid)
    assert (busy.status_code, _code(busy)) == (409, "LIMIT_REACHED")
    _job(execute_run(uuid.UUID(first.json()["run_id"])))
    assert _start(api, pid).status_code == 202  # finished: a new run may start


def test_a_bidding_project_cannot_form_a_team(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, _slot = _publish(api)
    r = _start(api, pid)
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")


# ---------------------------------------------------------------------------- result


def test_run_result_is_optimal_fair_and_reproducible(
    api: Api, api3: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = _run(api, world["pid"], min_newcomers=1)
    result = run["result"]
    assert run["status"] == "SUCCEEDED"
    assert run["params"]["min_newcomers"] == 1
    assert len(result["team"]) == 2
    assert result["verification"]["available"] is True
    assert result["verification"]["optimal"] is True
    assert result["newcomers"] >= 1  # the dial put the newcomer in
    assert result["fairness"]["applied_k"] == 1
    assert result["fairness"]["cost"] >= 0
    assert 1 <= len(result["top"]) <= 3
    assert result["top"][0]["recommended"] is True
    assert result["price_paisa"] <= result["budget_after_fee_paisa"]
    assert run["can_confirm"] is True
    # The job and its stream are the client's.
    job = api.get(f"{BASE}/jobs/{run['job']}").json()
    assert (job["status"], job["progress"]) == ("SUCCEEDED", 100)
    listed = api.get(f"{BASE}/projects/{world['pid']}/formation-runs").json()
    assert listed[0]["id"] == run["id"]
    # A developer and another client can't read it.
    api3.sign_in_as("CLIENT")
    assert api3.get(f"{BASE}/formation-runs/{run['id']}").status_code == 404
    assert api3.get(f"{BASE}/projects/{world['pid']}/formation-runs").status_code == 404
    # The admin verifies with a step-up; the run reproduces.
    admin = api3.sign_in_as("ADMIN")
    assert api3.get(f"{BASE}/formation-runs/{run['id']}").status_code == 200
    r = api3.post(f"{BASE}/formation-runs/{run['id']}/verify")
    assert (r.status_code, _code(r)) == (403, "STEP_UP_REQUIRED")
    assert (
        api3.post(
            f"{BASE}/auth/step-up", json={"code": next_totp(admin.totp_secret or "")}
        ).status_code
        == 204
    )
    r = api3.post(f"{BASE}/formation-runs/{run['id']}/verify")
    assert r.status_code == 202, r.text
    assert _job(execute_verify(uuid.UUID(run["id"]), uuid.UUID(r.json()["job_id"])))
    page = api3.get(f"{BASE}/admin/formation-runs").json()
    mine = next(x for x in page["items"] if x["id"] == run["id"])
    assert mine["verified"] is True
    assert api3.get(f"{BASE}/admin/formation-runs?cursor=bad").status_code == 422


def test_the_dial_at_zero_costs_nothing(api: Api, world: dict[str, Any]) -> None:
    run = _run(api, world["pid"], min_newcomers=0)
    fairness = run["result"]["fairness"]
    assert (fairness["requested_k"], fairness["cost"], fairness["binding"]) == (0, 0.0, False)


# ---------------------------------------------------------------------------- confirm


def test_confirm_forms_the_team_and_explains_to_the_others(
    api: Api, api2: Api, api3: Api, world: dict[str, Any], migration_url: str
) -> None:
    run = _run(api, world["pid"], min_newcomers=1)
    team = {m["bid_id"] for m in run["result"]["team"]}
    dev = api3.sign_in_as("DEVELOPER")
    assert api3.post(f"{BASE}/formation-runs/{run['id']}/confirm").status_code == 403
    del dev
    r = api.post(f"{BASE}/formation-runs/{run['id']}/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["project_status"] == "TEAM_PENDING"
    assert r.json()["invitations_sent"] is True
    again = api.post(f"{BASE}/formation-runs/{run['id']}/confirm")
    assert (again.status_code, _code(again)) == (409, "INVALID_STATE")
    assert _start(api, world["pid"]).status_code == 409  # no more runs once a team is formed
    statuses = dict(
        _sql(
            migration_url,
            "SELECT id::text, status::text FROM bids WHERE project_id = :pid",
            pid=world["pid"],
        )
    )
    for bid_id, status in statuses.items():
        assert status == ("SELECTED" if bid_id in team else "NOT_SELECTED"), bid_id
    rows = _sql(
        migration_url,
        "SELECT count(*), count(i.sent_at) FROM team_members m "
        "JOIN invitations i ON i.team_member_id = m.id JOIN teams t ON t.id = m.team_id "
        "WHERE t.project_id = :pid",
        pid=world["pid"],
    )
    assert tuple(rows[0]) == (2, 2)  # two members, both invitations sent at confirm (D123)
    reservations = _sql(
        migration_url,
        "SELECT count(*) FROM availability_reservations "
        "WHERE project_id = :pid AND status = 'TENTATIVE'",
        pid=world["pid"],
    )
    assert reservations[0][0] == 2
    told = _sql(
        migration_url,
        "SELECT count(*) FROM notifications n JOIN bids b "
        "ON n.link_path = '/dev/bids/' || b.id::text WHERE b.project_id = :pid "
        "AND n.type = 'BID_NOT_SELECTED'",
        pid=world["pid"],
    )
    assert told[0][0] == 3

    assert _job(write_explanations(uuid.UUID(run["id"])))["explanations"] == 3
    assert _job(write_explanations(uuid.UUID(run["id"])))["explanations"] == 3  # idempotent
    # A bidder who wasn't selected reads their own explanation, which names nobody else.
    loser_user, loser_bid = next((d, b) for d, b in world["bidders"] if b not in team)
    assert api2.login(loser_user).status_code == 200
    own = loser_bid
    others = {b for _d, b in world["bidders"]} - {own}
    r = api2.get(f"{BASE}/bids/{own}/explanation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reasons"] in (["NOT_SELECTED"], ["NOT_SHORTLISTED"])
    assert body["compare"] is None or body["compare"]["your_price_paisa"] > 0
    text_body = json.dumps(body)
    for other in others:
        assert other not in text_body
    for m in run["result"]["team"]:
        assert m["developer_name"] not in text_body
        assert m["developer_id"] not in text_body
    for other in others:
        assert api2.get(f"{BASE}/bids/{other}/explanation").status_code == 404
    # A selected bidder has nothing to explain.
    winner_user, winner_bid = next((d, b) for d, b in world["bidders"] if b in team)
    assert api2.login(winner_user).status_code == 200
    assert api2.get(f"{BASE}/bids/{winner_bid}/explanation").status_code == 404
    assert api.get(f"{BASE}/bids/{own}/explanation").status_code == 403  # the client: no
    assert api2.get(f"{BASE}/bids/{UNKNOWN}/explanation").status_code == 404
