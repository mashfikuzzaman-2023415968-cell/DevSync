"""Bidding rules over HTTP (spec §8 bid states, §10.1 conventions, §13.5 #12, §14.8 caps):

- INELIGIBLE marking when bidding closes, with plain-language reasons for the bidder (and the
  client still sees every bid), re-evaluated when the client changes the terms and reopened by
  an extension;
- the developer's bid detail `GET /bids/{id}` (own bid only; IDOR → 404);
- at most 30 open bids per developer and 20 active projects per client (409 `LIMIT_REACHED`);
- `If-Match` on bid edits and withdrawals (stale → 409 `VERSION_CONFLICT`);
- cursor pagination of `GET /me/bids`.

Bulk rows (other projects, filler bids) are written with the migrator role, like the other
bidding tests do for reputation snapshots; everything under test goes through the API.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from app.jobs.bidding_jobs import close_due_bidding
from tests.helpers import Api, SeededUser
from tests.security.test_bidding_followups import (
    _bid,
    _close_bidding,
    _developer,
    _notifications,
    _publish,
    _sql,
)

pytestmark = [pytest.mark.security, pytest.mark.api]


# --------------------------------------------------------------------------- helpers


def _slot_skill(url: str, slot_id: str) -> str:
    return str(_sql(url, "SELECT skill_id FROM project_slots WHERE id = :s", s=slot_id)[0][0])


def _other_project(url: str, client_id: str, skill_id: str, status: str = "BIDDING") -> str:
    """A published project of `client_id` with one 2-person slot; returns the slot id."""
    pid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(
        url,
        "INSERT INTO projects (id, client_id, title, budget_paisa, deadline_days, team_size, "
        "status, bidding_deadline) VALUES (:id, :client, 'Filler project', 10000000, 30, 2, "
        "CAST(:status AS project_status), now() + interval '3 days')",
        id=pid,
        client=client_id,
        status=status,
    )
    _sql(
        url,
        "INSERT INTO project_slots (id, project_id, skill_id, count) VALUES (:id, :p, :s, 2)",
        id=sid,
        p=pid,
        s=skill_id,
    )
    return sid


def _filler_bids(
    url: str, client_id: str, dev_id: str, skill_id: str, n: int, *, status: str = "ACTIVE"
) -> list[str]:
    """`n` bids by `dev_id`, each on its own filler project, `i` minutes apart (newest first)."""
    ids = []
    for i in range(n):
        sid = _other_project(url, client_id, skill_id)
        bid_id = str(uuid.uuid4())
        _sql(
            url,
            "INSERT INTO bids (id, project_id, developer_id, slot_id, price_paisa, days_needed, "
            "hours_per_week_committed, status, created_at) SELECT :id, project_id, :dev, id, "
            "100000, 10, 10, CAST(:status AS bid_status), now() - make_interval(mins => :i) "
            "FROM project_slots WHERE id = :sid",
            id=bid_id,
            dev=dev_id,
            sid=sid,
            status=status,
            i=i + 1,
        )
        ids.append(bid_id)
    return ids


def _set_bid(url: str, bid_id: str, status: str, reasons: list[str]) -> None:
    _sql(
        url,
        "UPDATE bids SET status = CAST(:st AS bid_status), ineligible_reasons = CAST(:r AS jsonb) "
        "WHERE id = :id",
        st=status,
        r=json.dumps(reasons),
        id=bid_id,
    )


def _bid_row(url: str, bid_id: str) -> tuple[str, list[str], int]:
    row = _sql(
        url, "SELECT status, ineligible_reasons, version FROM bids WHERE id = :id", id=bid_id
    )[0]
    return str(row[0]), list(row[1]), int(row[2])


def _run_deadline_job() -> dict[str, int]:
    return asyncio.run(close_due_bidding())


def _code(r: Any) -> str:
    return str(r.json()["error"]["code"])


# --------------------------------------------------------------------------- open-bid cap (30)


def test_the_30th_open_bid_is_accepted_and_the_31st_refused(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    pid2, slot2 = _publish(api, title="Second ordering system")
    skill = _slot_skill(migration_url, slot_id)
    dev = _developer(api, migration_url)
    _filler_bids(migration_url, client.user_id, dev.user_id, skill, 29)

    thirtieth = _bid(api, pid, slot_id)
    assert thirtieth.status_code == 201, thirtieth.text
    thirty_first = _bid(api, pid2, slot2)
    assert thirty_first.status_code == 409
    assert _code(thirty_first) == "LIMIT_REACHED"
    assert "30 open bids" in thirty_first.json()["error"]["message"]

    # Withdrawing one frees a place (boundary back to 29).
    assert api.delete(f"/api/v1/bids/{thirtieth.json()['id']}").status_code == 204
    assert _bid(api, pid2, slot2).status_code == 201


def test_withdrawn_and_ineligible_bids_do_not_count(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    skill = _slot_skill(migration_url, slot_id)
    dev = _developer(api, migration_url)
    _filler_bids(migration_url, client.user_id, dev.user_id, skill, 29)
    _filler_bids(migration_url, client.user_id, dev.user_id, skill, 3, status="WITHDRAWN")
    _filler_bids(migration_url, client.user_id, dev.user_id, skill, 2, status="INELIGIBLE")
    assert _bid(api, pid, slot_id).status_code == 201  # 29 open + this one = 30


def test_the_cap_is_per_developer(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    skill = _slot_skill(migration_url, slot_id)
    busy = _developer(api, migration_url)
    _filler_bids(migration_url, client.user_id, busy.user_id, skill, 30)
    assert _code(_bid(api, pid, slot_id)) == "LIMIT_REACHED"
    _developer(api, migration_url)  # someone else is not affected
    assert _bid(api, pid, slot_id).status_code == 201


# --------------------------------------------------------------------------- active-project cap


def _draft(api: Api, title: str) -> str:
    """A complete draft ready to publish (as the signed-in client, payment verified)."""
    sid = str(api.get("/api/v1/skills").json()[0].get("id"))
    pid = api.post(
        "/api/v1/projects",
        json={
            "title": title,
            "summary": "Order and track restaurant orders.",
            "budget_paisa": 12_000_000,
            "deadline_days": 30,
            "team_size": 2,
        },
    ).json()["id"]
    api.put(f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]})
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Build", "duration_days": 10, "share_bp": 10000, "skill_ids": [sid]}
            ]
        },
    )
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204
    return str(pid)


def test_the_20th_active_project_publishes_and_the_21st_is_refused(
    api: Api, migration_url: str
) -> None:
    client = api.sign_in_as("CLIENT")
    skill = str(api.get("/api/v1/skills").json()[0]["id"])
    for status in ["BIDDING"] * 10 + ["FORMING", "TEAM_PENDING", "IN_PROGRESS"] * 3:
        _other_project(migration_url, client.user_id, skill, status)  # 19 active
    for status in ("DRAFT", "CANCELLED", "COMPLETED"):
        _other_project(migration_url, client.user_id, skill, status)  # not active

    twentieth = _draft(api, "Twentieth active project")
    assert api.post(f"/api/v1/projects/{twentieth}/publish", json={}).status_code == 200
    extra = _draft(api, "One project too many")
    refused = api.post(f"/api/v1/projects/{extra}/publish", json={})
    assert refused.status_code == 409
    assert _code(refused) == "LIMIT_REACHED"
    assert "20 active projects" in refused.json()["error"]["message"]
    # The draft is untouched and publishes once a place is free.
    assert api.get(f"/api/v1/projects/{extra}").json()["status"] == "DRAFT"
    cancel = api.post(f"/api/v1/projects/{twentieth}/cancel", json={"reason": "Not needed now."})
    assert cancel.status_code == 200
    assert api.post(f"/api/v1/projects/{extra}/publish", json={}).status_code == 200


# --------------------------------------------------------------------------- If-Match on bids


def test_bid_edits_use_the_version(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    _developer(api, migration_url)
    bid = _bid(api, pid, slot_id).json()
    assert bid["version"] == 1

    ok = api.patch(f"/api/v1/bids/{bid['id']}", json={"days_needed": 18}, headers={"If-Match": "1"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["version"] == 2

    stale = api.patch(
        f"/api/v1/bids/{bid['id']}", json={"days_needed": 15}, headers={"If-Match": "1"}
    )
    assert stale.status_code == 409
    assert _code(stale) == "VERSION_CONFLICT"
    assert api.get(f"/api/v1/bids/{bid['id']}").json()["days_needed"] == 18  # not applied

    bad = api.patch(
        f"/api/v1/bids/{bid['id']}", json={"days_needed": 15}, headers={"If-Match": "two"}
    )
    assert bad.status_code == 422

    stale_withdraw = api.delete(f"/api/v1/bids/{bid['id']}", headers={"If-Match": "1"})
    assert _code(stale_withdraw) == "VERSION_CONFLICT"
    assert api.delete(f"/api/v1/bids/{bid['id']}", headers={"If-Match": "2"}).status_code == 204


# --------------------------------------------------------------------------- bid detail


def test_bid_detail_is_the_bidders_own(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    dev = _developer(api, migration_url)
    bid_id = _bid(api, pid, slot_id).json()["id"]

    mine = api.get(f"/api/v1/bids/{bid_id}")
    assert mine.status_code == 200, mine.text
    body = mine.json()
    assert body["project"]["title"] == "Online ordering system"
    assert body["project"]["open_for_bids"] is True
    assert (body["can_edit"], body["can_withdraw"]) == (True, True)
    assert body["eligibility"]["eligible"] is True
    assert body["reasons"] == []

    _developer(api, migration_url)  # another developer: the same id is "not found"
    assert api.get(f"/api/v1/bids/{bid_id}").status_code == 404
    assert api.get(f"/api/v1/bids/{uuid.uuid4()}").status_code == 404
    assert api.get("/api/v1/bids/not-a-uuid").status_code == 422
    api.login(client)  # the project's client uses the bids table, not this view
    assert api.get(f"/api/v1/bids/{bid_id}").status_code == 403
    api.login(dev)
    assert api.get(f"/api/v1/bids/{bid_id}").status_code == 200


def test_bid_detail_after_bidding_closed_offers_no_changes(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    _developer(api, migration_url)
    bid_id = _bid(api, pid, slot_id).json()["id"]
    _close_bidding(migration_url, pid)
    body = api.get(f"/api/v1/bids/{bid_id}").json()
    assert body["project"]["open_for_bids"] is False
    assert (body["can_edit"], body["can_withdraw"]) == (False, False)
    assert body["eligibility"] is None


def test_ineligible_reasons_are_plain_words_for_the_bidder(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    dev = _developer(api, migration_url)
    bid_id = _bid(api, pid, slot_id).json()["id"]
    _close_bidding(migration_url, pid)
    _set_bid(migration_url, bid_id, "INELIGIBLE", ["OVER_BUDGET"])

    detail = api.get(f"/api/v1/bids/{bid_id}").json()
    assert detail["status"] == "INELIGIBLE"
    [reason] = detail["reasons"]
    assert reason["code"] == "OVER_BUDGET"
    assert "budget" in reason["text"]
    assert reason["hint"]
    listed = api.get("/api/v1/me/bids").json()["items"]
    assert [b["reasons"] for b in listed if b["id"] == bid_id] == [detail["reasons"]]

    # A stored code the server doesn't know is never echoed back.
    _set_bid(migration_url, bid_id, "INELIGIBLE", ["<script>alert(1)</script>"])
    assert api.get(f"/api/v1/bids/{bid_id}").json()["reasons"] == []

    # The client still sees the bid (and its verdict) in the bids table.
    api.login(client)
    rows = api.get(f"/api/v1/projects/{pid}/bids").json()["bids"]
    assert [r["id"] for r in rows] == [bid_id]
    api.login(dev)


# --------------------------------------------------------------------------- INELIGIBLE lifecycle


def _two_bidders(api: Api, url: str) -> tuple[SeededUser, str, str, SeededUser, str, str]:
    """A 2-place project, one eligible bid and one over budget; bidding closed."""
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api, budget=10_000_000)
    good = _developer(api, url)
    good_bid = _bid(api, pid, slot_id).json()["id"]
    pricey = _developer(api, url)
    pricey_bid = _bid(api, pid, slot_id, price_paisa=9_800_000).json()["id"]  # > ৳95,000
    _close_bidding(url, pid)
    _ = good
    return client, pid, good_bid, pricey, pricey_bid, slot_id


def test_closing_marks_filtered_bids_ineligible_and_tells_the_bidder_once(
    api: Api, migration_url: str
) -> None:
    _client, pid, good_bid, pricey, pricey_bid, _slot = _two_bidders(api, migration_url)
    _run_deadline_job()
    assert _bid_row(migration_url, pricey_bid)[:2] == ("INELIGIBLE", ["OVER_BUDGET"])
    assert _bid_row(migration_url, good_bid)[:2] == ("ACTIVE", [])
    assert _notifications(migration_url, pricey.user_id, "BID_INELIGIBLE") == 1

    _run_deadline_job()  # the project is still short (1 of 2): re-runs change nothing
    assert _notifications(migration_url, pricey.user_id, "BID_INELIGIBLE") == 1
    version = _bid_row(migration_url, pricey_bid)[2]
    _run_deadline_job()
    assert _bid_row(migration_url, pricey_bid)[2] == version

    api.login(pricey)
    detail = api.get(f"/api/v1/bids/{pricey_bid}").json()
    assert detail["status"] == "INELIGIBLE"
    assert detail["evaluated_at"] is not None
    assert detail["reasons"][0]["code"] == "OVER_BUDGET"
    # An ineligible bid can't be edited or withdrawn (bidding has closed).
    assert api.patch(f"/api/v1/bids/{pricey_bid}", json={"days_needed": 5}).status_code == 409
    assert api.delete(f"/api/v1/bids/{pricey_bid}").status_code == 409
    _ = pid


def test_raising_the_budget_after_close_makes_the_bid_active_again(
    api: Api, migration_url: str
) -> None:
    client, pid, _good, _pricey, pricey_bid, _slot = _two_bidders(api, migration_url)
    _run_deadline_job()
    api.login(client)
    r = api.patch(f"/api/v1/projects/{pid}/bidding-terms", json={"budget_paisa": 12_000_000})
    assert r.status_code == 200, r.text
    assert _bid_row(migration_url, pricey_bid)[:2] == ("ACTIVE", [])
    assert api.get(f"/api/v1/projects/{pid}").json()["status"] == "FORMING"


def test_extending_bidding_reopens_ineligible_bids(api: Api, migration_url: str) -> None:
    client, pid, _good, pricey, pricey_bid, slot_id = _two_bidders(api, migration_url)
    _run_deadline_job()
    api.login(client)
    assert api.post(f"/api/v1/projects/{pid}/extend-bidding").status_code == 200
    assert _bid_row(migration_url, pricey_bid)[:2] == ("ACTIVE", [])
    assert _notifications(migration_url, pricey.user_id, "BIDDING_REOPENED") == 1

    api.login(pricey)  # ... and the bidder can now fix it
    version = api.get(f"/api/v1/bids/{pricey_bid}").json()["version"]
    fixed = api.patch(
        f"/api/v1/bids/{pricey_bid}",
        json={"price_paisa": 4_000_000},
        headers={"If-Match": str(version)},
    )
    assert fixed.status_code == 200, fixed.text
    # Still one standing bid per developer: a second one is refused.
    assert _bid(api, pid, slot_id).status_code == 409


# --------------------------------------------------------------------------- pagination


def test_my_bids_pages_with_a_cursor(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    skill = _slot_skill(migration_url, slot_id)
    dev = _developer(api, migration_url)
    filler = _filler_bids(migration_url, client.user_id, dev.user_id, skill, 24)
    newest = _bid(api, pid, slot_id).json()["id"]

    first = api.get("/api/v1/me/bids").json()
    assert len(first["items"]) == 20  # the default page
    assert first["items"][0]["id"] == newest
    assert first["next_cursor"]
    second = api.get("/api/v1/me/bids", params={"cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 5
    assert second["next_cursor"] is None
    seen = [b["id"] for b in first["items"] + second["items"]]
    assert sorted(seen) == sorted([newest, *filler])  # no gaps, no repeats
    assert seen[1:] == filler  # newest first

    # Boundaries: a page exactly the size of what is left has no next cursor.
    assert api.get("/api/v1/me/bids", params={"limit": 25}).json()["next_cursor"] is None
    assert api.get("/api/v1/me/bids", params={"limit": 24}).json()["next_cursor"]
    for bad in ({"limit": 0}, {"limit": 101}, {"cursor": "%%%"}, {"cursor": "bm90LWEtY3Vyc29y"}):
        assert api.get("/api/v1/me/bids", params=bad).status_code == 422, bad

    only = api.get("/api/v1/me/bids", params={"project_id": pid}).json()["items"]
    assert [b["id"] for b in only] == [newest]
    _set_bid(migration_url, filler[0], "WITHDRAWN", [])
    open_ = api.get("/api/v1/me/bids", params={"status": "ACTIVE", "limit": 100}).json()
    assert len(open_["items"]) == 24
    assert filler[0] not in {b["id"] for b in open_["items"]}
    assert api.get("/api/v1/me/bids", params={"status": "BOGUS"}).status_code == 422

    _developer(api, migration_url)  # sealed: another developer sees none of them
    assert api.get("/api/v1/me/bids").json() == {"items": [], "next_cursor": None}
    assert api.get("/api/v1/me/bids", params={"project_id": pid}).json()["items"] == []
