"""Monitoring over HTTP (spec §9.11, §10.2 Monitoring, §17 Phase 9; D150–D152, D155).

Covered: a late critical milestone creates a CRITICAL risk with the deadline impact; evaluating
twice changes nothing and notifies the client and the lead once; a risk resolves when its rule
stops firing; the dashboard is role-shaped (only the client and admins get the budget) and the
cache never serves one shape to another, while events invalidate it; members never see budget
figures or client-only risks; reads never write; the plan carries the forecast for members too;
removal for inactivity works at 10 days and not at 9 (D150); the activity feed and the Evidence
tab carry no money; who may read what.

Modules driven: `app/api/v1/monitoring.py`, `app/services/monitoring.py`, `app/core/cache.py`,
`app/schemas/monitoring.py`, `app/api/v1/test_seed.py` (the D155 routes).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.helpers import Api
from tests.security.formation_world import BASE, _code, _sql
from tests.security.workspace_world import act_as, started_project

pytestmark = [pytest.mark.security, pytest.mark.api]


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    """The started world, begun 4 days ago, with "Build" (5 days, critical) a quarter done: its
    pace forecasts day 16 instead of day 5 (§9.10), so it is late."""
    world = started_project(api, migration_url)
    world["url"] = migration_url
    _sql(
        migration_url,
        "UPDATE projects SET start_date = start_date - 4 WHERE id = :p",
        p=world["pid"],
    )
    _sql(
        migration_url,
        "UPDATE milestones SET actual_start = actual_start - 4 WHERE id = :m",
        m=world["m1"],
    )
    act_as(api, world["lead"])
    ids = []
    for i in range(4):
        r = api.post(
            f"{BASE}/milestones/{world['m1']}/tasks",
            json={
                "title": f"Part {i}",
                "estimate_hours": "2.0",
                "difficulty": "EASY",
                "assignee_id": world["member"].user_id,
            },
        )
        assert r.status_code == 201, r.text
        ids.append(r.json())
    task = ids[0]
    for status in ("IN_PROGRESS", "REVIEW", "DONE"):
        moved = api.post(
            f"{BASE}/tasks/{task['id']}/move",
            json={"status": status},
            headers={"If-Match": str(task["version"])},
        )
        assert moved.status_code == 200, moved.text
        task = moved.json()
    world["tasks"] = ids
    return world


def _evaluate(api: Api, w: dict[str, Any], as_of: datetime | None = None) -> dict[str, Any]:
    body = {"as_of": as_of.isoformat()} if as_of else {}
    r = api.post(f"{BASE}/__test__/projects/{w['pid']}/monitoring/evaluate", json=body)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _count(url: str, table: str, pid: str) -> int:
    return int(_sql(url, f"SELECT count(*) FROM {table} WHERE project_id = :p", p=pid)[0][0])  # noqa: S608 - fixed table names


def test_FR_MON_5_a_late_critical_milestone_opens_a_critical_risk(  # noqa: N802
    api: Api, w: dict[str, Any]
) -> None:
    result = _evaluate(api, w)
    assert result["critical_opened"] >= 1
    assert result["impact_days"] == 11  # forecast day 16 vs a 5-day plan
    act_as(api, w["client"])
    risks = api.get(f"{BASE}/projects/{w['pid']}/risks").json()["items"]
    kinds = {(x["type"], x["severity"]) for x in risks}
    assert ("CRITICAL_PATH_DELAY", "CRITICAL") in kinds
    assert ("DEADLINE_IMPACT", "CRITICAL") in kinds  # 11 days > 10% of 5
    delay = next(x for x in risks if x["type"] == "CRITICAL_PATH_DELAY")
    assert delay["title"] == "Build late pushes the deadline by 11 days"
    assert delay["why"]
    assert risks[0]["severity"] == "CRITICAL"  # worst first


def test_evaluating_twice_changes_nothing_and_notifies_once(api: Api, w: dict[str, Any]) -> None:
    _evaluate(api, w)
    before = _sql(
        w["url"],
        "SELECT id, severity, status FROM risks WHERE project_id = :p ORDER BY id",
        p=w["pid"],
    )
    second = _evaluate(api, w)
    assert second["critical_opened"] == 0
    after = _sql(
        w["url"],
        "SELECT id, severity, status FROM risks WHERE project_id = :p ORDER BY id",
        p=w["pid"],
    )
    assert before == after
    assert _count(w["url"], "forecast_snapshots", w["pid"]) == 1  # one per day, upserted
    for who in ("client", "lead"):
        act_as(api, w[who])
        notes = [
            n
            for n in api.get(f"{BASE}/notifications").json()["items"]
            if n["type"] == "RISK_CRITICAL"
        ]
        assert len(notes) == 2, who  # the two CRITICAL risks, each told once
    act_as(api, w["member"])
    assert not [
        n for n in api.get(f"{BASE}/notifications").json()["items"] if n["type"] == "RISK_CRITICAL"
    ]


def test_a_risk_resolves_when_its_rule_stops_firing(api: Api, w: dict[str, Any]) -> None:
    _evaluate(api, w)
    # Put the start back to today: Build is on time again.
    _sql(w["url"], "UPDATE projects SET start_date = start_date + 4 WHERE id = :p", p=w["pid"])
    _sql(w["url"], "UPDATE milestones SET actual_start = actual_start + 4 WHERE id = :m", m=w["m1"])
    _evaluate(api, w)
    rows = _sql(
        w["url"],
        "SELECT type, status, resolved_at IS NOT NULL FROM risks "
        "WHERE project_id = :p AND type = 'CRITICAL_PATH_DELAY'",
        p=w["pid"],
    )
    assert [tuple(r) for r in rows] == [("CRITICAL_PATH_DELAY", "RESOLVED", True)]


def test_the_dashboard_is_role_shaped_and_never_shared(api: Api, w: dict[str, Any]) -> None:
    _evaluate(api, w)
    act_as(api, w["client"])
    client = api.get(f"{BASE}/projects/{w['pid']}/dashboard").json()
    assert client["view"] == "client"
    assert client["budget"]["budget_paisa"] == 1_000_000
    assert client["budget"]["released_paisa"] == 0  # escrow arrives in Phase 10
    assert client["health"] in ("AT_RISK", "CRITICAL")
    assert client["tasks"] == {"todo": 3, "in_progress": 0, "review": 0, "done": 1}
    act_as(api, w["member"])  # right after the client's response was cached
    member = api.get(f"{BASE}/projects/{w['pid']}/dashboard")
    assert member.json()["view"] == "member"
    assert "budget" not in member.json()
    assert "_paisa" not in member.text
    # An event invalidates the cache: the counts change at once.
    act_as(api, w["lead"])
    t = w["tasks"][1]
    moved = api.post(
        f"{BASE}/tasks/{t['id']}/move",
        json={"status": "IN_PROGRESS"},
        headers={"If-Match": str(t["version"])},
    )
    assert moved.status_code == 200
    again = api.get(f"{BASE}/projects/{w['pid']}/dashboard").json()
    assert again["tasks"]["in_progress"] == 1


def test_members_never_see_money_or_client_only_risks(api: Api, w: dict[str, Any]) -> None:
    _evaluate(api, w)
    _sql(
        w["url"],
        "INSERT INTO risks (project_id, type, severity, entity_type, title, opened_at) "
        "VALUES (:p, 'BUDGET', 'MEDIUM', 'PROJECT', 'Spending is ahead of progress', now())",
        p=w["pid"],
    )
    act_as(api, w["client"])
    assert any(
        x["type"] == "BUDGET" for x in api.get(f"{BASE}/projects/{w['pid']}/risks").json()["items"]
    )
    act_as(api, w["member"])
    for path in ("risks", "dashboard", "activity", "evidence", "plan"):
        r = api.get(f"{BASE}/projects/{w['pid']}/{path}")
        assert r.status_code == 200, (path, r.text)
        assert "_paisa" not in r.text or path == "plan", path
        assert "BUDGET" not in r.text, path


def test_reads_never_write(api: Api, w: dict[str, Any]) -> None:
    """No evaluation yet: the dashboard and the plan compute in memory and store nothing."""
    act_as(api, w["client"])
    before = (_count(w["url"], "risks", w["pid"]), _count(w["url"], "forecast_snapshots", w["pid"]))
    dash = api.get(f"{BASE}/projects/{w['pid']}/dashboard").json()
    assert dash["evaluated_at"] is None
    assert dash["forecast"]["impact_days"] == 11
    plan = api.get(f"{BASE}/projects/{w['pid']}/plan").json()
    assert plan["forecast"]["finish_day"] == 16
    api.get(f"{BASE}/projects/{w['pid']}/risks")
    api.get(f"{BASE}/projects/{w['pid']}/activity")
    after = (_count(w["url"], "risks", w["pid"]), _count(w["url"], "forecast_snapshots", w["pid"]))
    assert before == after == (0, 0)


def test_FR_PROJ_6_members_read_the_plan_with_its_forecast(api: Api, w: dict[str, Any]) -> None:  # noqa: N802
    _evaluate(api, w)
    act_as(api, w["member"])
    plan = api.get(f"{BASE}/projects/{w['pid']}/plan")
    assert plan.status_code == 200, plan.text
    forecast = plan.json()["forecast"]
    build = next(n for n in forecast["nodes"] if n["key"] == w["m1"])
    assert (build["status"], build["progress_pct"], build["forecast_ef"]) == ("ACTIVE", 25, 16)
    assert forecast["impact_days"] == 11
    for who in ("outsider", "former"):
        act_as(api, w[who])
        assert api.get(f"{BASE}/projects/{w['pid']}/plan").status_code == 404, who


def test_removal_for_inactivity_at_ten_days_not_nine(api: Api, w: dict[str, Any]) -> None:
    """D150: the member's last activity decides (here: the task moves above were the lead's)."""
    joined = datetime.now(UTC) - timedelta(days=9, hours=1)
    _sql(
        w["url"],
        "UPDATE team_members SET joined_at = :j WHERE id = :m",
        j=joined,
        m=w["member_member"],
    )
    act_as(api, w["client"])
    body = {"reason": "No check-ins or task updates for days.", "basis": "INACTIVITY"}
    nine = api.post(f"{BASE}/team-members/{w['member_member']}/removal-requests", json=body)
    assert (nine.status_code, _code(nine)) == (409, "INVALID_STATE")
    assert "9 days" in nine.json()["error"]["message"]
    _sql(
        w["url"],
        "UPDATE team_members SET joined_at = :j WHERE id = :m",
        j=joined - timedelta(days=1),
        m=w["member_member"],
    )
    ten = api.post(f"{BASE}/team-members/{w['member_member']}/removal-requests", json=body)
    assert ten.status_code == 201, ten.text
    # The suggestion never starts a repair by itself (§9.9).
    assert not _sql(
        w["url"],
        "SELECT 1 FROM repair_proposals rp JOIN teams t ON t.id = "
        "rp.team_id WHERE t.project_id = :p",
        p=w["pid"],
    )


def test_activity_and_evidence(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["client"])
    feed = api.get(f"{BASE}/projects/{w['pid']}/activity?limit=2").json()
    assert len(feed["items"]) == 2
    assert feed["next_cursor"]
    assert feed["items"][0]["summary"]
    rest = api.get(f"{BASE}/projects/{w['pid']}/activity?cursor={feed['next_cursor']}").json()
    assert {x["id"] for x in rest["items"]}.isdisjoint({x["id"] for x in feed["items"]})
    evidence = api.get(f"{BASE}/projects/{w['pid']}/evidence").json()["members"]
    member = next(m for m in evidence if m["member"]["id"] == w["member"].user_id)
    assert (member["tasks_done"], member["hours_done"]) == (1, "2.0")  # credited to the assignee
    assert "price" not in json.dumps(evidence)
    assert api.get(f"{BASE}/projects/{w['pid']}/activity?sort=new").status_code == 400


def test_who_may_read_monitoring(api: Api, w: dict[str, Any]) -> None:
    for who in ("outsider", "former", "other_client"):
        act_as(api, w[who])
        for path in ("dashboard", "risks", "activity", "evidence"):
            assert api.get(f"{BASE}/projects/{w['pid']}/{path}").status_code == 404, (who, path)
    api.sign_in_as("ADMIN")
    dash = api.get(f"{BASE}/projects/{w['pid']}/dashboard")
    assert dash.status_code == 200
    assert dash.json()["view"] == "client"  # admins read the full view (§2.2 read-only)
