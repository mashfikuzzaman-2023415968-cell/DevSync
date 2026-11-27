"""A started project for the Phase 9 workspace tests, built directly in the database.

Forming a team through the API takes a formation run per test (seconds each, see
`formation_world.py`); the workspace tests only need its result. So the rows a started project
has — project IN_PROGRESS since today (Asia/Dhaka), an ACTIVE and a PLANNED milestone (plus an
approved one), a team with an ACTIVE lead, an ACTIVE member and a member who LEFT, their accepted
bids — are inserted as the migrator. Everyone then acts through the real API: the client, the
lead, the member, the former member, an outsider developer, another client and an admin.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.clock import DISPLAY_TZ
from tests.helpers import Api, SeededUser
from tests.security.formation_world import BASE, _sql


def reset_limits(api: Api) -> None:
    assert api.get(f"{BASE}/__test__/ratelimits/reset").status_code == 204


def act_as(api: Api, user: SeededUser) -> None:
    """Sign `api` in as `user` (after resetting the sign-in limits)."""
    reset_limits(api)
    r = api.login(user)
    assert r.status_code == 200, r.text


def _insert_world(url: str, people: dict[str, SeededUser]) -> dict[str, str]:
    ids = {
        k: str(uuid.uuid4())
        for k in (
            "pid",
            "slot",
            "m1",
            "m2",
            "m3",
            "run",
            "team",
            "bid_lead",
            "bid_member",
            "bid_former",
            "lead_member",
            "member_member",
            "former_member",
        )
    }
    today = datetime.now(UTC).astimezone(DISPLAY_TZ).date()
    skill = _sql(url, "SELECT id FROM skills ORDER BY name LIMIT 1")[0][0]
    stmts = [
        (
            "INSERT INTO projects (id, client_id, title, budget_paisa, deadline_days, team_size, "
            "status, start_date) VALUES (:pid, :client, 'Inventory board', 1000000, 30, 3, "
            "'IN_PROGRESS', :today)"
        ),
        "INSERT INTO project_slots (id, project_id, skill_id, label, count) "
        "VALUES (:slot, :pid, :skill, 'Developer', 3)",
        "INSERT INTO milestones (id, project_id, name, duration_days, share_bp, position, status, "
        "actual_start) VALUES (:m1, :pid, 'Build', 5, 5000, 0, 'ACTIVE', :today), "
        "(:m2, :pid, 'Test', 3, 3000, 1, 'PLANNED', NULL), "
        "(:m3, :pid, 'Design', 2, 2000, 2, 'APPROVED', :today)",
        "INSERT INTO formation_runs (id, project_id, requested_by, status, settings_version, "
        "seed, params, candidate_snapshot) VALUES (:run, :pid, :client, 'SUCCEEDED', 6, 1, "
        "'{}', '{}')",
        "INSERT INTO teams (id, project_id, run_id, status, confirmed_at) "
        "VALUES (:team, :pid, :run, 'ACTIVE', now())",
        "INSERT INTO bids (id, project_id, developer_id, slot_id, price_paisa, days_needed, "
        "hours_per_week_committed, status) VALUES "
        "(:bid_lead, :pid, :lead, :slot, 300000, 20, 20, 'ACCEPTED'), "
        "(:bid_member, :pid, :member, :slot, 300000, 20, 20, 'ACCEPTED'), "
        "(:bid_former, :pid, :former, :slot, 300000, 20, 20, 'ACCEPTED')",
        "INSERT INTO team_members (id, team_id, developer_id, bid_id, slot_id, price_paisa, "
        "days_needed, is_lead, status, joined_at, left_at) VALUES "
        "(:lead_member, :team, :lead, :bid_lead, :slot, 300000, 20, true, 'ACTIVE', now(), NULL), "
        "(:member_member, :team, :member, :bid_member, :slot, 300000, 20, false, 'ACTIVE', now(), "
        "NULL), "
        "(:former_member, :team, :former, :bid_former, :slot, 300000, 20, false, 'LEFT', now(), "
        "now())",
    ]
    params: dict[str, Any] = {
        **ids,
        "client": people["client"].user_id,
        "lead": people["lead"].user_id,
        "member": people["member"].user_id,
        "former": people["former"].user_id,
        "skill": skill,
        "today": today,
    }
    for stmt in stmts:
        _sql(url, stmt, **params)
    return ids


def started_project(api: Api, migration_url: str) -> dict[str, Any]:
    """Seed the people and the started project; `api` is left signed in as the client."""
    people = {
        "client": api.seed("CLIENT"),
        "lead": api.seed("DEVELOPER"),
        "member": api.seed("DEVELOPER"),
        "former": api.seed("DEVELOPER"),
        "outsider": api.seed("DEVELOPER"),
        "other_client": api.seed("CLIENT"),
    }
    ids = _insert_world(migration_url, people)
    act_as(api, people["client"])
    return {**ids, **people}


def set_project_status(url: str, pid: str, status: str) -> None:
    _sql(
        url,
        "UPDATE projects SET status = CAST(:s AS project_status) WHERE id = :pid",
        s=status,
        pid=pid,
    )


def events(url: str, pid: str, event_type: str) -> list[dict[str, Any]]:
    rows = _sql(
        url,
        "SELECT actor_id, subject_id, data FROM activity_events "
        "WHERE project_id = :pid AND type = :t ORDER BY at, id",
        pid=pid,
        t=event_type,
    )
    return [
        {"actor_id": str(a) if a else None, "subject_id": str(s) if s else None, "data": d}
        for a, s, d in rows
    ]


def audits(url: str, entity_id: str, action: str) -> int:
    rows = _sql(
        url,
        "SELECT count(*) FROM audit_log WHERE entity_id = :e AND action = :a",
        e=entity_id,
        a=action,
    )
    return int(rows[0][0])
