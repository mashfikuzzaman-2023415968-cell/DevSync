"""Weekly check-ins over HTTP and the reminders job (spec §10.2 Check-ins, §11, §12; D145).

Covered: members post one per week (a second, also two at once, is 409); the client reads and
can't post (403); former members and outsiders get 404; field bounds and mass assignment; a
blocker tells the lead and records `blocker.reported`; the feed's "this week" list; and the
Monday job, which reminds only members who haven't posted and records each finished missed week
once (idempotent, catches up after a skipped run). The on-time boundary itself is unit-tested
with fixed instants in `tests/algorithms/test_weeks.py`.

Modules driven: `app/api/v1/checkins.py`, `app/services/checkins.py`,
`app/jobs/workspace_jobs.py`, `app/schemas/checkins.py`.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.algorithms.weeks import week_of
from app.jobs.workspace_jobs import remind_checkins
from tests.helpers import Api
from tests.security.formation_world import BASE, _code, _job, _sql
from tests.security.workspace_world import act_as, events, started_project

pytestmark = [pytest.mark.security, pytest.mark.api]
GOOD = {"done": "Finished the stock table.", "next": "Filters and paging.", "confidence": 4}


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    world = started_project(api, migration_url)
    world["url"] = migration_url
    return world


def _post(api: Api, w: dict[str, Any], **body: Any) -> Any:
    return api.post(f"{BASE}/projects/{w['pid']}/checkins", json={**GOOD, **body})


def test_a_member_checks_in_once_a_week(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    first = _post(api, w)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["week_start"] == week_of(datetime.now(UTC)).isoformat()
    assert body["member"]["id"] == w["member"].user_id
    second = _post(api, w, done="Again")
    assert (second.status_code, _code(second)) == (409, "CHECKIN_EXISTS")
    posted = events(w["url"], w["pid"], "checkin.posted")
    assert len(posted) == 1
    assert posted[0]["subject_id"] == w["member"].user_id


def test_two_check_ins_at_once_leave_exactly_one(api: Api, api2: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    act_as(api2, w["member"])
    results: list[int] = []

    def post(client: Api) -> None:
        results.append(_post(client, w).status_code)

    threads = [threading.Thread(target=post, args=(c,)) for c in (api, api2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 409]
    rows = _sql(w["url"], "SELECT count(*) FROM checkins WHERE project_id = :p", p=w["pid"])
    assert rows[0][0] == 1


def test_who_may_post_and_read(api: Api, w: dict[str, Any]) -> None:
    for who, code in (("client", 403), ("other_client", 403), ("former", 404), ("outsider", 404)):
        act_as(api, w[who])
        assert _post(api, w).status_code == code, who
    act_as(api, w["lead"])
    assert _post(api, w).status_code == 201  # the lead is a member too
    for who, code in (("client", 200), ("member", 200), ("former", 404), ("outsider", 404)):
        act_as(api, w[who])
        assert api.get(f"{BASE}/projects/{w['pid']}/checkins").status_code == code, who


@pytest.mark.parametrize(
    "body",
    [
        {"done": ""},
        {"done": "x" * 2001},
        {"next": "x" * 2001},
        {"blockers": "x" * 2001},
        {"confidence": 0},
        {"confidence": 6},
        {"confidence": True},  # booleans are never numbers (D81)
        {"week_start": "2026-11-23"},
        {"on_time": True},
        {"team_member_id": "00000000-0000-4000-8000-000000000000"},
        {"done": "nul \u0000 here"},
    ],
)
def test_field_bounds_and_mass_assignment(
    api: Api, w: dict[str, Any], body: dict[str, Any]
) -> None:
    act_as(api, w["member"])
    assert _post(api, w, **body).status_code == 422


def test_the_longest_texts_are_accepted(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    r = _post(api, w, done="x" * 2000, next="y" * 2000, blockers="z" * 2000, confidence=1)
    assert r.status_code == 201, r.text


def test_a_blocker_tells_the_lead(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    r = _post(api, w, blockers="The supplier API keys haven't arrived.")
    assert r.status_code == 201
    assert len(events(w["url"], w["pid"], "blocker.reported")) == 1
    act_as(api, w["lead"])
    notes = api.get(f"{BASE}/notifications").json()["items"]
    assert any(n["type"] == "BLOCKER_REPORTED" for n in notes)
    assert all("supplier" not in n["body"] for n in notes)  # the text stays in the workspace


def test_the_feed_says_who_still_owes_a_check_in(api: Api, w: dict[str, Any]) -> None:
    joined = datetime.now(UTC) - timedelta(days=8)  # so this week is expected whatever today is
    _sql(
        w["url"], "UPDATE team_members SET joined_at = :j WHERE team_id = :t", j=joined, t=w["team"]
    )
    act_as(api, w["member"])
    assert _post(api, w).status_code == 201
    feed = api.get(f"{BASE}/projects/{w['pid']}/checkins").json()
    assert feed["this_week"]["posted"] is True
    missing = {m["id"] for m in feed["this_week"]["missing"]}
    assert w["lead"].user_id in missing
    assert w["member"].user_id not in missing
    assert w["former"].user_id not in missing
    assert [c["member"]["id"] for c in feed["items"]] == [w["member"].user_id]
    assert api.get(f"{BASE}/projects/{w['pid']}/checkins?sort=new").status_code == 400


def test_reminders_and_missed_weeks(api: Api, w: dict[str, Any]) -> None:
    # Both members became ACTIVE three weeks ago; the member posts this week, the lead never.
    joined = datetime.now(UTC) - timedelta(days=21)
    _sql(
        w["url"], "UPDATE team_members SET joined_at = :j WHERE team_id = :t", j=joined, t=w["team"]
    )
    act_as(api, w["member"])
    assert _post(api, w).status_code == 201
    now = datetime.now(UTC)
    first = _job(remind_checkins(now))
    assert first["reminded"] >= 1
    act_as(api, w["lead"])
    lead_notes = [
        n
        for n in api.get(f"{BASE}/notifications").json()["items"]
        if n["type"] == "CHECKIN_REMINDER"
    ]
    assert len(lead_notes) == 1
    act_as(api, w["member"])
    assert not [
        n
        for n in api.get(f"{BASE}/notifications").json()["items"]
        if n["type"] == "CHECKIN_REMINDER"
    ]
    missed = events(w["url"], w["pid"], "checkin.missed")
    lead_missed = [e for e in missed if e["subject_id"] == w["lead"].user_id]
    member_missed = [e for e in missed if e["subject_id"] == w["member"].user_id]
    assert len(lead_missed) in (2, 3)  # the finished weeks since the first Monday after joining
    assert len(member_missed) == len(lead_missed)  # the member also missed those weeks
    again = _job(remind_checkins(now))  # idempotent per member-week
    assert again == {"reminded": 0, "missed": 0}
    later = _job(remind_checkins(now + timedelta(days=7)))  # a skipped week is caught up
    assert later["missed"] >= 1
