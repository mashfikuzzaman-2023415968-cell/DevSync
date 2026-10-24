"""Project details and the developer search filters (spec §13.5 #10–#11, §10 Marketplace).

* `GET /public/projects/{id}` adds the description, the published plan (milestones with names,
  durations and states; the CPM schedule with its dependency edges for the mini Gantt) and, for
  signed-in callers only, who the client is (organisation, else display name). Never bid data.
* `GET /projects/search` takes `role` (projects with a slot needing that skill) and `hours` (the
  hours a week the developer can commit; kept only when they fit next to confirmed reservations,
  §9.17), with keyset pages that never skip or repeat a project under the post-filter.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.helpers import Api
from tests.security.test_bidding_followups import _bid, _developer, _publish, _skill, _sql

pytestmark = [pytest.mark.security, pytest.mark.api]

BID_KEYS = {"bids", "bid_count", "bids_count", "price_paisa", "prices", "eligible"}


def _today() -> datetime:
    return datetime.now(UTC)


def _project(api: Api, *, title: str, skill_index: int = 0, **extra: Any) -> str:
    """As the signed-in client: a BIDDING project with a 2-milestone plan (Design → Build)."""
    sid = str(_skill(api, skill_index).get("skill_id") or _skill(api, skill_index)["id"])
    body = {
        "title": title,
        "summary": "Order and track restaurant orders.",
        "description": "A web app for a restaurant to take and track orders.",
        "budget_paisa": 12_000_000,
        "deadline_days": 30,
        "team_size": 2,
        **extra,
    }
    created = api.post("/api/v1/projects", json=body)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    api.put(f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]})
    milestones = api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    ).json()
    ids = {m["name"]: m["id"] for m in milestones}
    deps = api.put(
        f"/api/v1/projects/{pid}/dependencies",
        json={"dependencies": [{"predecessor_id": ids["Design"], "successor_id": ids["Build"]}]},
    )
    assert deps.status_code == 200, deps.text
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204
    published = api.post(f"/api/v1/projects/{pid}/publish", json={})
    assert published.status_code == 200, published.text
    return str(pid)


# --------------------------------------------------------------------------- project details


def test_details_show_description_plan_and_client_to_a_signed_in_developer(api: Api) -> None:
    api.sign_in_as("CLIENT")
    org = api.patch("/api/v1/me/client-profile", json={"organization": "Dhaka Bites Ltd"})
    assert org.status_code == 200, org.text
    pid = _project(api, title="Details project")

    api.sign_in_as("DEVELOPER")
    r = api.get(f"/api/v1/public/projects/{pid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["description"] == "A web app for a restaurant to take and track orders."
    assert body["client"] == {"name": "Dhaka Bites Ltd"}
    assert [(m["name"], m["duration_days"], m["status"]) for m in body["milestones"]] == [
        ("Design", 5, "PLANNED"),
        ("Build", 10, "PLANNED"),
    ]
    schedule = body["schedule"]
    assert schedule["duration"] == 15
    nodes = {n["name"]: n for n in schedule["nodes"]}
    assert (nodes["Design"]["es"], nodes["Design"]["ef"]) == (0, 5)
    assert (nodes["Build"]["es"], nodes["Build"]["ef"]) == (5, 15)
    assert all(n["critical"] for n in nodes.values())
    assert schedule["edges"] == [
        {"predecessor": nodes["Design"]["key"], "successor": nodes["Build"]["key"]}
    ]
    # Sealed bids: nothing about bids, ever (§14.5).
    assert not BID_KEYS & set(body)


def test_guests_get_the_plan_but_not_the_client(api: Api) -> None:
    api.sign_in_as("CLIENT")
    api.patch("/api/v1/me/client-profile", json={"organization": "Hidden Org"})
    pid = _project(api, title="Guest view project")
    api.client.cookies.clear()

    r = api.get(f"/api/v1/public/projects/{pid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client"] is None
    assert "Hidden Org" not in r.text
    assert [m["name"] for m in body["milestones"]] == ["Design", "Build"]
    assert body["schedule"]["duration"] == 15


def test_client_name_falls_back_to_the_display_name(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")  # no organisation saved
    pid = _project(api, title="No org project")
    display = _sql(
        migration_url, "SELECT display_name FROM users WHERE id = :id", id=client.user_id
    )[0][0]
    api.sign_in_as("DEVELOPER")
    assert api.get(f"/api/v1/public/projects/{pid}").json()["client"] == {"name": display}


def test_details_never_show_a_bid_even_to_its_bidder(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    _developer(api, migration_url)
    assert _bid(api, pid, slot_id, price_paisa=1_234_567).status_code == 201
    r = api.get(f"/api/v1/public/projects/{pid}")
    assert r.status_code == 200
    assert "1234567" not in r.text
    assert not BID_KEYS & set(r.json())


def test_projects_without_a_baseline_have_no_plan(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid = _project(api, title="Baseline-less project")
    # A project published before baselines existed (the column is the only marker the API reads).
    _sql(migration_url, "UPDATE projects SET current_baseline_id = NULL WHERE id = :p", p=pid)
    api.sign_in_as("DEVELOPER")
    body = api.get(f"/api/v1/public/projects/{pid}").json()
    assert body["milestones"] == []
    assert body["schedule"] is None


def test_drafts_and_unknown_projects_stay_hidden(api: Api) -> None:
    api.sign_in_as("CLIENT")
    draft = api.post(
        "/api/v1/projects",
        json={"title": "Draft", "budget_paisa": 1_000_000, "deadline_days": 10, "team_size": 2},
    ).json()["id"]
    api.sign_in_as("DEVELOPER")
    assert api.get(f"/api/v1/public/projects/{draft}").status_code == 404
    assert api.get(f"/api/v1/public/projects/{uuid.uuid4()}").status_code == 404
    assert api.get("/api/v1/public/projects/not-a-uuid").status_code == 422


# --------------------------------------------------------------------------- role filter


def test_role_keeps_projects_with_a_slot_for_that_skill(api: Api) -> None:
    api.sign_in_as("CLIENT")
    token = f"role{uuid.uuid4().hex[:8]}"
    first = _skill(api, 0)["name"]
    second = _skill(api, 3)["name"]
    assert first.lower() != second.lower()
    a = _project(api, title=f"{token} first", skill_index=0)
    b = _project(api, title=f"{token} second", skill_index=3)

    api.sign_in_as("DEVELOPER")

    def ids(**params: Any) -> list[str]:
        r = api.get("/api/v1/projects/search", params={"q": token, **params})
        assert r.status_code == 200, r.text
        return [p["id"] for p in r.json()["items"]]

    assert set(ids()) == {a, b}
    assert ids(role=first) == [a]
    assert ids(role=second.upper()) == [b]  # skill names match case-insensitively
    assert ids(role="No such skill") == []
    # Combined with `skills` both must hold.
    assert ids(role=first, skills=[second]) == []


@pytest.mark.parametrize("role", ["", "x" * 81])
def test_role_is_validated(api: Api, role: str) -> None:
    api.sign_in_as("DEVELOPER")
    assert api.get("/api/v1/projects/search", params={"role": role}).status_code == 422


# --------------------------------------------------------------------------- hours filter


def _reserve(url: str, dev_id: str, pid: str, *, hours: int, start: int, end: int) -> None:
    _sql(
        url,
        "INSERT INTO availability_reservations (id, developer_id, project_id, hours_per_week, "
        "from_date, to_date, status) VALUES (:id, :dev, :pid, :h, current_date + :s, "
        "current_date + :e, 'CONFIRMED')",
        id=str(uuid.uuid4()),
        dev=dev_id,
        pid=pid,
        h=hours,
        s=start,
        e=end,
    )


def test_hours_keep_only_projects_the_commitment_fits(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    token = f"hours{uuid.uuid4().hex[:8]}"
    later = (_today() + timedelta(days=120)).date().isoformat()
    now_project = _project(api, title=f"{token} now")  # runs from today for 30 days
    later_project = _project(api, title=f"{token} later", start_date=later)

    dev = api.sign_in_as("DEVELOPER")
    assert api.patch("/api/v1/me/developer-profile", json={"hours_per_week": 40}).status_code == 200
    # 30 h a week already confirmed from day 100 to day 200: only "later" overlaps it.
    _reserve(migration_url, dev.user_id, later_project, hours=30, start=100, end=200)

    def ids(**params: Any) -> set[str]:
        r = api.get("/api/v1/projects/search", params={"q": token, **params})
        assert r.status_code == 200, r.text
        return {p["id"] for p in r.json()["items"]}

    assert ids() == {now_project, later_project}  # no hours: no availability filter
    assert ids(hours=10) == {now_project, later_project}  # 30 + 10 ≤ 40 (boundary)
    assert ids(hours=11) == {now_project}  # 30 + 11 > 40
    assert ids(hours=40) == {now_project}
    assert ids(hours=41) == set()  # more than the profile's 40 h: nothing fits


@pytest.mark.parametrize("hours", ["0", "169", "-1", "ten"])
def test_hours_are_validated(api: Api, hours: str) -> None:
    api.sign_in_as("DEVELOPER")
    assert api.get("/api/v1/projects/search", params={"hours": hours}).status_code == 422


def test_hours_pages_never_skip_or_repeat(api: Api, migration_url: str) -> None:
    """The post-filter reads on until a page is full; the cursor continues after the last
    project examined, so paging the filtered list sees each fitting project once."""
    api.sign_in_as("CLIENT")
    token = f"hpage{uuid.uuid4().hex[:8]}"
    later = (_today() + timedelta(days=120)).date().isoformat()
    fitting = set()
    blocked = set()
    for i in range(6):
        if i % 2:
            blocked.add(_project(api, title=f"{token} blocked {i}", start_date=later))
        else:
            fitting.add(_project(api, title=f"{token} fitting {i}"))

    dev = api.sign_in_as("DEVELOPER")
    api.patch("/api/v1/me/developer-profile", json={"hours_per_week": 40})
    _reserve(migration_url, dev.user_id, next(iter(blocked)), hours=35, start=100, end=200)

    for sort in ("newest", "budget", "deadline"):
        seen: list[str] = []
        cursor: str | None = None
        for _ in range(10):
            params: dict[str, Any] = {"q": token, "hours": 10, "limit": 1, "sort": sort}
            if cursor:
                params["cursor"] = cursor
            r = api.get("/api/v1/projects/search", params=params)
            assert r.status_code == 200, r.text
            seen += [p["id"] for p in r.json()["items"]]
            cursor = r.json()["next_cursor"]
            if not cursor:
                break
        assert len(seen) == len(set(seen)), sort
        assert set(seen) == fitting, sort


def test_clients_cannot_search_with_developer_filters(api: Api) -> None:
    api.sign_in_as("CLIENT")
    assert api.get("/api/v1/projects/search", params={"hours": 10}).status_code == 403
    api.client.cookies.clear()
    assert api.get("/api/v1/projects/search", params={"role": "React"}).status_code == 401
