"""`GET /me/projects` (spec §13.5 #13, #9; plan endpoint 29).

Covered: an active member and the lead see the project with their slot and lead flag, progress,
health, risk and the next deadline from the member-shaped dashboard (never money); a member who
left and an outsider see nothing; clients 403; a project not started yet shows no progress;
`completed` lists finished memberships; unknown and repeated parameters, bad cursors and limits.

Modules driven: `app/api/v1/monitoring.py` (`/me/projects`), `app/services/my_projects.py`,
`app/schemas/monitoring.py` (MyProject).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import Api
from tests.security.formation_world import BASE, _code, _sql
from tests.security.workspace_world import act_as, set_project_status, started_project

pytestmark = [pytest.mark.security, pytest.mark.api]


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    world = started_project(api, migration_url)
    world["url"] = migration_url
    return world


def _mine(api: Api, query: str = "") -> list[dict[str, Any]]:
    r = api.get(f"{BASE}/me/projects{query}")
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def test_members_see_their_project_with_progress_and_risk(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    items = [i for i in _mine(api) if i["project_id"] == w["pid"]]
    assert len(items) == 1
    item = items[0]
    assert (item["title"], item["status"], item["role"], item["is_lead"]) == (
        "Inventory board",
        "IN_PROGRESS",
        "Developer",
        False,
    )
    assert 0 <= item["progress_pct"] <= 100
    assert item["health"] in ("HEALTHY", "AT_RISK", "CRITICAL")
    board = api.get(f"{BASE}/projects/{w['pid']}/dashboard").json()  # the same numbers
    assert item["progress_pct"] == board["progress_pct"]
    assert item["overall_risk"] == board["overall_risk"]
    assert item["next_milestone"] == board["next_milestone"]["name"]
    assert item["next_deadline"] in (
        board["next_milestone"]["forecast_finish_date"],
        board["next_milestone"]["planned_finish_date"],
    )
    text = api.get(f"{BASE}/me/projects").text
    assert "_paisa" not in text
    assert "budget" not in text
    act_as(api, w["lead"])
    lead = next(i for i in _mine(api) if i["project_id"] == w["pid"])
    assert lead["is_lead"] is True


def test_others_see_nothing_and_clients_are_refused(api: Api, w: dict[str, Any]) -> None:
    for who in ("former", "outsider"):
        act_as(api, w[who])
        assert all(i["project_id"] != w["pid"] for i in _mine(api)), who
        assert all(i["project_id"] != w["pid"] for i in _mine(api, "?state=completed")), who
    act_as(api, w["client"])
    r = api.get(f"{BASE}/me/projects")
    assert (r.status_code, _code(r)) == (403, "ROLE_NOT_ALLOWED")


def test_not_started_and_completed(api: Api, w: dict[str, Any]) -> None:
    set_project_status(w["url"], w["pid"], "TEAM_PENDING")
    act_as(api, w["member"])
    pending = next(i for i in _mine(api) if i["project_id"] == w["pid"])
    assert (pending["progress_pct"], pending["overall_risk"], pending["next_deadline"]) == (
        None,
        None,
        None,
    )
    set_project_status(w["url"], w["pid"], "COMPLETED")
    _sql(
        w["url"],
        "UPDATE team_members SET status = 'COMPLETED' WHERE id = :m",
        m=w["member_member"],
    )
    assert all(i["project_id"] != w["pid"] for i in _mine(api))
    done = next(i for i in _mine(api, "?state=completed") if i["project_id"] == w["pid"])
    assert (done["status"], done["progress_pct"]) == ("COMPLETED", 100)


def test_parameters(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    for query in ("?state=all", "?limit=0", "?limit=51", "?cursor=bm9wZQ", "?sort=x",
                  "?state=active&state=completed"):  # fmt: skip
        r = api.get(f"{BASE}/me/projects{query}")
        assert r.status_code in (400, 422), (query, r.status_code)
    assert api.get(f"{BASE}/me/projects?limit=1").status_code == 200
