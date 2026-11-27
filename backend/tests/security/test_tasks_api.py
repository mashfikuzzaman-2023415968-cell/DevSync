"""Tasks over HTTP (spec §8 Task, §10.2 Tasks, §14.13 row 9, §17 Phase 9; D142–D144, D148,
D168, D172, D173). The world is a started project built in the database
(`workspace_world.py`); every action goes through the API as a real signed-in user.

Covered: who may create, edit, move, delete (lead / assignee / other member / client / former
member / outsider / admin), one-step moves, the active-milestone rule, dependency rules (DONE
waits for dependencies, leaving DONE waits for dependents, same milestone, cycles, the cap),
required and stale `If-Match`, evidence rules, the audit trail and evidence events, mass
assignment, unknown query parameters and limits, and IDOR on task ids.

Modules driven: `app/api/v1/tasks.py`, `app/services/tasks.py`, `app/services/workspace.py`,
`app/services/activity.py` (events through the definer), `app/schemas/tasks.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import Api
from tests.security.formation_world import BASE, UNKNOWN, _code
from tests.security.workspace_world import (
    act_as,
    audits,
    events,
    set_project_status,
    started_project,
)

pytestmark = [pytest.mark.security, pytest.mark.api]


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    world = started_project(api, migration_url)
    world["url"] = migration_url
    return world


def _create(api: Api, milestone: str, title: str = "Stock list API", **extra: Any) -> Any:
    body = {"title": title, "estimate_hours": "8.0", "difficulty": "MEDIUM", **extra}
    return api.post(f"{BASE}/milestones/{milestone}/tasks", json=body)


def _task(
    api: Api, w: dict[str, Any], title: str = "Stock list API", **extra: Any
) -> dict[str, Any]:
    act_as(api, w["lead"])
    r = _create(api, w["m1"], title, **extra)
    assert r.status_code == 201, r.text
    return dict(r.json())


def _move(api: Api, task: dict[str, Any], status: str, **body: Any) -> Any:
    return api.post(
        f"{BASE}/tasks/{task['id']}/move",
        json={"status": status, **body},
        headers={"If-Match": str(task["version"])},
    )


def _fresh(api: Api, task_id: str) -> dict[str, Any]:
    r = api.get(f"{BASE}/tasks/{task_id}")
    assert r.status_code == 200, r.text
    return dict(r.json())


# ------------------------------------------------------------------------------ who may create


def test_only_the_lead_creates_tasks(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w, assignee_id=w["member"].user_id)
    assert (task["status"], task["progress_pct"], task["position"]) == ("TODO", 0, "V")
    assert task["assignee"]["id"] == w["member"].user_id
    assert task["can_edit"] is True
    assert audits(w["url"], task["id"], "task.create") == 1
    for who, code in (
        ("client", 403),
        ("member", 403),
        ("former", 404),
        ("outsider", 404),
        ("other_client", 403),
    ):
        act_as(api, w[who])
        r = _create(api, w["m1"], "Forbidden")
        assert r.status_code == code, (who, r.text)
    act_as(api, w["member"])  # the assignee was told
    notes = api.get(f"{BASE}/notifications").json()["items"]
    assert any(n["type"] == "TASK_ASSIGNED" and task["id"] in n["link_path"] for n in notes)


def test_an_admin_cannot_create_or_move(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w)
    api.sign_in_as("ADMIN")
    assert _create(api, w["m1"], "Admin task").status_code == 403
    assert _move(api, task, "IN_PROGRESS").status_code == 403
    assert api.get(f"{BASE}/tasks/{task['id']}").status_code == 200  # reads progress (§2.2)


def test_create_rules(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["lead"])
    finished = _create(api, w["m3"], "Late addition")
    assert (finished.status_code, _code(finished)) == (409, "MILESTONE_FINISHED")
    for bad in (w["former"].user_id, w["outsider"].user_id, w["client"].user_id):
        r = _create(api, w["m1"], "Assigned badly", assignee_id=bad)
        assert (r.status_code, _code(r)) == (422, "VALIDATION_ERROR"), r.text
    early = _create(api, w["m1"], "Too early", deadline="2000-01-01")
    assert early.status_code == 422
    for title in ("", "x" * 161):
        assert _create(api, w["m1"], title).status_code == 422
    assert _create(api, w["m1"], "x" * 160).status_code == 201
    for estimate in ("0", "0.0", "1000.0", "1.25", "-1"):
        assert _create(api, w["m1"], "Bad estimate", estimate_hours=estimate).status_code == 422
    assert _create(api, w["m1"], "Biggest", estimate_hours="999.9").status_code == 201
    long = _create(api, w["m1"], "Long", description="d" * 5001)
    assert long.status_code == 422


@pytest.mark.parametrize(
    "field",
    [
        {"status": "DONE"},
        {"position": "0"},
        {"progress_pct": 100},
        {"project_id": "00000000-0000-4000-8000-000000000000"},
        {"created_by": "00000000-0000-4000-8000-000000000000"},
        {"version": 7},
    ],
)
def test_mass_assignment_is_refused(api: Api, w: dict[str, Any], field: dict[str, Any]) -> None:
    act_as(api, w["lead"])
    assert _create(api, w["m1"], "Mass", **field).status_code == 422


def test_writes_need_the_project_in_progress(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w)
    set_project_status(w["url"], w["pid"], "ON_HOLD")
    r = _create(api, w["m1"], "On hold")
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")
    assert _move(api, task, "IN_PROGRESS").status_code == 409
    assert api.get(f"{BASE}/tasks/{task['id']}").status_code == 200  # reading still works


# ------------------------------------------------------------------------------ moves


def test_FR_MON_1_move_permissions(api: Api, w: dict[str, Any]) -> None:  # noqa: N802
    mine = _task(api, w, "Member's task", assignee_id=w["member"].user_id)
    unassigned = _task(api, w, "Nobody's task")
    act_as(api, w["client"])
    r = _move(api, mine, "IN_PROGRESS")
    assert r.status_code == 403  # the client watches (§1.6)
    act_as(api, w["member"])
    assert _move(api, unassigned, "IN_PROGRESS").status_code == 403  # only the lead
    moved = _move(api, mine, "IN_PROGRESS")
    assert moved.status_code == 200, moved.text
    assert (moved.json()["status"], moved.json()["progress_pct"]) == ("IN_PROGRESS", 50)
    act_as(api, w["lead"])  # the lead moves anyone's
    lead_moved = _move(api, moved.json(), "REVIEW")
    assert (lead_moved.status_code, lead_moved.json()["progress_pct"]) == (200, 85)
    for who, code in (("former", 404), ("outsider", 404)):
        act_as(api, w[who])
        assert _move(api, lead_moved.json(), "DONE").status_code == code


def test_moves_are_one_step_at_a_time(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w)
    skip = _move(api, task, "REVIEW")
    assert (skip.status_code, _code(skip)) == (409, "ONE_STEP_ONLY")
    assert "In progress" in skip.json()["error"]["message"]
    detail = _fresh(api, task["id"])
    refused = {o["status"]: o for o in detail["can_move_to"]}
    assert refused["IN_PROGRESS"]["allowed"] is True
    assert refused["DONE"]["allowed"] is False
    assert refused["DONE"]["reason"] == "Move it to In progress first."
    path = ["IN_PROGRESS", "REVIEW", "DONE", "REVIEW", "IN_PROGRESS", "TODO"]
    current = task
    for status in path:
        r = _move(api, current, status)
        assert r.status_code == 200, (status, r.text)
        current = r.json()
    assert audits(w["url"], task["id"], "task.move") == len(path)
    assert len(events(w["url"], w["pid"], "task.done")) == 1
    assert len(events(w["url"], w["pid"], "task.reopened")) == 1


def test_FR_MON_2_work_starts_only_in_an_active_milestone(api: Api, w: dict[str, Any]) -> None:  # noqa: N802
    act_as(api, w["lead"])
    planned = _create(api, w["m2"], "Later work").json()
    r = _move(api, planned, "IN_PROGRESS")
    assert (r.status_code, _code(r)) == (409, "MILESTONE_NOT_ACTIVE")


def test_if_match_is_required_and_checked(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w)
    missing = api.post(f"{BASE}/tasks/{task['id']}/move", json={"status": "IN_PROGRESS"})
    assert (missing.status_code, _code(missing)) == (422, "VALIDATION_ERROR")
    stale = api.post(
        f"{BASE}/tasks/{task['id']}/move",
        json={"status": "IN_PROGRESS"},
        headers={"If-Match": str(task["version"] - 1)},
    )
    assert (stale.status_code, _code(stale)) == (409, "VERSION_CONFLICT")
    assert _fresh(api, task["id"])["status"] == "TODO"  # nothing changed


def test_evidence_events_credit_the_assignee(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w, assignee_id=w["member"].user_id)
    act_as(api, w["lead"])
    started = _move(api, task, "IN_PROGRESS")
    assert started.status_code == 200
    work = events(w["url"], w["pid"], "work.started")
    assert len(work) == 1
    assert work[0]["actor_id"] == w["lead"].user_id
    assert work[0]["subject_id"] == w["member"].user_id
    moved = events(w["url"], w["pid"], "task.moved")[-1]["data"]
    assert moved["estimate_hours"] == "8.0"
    assert moved["assignee_id"] == w["member"].user_id
    assert set(moved) == {
        "task_id",
        "milestone_id",
        "assignee_id",
        "estimate_hours",
        "from_status",
        "to_status",
    }


def test_reordering_within_a_column(api: Api, w: dict[str, Any]) -> None:
    a = _task(api, w, "A")
    b = _task(api, w, "B")
    c = _task(api, w, "C")
    assert a["position"] < b["position"] < c["position"]
    r = _move(api, c, "TODO", after_id=a["id"], before_id=b["id"])
    assert r.status_code == 200, r.text
    assert a["position"] < r.json()["position"] < b["position"]
    board = api.get(f"{BASE}/projects/{w['pid']}/tasks").json()["items"]
    assert [t["title"] for t in board] == ["A", "C", "B"]
    wrong = _move(api, _fresh(api, a["id"]), "IN_PROGRESS", after_id=b["id"])
    assert wrong.status_code == 422  # neighbours must be in the target column
    gap = _move(api, _fresh(api, b["id"]), "TODO", after_id=a["id"], before_id=b["id"])
    assert gap.status_code == 422


# ------------------------------------------------------------------------------ dependencies


def test_dependency_rules(api: Api, w: dict[str, Any]) -> None:
    first = _task(api, w, "Schema")
    second = _task(api, w, "Endpoints")
    dep = api.post(
        f"{BASE}/tasks/{second['id']}/dependencies", json={"depends_on_task_id": first["id"]}
    )
    assert dep.status_code == 201, dep.text
    cycle = api.post(
        f"{BASE}/tasks/{first['id']}/dependencies", json={"depends_on_task_id": second["id"]}
    )
    assert (cycle.status_code, _code(cycle)) == (409, "DEPENDENCY_CYCLE")
    assert "“Schema” → “Endpoints” → “Schema”" in cycle.json()["error"]["fields"]["cycle"]
    act_as(api, w["lead"])
    other = _create(api, w["m2"], "Elsewhere").json()
    cross = api.post(
        f"{BASE}/tasks/{second['id']}/dependencies", json={"depends_on_task_id": other["id"]}
    )
    assert cross.status_code == 422
    current = _fresh(api, second["id"])
    for status in ("IN_PROGRESS", "REVIEW"):
        current = _move(api, current, status).json()
    blocked = _move(api, current, "DONE")
    assert (blocked.status_code, _code(blocked)) == (409, "DEPENDENCIES_NOT_DONE")
    assert blocked.json()["error"]["fields"]["tasks"] == "“Schema”"
    f = first
    for status in ("IN_PROGRESS", "REVIEW", "DONE"):
        f = _move(api, f, status).json()
    done = _move(api, current, "DONE")
    assert done.status_code == 200
    reopen = _move(api, f, "REVIEW")
    assert (reopen.status_code, _code(reopen)) == (409, "DEPENDENTS_DONE")
    assert reopen.json()["error"]["fields"]["tasks"] == "“Endpoints”"


def test_at_most_twenty_dependencies(api: Api, w: dict[str, Any]) -> None:
    main = _task(api, w, "Main")
    for i in range(20):
        other = _create(api, w["m1"], f"Part {i}").json()
        r = api.post(
            f"{BASE}/tasks/{main['id']}/dependencies", json={"depends_on_task_id": other["id"]}
        )
        assert r.status_code == 201, (i, r.text)
    extra = _create(api, w["m1"], "Part 20").json()
    r = api.post(
        f"{BASE}/tasks/{main['id']}/dependencies", json={"depends_on_task_id": extra["id"]}
    )
    assert (r.status_code, _code(r)) == (409, "LIMIT_REACHED")
    too_many = _create(api, w["m1"], "Many", depends_on_ids=[UNKNOWN] * 21)
    assert too_many.status_code == 422


# ------------------------------------------------------------------------------ evidence, delete


def test_FR_MON_3_evidence_rules(api: Api, w: dict[str, Any]) -> None:  # noqa: N802
    task = _task(api, w, assignee_id=w["member"].user_id)
    act_as(api, w["member"])
    ok = api.post(
        f"{BASE}/tasks/{task['id']}/evidence",
        json={"kind": "PR", "url": "https://github.com/acme/inventory/pull/12", "note": "Paging"},
    )
    assert ok.status_code == 201, ok.text
    bad = [
        {"kind": "LINK", "url": "http://example.com/x"},
        {"kind": "LINK", "url": "javascript:alert(1)"},
        {"kind": "PR", "url": "https://gitlab.com/acme/inventory/pull/12"},
        {"kind": "LINK", "url": "https://example.com/" + "a" * 2048},
        {"kind": "FILE", "url": "https://example.com/x"},
        {"kind": "FILE", "file_id": UNKNOWN},
        {"kind": "LINK", "url": "https://example.com", "note": "n" * 501},
    ]
    for body in bad:
        r = api.post(f"{BASE}/tasks/{task['id']}/evidence", json=body)
        assert r.status_code == 422, (body, r.text)
    assert len(events(w["url"], w["pid"], "task.evidence_added")) == 1
    act_as(api, w["client"])
    r = api.post(
        f"{BASE}/tasks/{task['id']}/evidence", json={"kind": "LINK", "url": "https://example.com"}
    )
    assert r.status_code == 403
    act_as(api, w["lead"])
    blocked = api.delete(f"{BASE}/tasks/{task['id']}", headers={"If-Match": "1"})
    assert (blocked.status_code, _code(blocked)) == (409, "INVALID_STATE")  # D173


def test_delete_rules(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w)
    act_as(api, w["member"])
    assert api.delete(f"{BASE}/tasks/{task['id']}", headers={"If-Match": "1"}).status_code == 403
    act_as(api, w["lead"])
    no_version = api.delete(f"{BASE}/tasks/{task['id']}")
    assert no_version.status_code == 422
    gone = api.delete(f"{BASE}/tasks/{task['id']}", headers={"If-Match": "1"})
    assert gone.status_code == 204
    assert audits(w["url"], task["id"], "task.delete") == 1
    assert api.get(f"{BASE}/tasks/{task['id']}").status_code == 404
    done = _task(api, w, "Finished")
    for status in ("IN_PROGRESS", "REVIEW", "DONE"):
        done = _move(api, done, status).json()
    r = api.delete(f"{BASE}/tasks/{done['id']}", headers={"If-Match": str(done["version"])})
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")


def test_editing_and_moving_milestones(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w, assignee_id=w["member"].user_id)
    r = api.patch(
        f"{BASE}/tasks/{task['id']}",
        json={"assignee_id": None, "milestone_id": w["m2"]},
        headers={"If-Match": str(task["version"])},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["assignee"], r.json()["milestone_id"]) == (None, w["m2"])
    assert audits(w["url"], task["id"], "task.reassign") == 1
    to_done = api.patch(
        f"{BASE}/tasks/{task['id']}",
        json={"milestone_id": w["m3"]},
        headers={"If-Match": str(r.json()["version"])},
    )
    assert (to_done.status_code, _code(to_done)) == (409, "MILESTONE_FINISHED")
    empty = api.patch(
        f"{BASE}/tasks/{task['id']}", json={}, headers={"If-Match": str(r.json()["version"])}
    )
    assert empty.status_code == 422
    act_as(api, w["member"])
    r2 = api.patch(
        f"{BASE}/tasks/{task['id']}",
        json={"title": "Mine now"},
        headers={"If-Match": str(r.json()["version"])},
    )
    assert r2.status_code == 403


# ------------------------------------------------------------------------------ lists and ids


def test_lists_take_only_their_parameters(api: Api, w: dict[str, Any]) -> None:
    _task(api, w)
    base = f"{BASE}/projects/{w['pid']}/tasks"
    assert api.get(base).status_code == 200
    assert api.get(f"{base}?sort=title").status_code == 400
    assert api.get(f"{base}?status=TODO&status=DONE").status_code == 400
    assert api.get(f"{base}?limit=101").status_code == 422
    assert api.get(f"{base}?limit=0").status_code == 422
    assert api.get(f"{base}?cursor=not-a-cursor").status_code == 400
    assert api.get(f"{base}?status=FINISHED").status_code == 422
    mine = api.get(f"{base}?mine=true").json()["items"]
    assert mine == []  # the lead has no tasks assigned
    assert api.get(f"{BASE}/milestones/{w['m1']}/tasks?mine=true").status_code == 400


def test_paging_is_a_total_order(api: Api, w: dict[str, Any]) -> None:
    titles = [f"T{i}" for i in range(5)]
    for t in titles:
        _task(api, w, t)
    seen: list[str] = []
    cursor = None
    while True:
        q = f"?limit=2&cursor={cursor}" if cursor else "?limit=2"
        page = api.get(f"{BASE}/projects/{w['pid']}/tasks{q}").json()
        seen += [t["title"] for t in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == titles


def test_a_leaving_member_hands_back_their_tasks(api: Api, w: dict[str, Any]) -> None:
    """Phase 8's leave now records `member.left` (without the reason) and unassigns the member's
    unfinished tasks, telling the lead (D143, D149)."""
    open_task = _task(api, w, "Open", assignee_id=w["member"].user_id)
    finished = _task(api, w, "Finished", assignee_id=w["member"].user_id)
    for status in ("IN_PROGRESS", "REVIEW", "DONE"):
        finished = _move(api, finished, status).json()
    act_as(api, w["member"])
    reason = "I have to stop working on this project for family reasons."
    left = api.post(f"{BASE}/team-members/{w['member_member']}/leave", json={"reason": reason})
    assert left.status_code == 200, left.text
    act_as(api, w["lead"])
    assert _fresh(api, open_task["id"])["assignee"] is None
    assert _fresh(api, finished["id"])["assignee"]["id"] == w["member"].user_id  # done stays
    gone = events(w["url"], w["pid"], "member.left")
    assert len(gone) == 1
    assert gone[0]["subject_id"] == w["member"].user_id
    assert gone[0]["data"]["how"] == "LEFT"
    assert reason not in str(gone[0]["data"])
    notes = api.get(f"{BASE}/notifications").json()["items"]
    assert any(n["type"] == "TASKS_UNASSIGNED" for n in notes)


def test_tasks_of_other_projects_are_404(api: Api, w: dict[str, Any]) -> None:
    task = _task(api, w)
    for who in ("outsider", "other_client", "former"):
        act_as(api, w[who])
        assert api.get(f"{BASE}/tasks/{task['id']}").status_code == 404, who
        assert api.get(f"{BASE}/projects/{w['pid']}/tasks").status_code == 404, who
        assert api.get(f"{BASE}/milestones/{w['m1']}/tasks").status_code == 404, who
    act_as(api, w["client"])
    assert api.get(f"{BASE}/tasks/{UNKNOWN}").status_code == 404
    detail = _fresh(api, task["id"])
    assert detail["can_move_to"] == []  # the client has no task actions
    assert detail["can_edit"] is False
