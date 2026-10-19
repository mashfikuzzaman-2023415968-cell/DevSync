"""Projects and the CPM planner over HTTP (spec §17 Phase 4, §14.13 row 4, §16.4).

Covers the happy path plus boundaries and failures: draft-only editing, optimistic concurrency,
the publish guards (payment, slots, 100% shares, schedule-risk acknowledgement), dependency-cycle
rejection, the §18.2 golden CPM via preview, IDOR (a foreign project is 404), mass assignment and
sealed lifecycle transitions.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]


def _pm(key: str, name: str, dur: int, share: int, *preds: str) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "duration_days": dur,
        "share_bp": share,
        "predecessor_keys": list(preds),
    }


# The §18.2 "Online ordering system" plan, by client key (predecessors by key).
ORDERING = [
    _pm("req", "Requirements", 4, 1000),
    _pm("db", "Database", 5, 1500, "req"),
    _pm("api", "Backend API", 8, 3000, "db"),
    _pm("fe", "Frontend", 9, 2500, "req"),
    _pm("int", "Integration", 3, 1000, "api", "fe"),
    _pm("test", "Testing", 4, 1000, "int"),
]


def _skill_id(api: Api) -> str:
    skills = api.get("/api/v1/skills").json()
    assert skills, "seeded skills expected"
    return skills[0].get("skill_id") or skills[0]["id"]


def _create_draft(api: Api, **over: Any) -> dict[str, Any]:
    body = {
        "title": "Online ordering system",
        "summary": "Order and track restaurant orders.",
        "budget_paisa": 12_000_000,
        "deadline_days": 30,
        "team_size": 2,
    }
    body.update(over)
    r = api.post("/api/v1/projects", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _add_two_milestones(api: Api, pid: str, sid: str) -> list[dict[str, Any]]:
    r = api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- draft CRUD


def test_create_get_and_list_draft(api: Api) -> None:
    api.sign_in_as("CLIENT")
    created = _create_draft(api)
    assert created["status"] == "DRAFT"
    assert created["version"] == 1
    got = api.get(f"/api/v1/projects/{created['id']}")
    assert got.status_code == 200
    assert got.json()["title"] == "Online ordering system"
    listed = api.get("/api/v1/projects")
    assert listed.status_code == 200
    assert any(p["id"] == created["id"] for p in listed.json())


def test_create_rejects_unknown_fields(api: Api) -> None:
    api.sign_in_as("CLIENT")
    r = api.post(
        "/api/v1/projects",
        json={
            "title": "Valid title here",
            "budget_paisa": 1000,
            "deadline_days": 10,
            "team_size": 2,
            "status": "BIDDING",  # mass-assignment attempt
            "client_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert r.status_code == 422, r.text


def test_create_validates_bounds(api: Api) -> None:
    api.sign_in_as("CLIENT")
    r = api.post(
        "/api/v1/projects",
        json={"title": "no", "budget_paisa": -1, "deadline_days": 0, "team_size": 1},
    )
    assert r.status_code == 422


def test_update_bumps_version_and_detects_conflict(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api)["id"]
    ok = api.patch(f"/api/v1/projects/{pid}", json={"summary": "new"}, headers={"If-Match": "1"})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2
    stale = api.patch(
        f"/api/v1/projects/{pid}", json={"summary": "again"}, headers={"If-Match": "1"}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_delete_draft(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api)["id"]
    assert api.delete(f"/api/v1/projects/{pid}").status_code == 204
    assert api.get(f"/api/v1/projects/{pid}").status_code == 404


# --------------------------------------------------------------------------- slots & milestones


def test_slots_auto_sum_team_size_and_bounds(api: Api) -> None:
    api.sign_in_as("CLIENT")
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    ok = api.put(
        f"/api/v1/projects/{pid}/slots",
        json={"slots": [{"skill_id": sid, "label": "Dev", "count": 4}]},
    )
    assert ok.status_code == 200
    assert api.get(f"/api/v1/projects/{pid}").json()["team_size"] == 4
    too_many = api.put(
        f"/api/v1/projects/{pid}/slots",
        json={"slots": [{"skill_id": sid, "count": 11}]},
    )
    assert too_many.status_code == 422
    too_few = api.put(
        f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 1}]}
    )
    assert too_few.status_code == 422


def test_slots_reject_unknown_skill(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api)["id"]
    r = api.put(
        f"/api/v1/projects/{pid}/slots",
        json={"slots": [{"skill_id": "00000000-0000-4000-8000-000000000000", "count": 2}]},
    )
    assert r.status_code == 422


def test_milestones_round_trip(api: Api) -> None:
    api.sign_in_as("CLIENT")
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    milestones = _add_two_milestones(api, pid, sid)
    assert len(milestones) == 2
    assert milestones[0]["skill_ids"] == [sid]
    assert [m["position"] for m in milestones] == [0, 1]


def test_dependency_cycle_rejected(api: Api) -> None:
    api.sign_in_as("CLIENT")
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    m = _add_two_milestones(api, pid, sid)
    r = api.put(
        f"/api/v1/projects/{pid}/dependencies",
        json={
            "dependencies": [
                {"predecessor_id": m[0]["id"], "successor_id": m[1]["id"]},
                {"predecessor_id": m[1]["id"], "successor_id": m[0]["id"]},
            ]
        },
    )
    assert r.status_code == 422
    assert "cycle" in r.json()["error"]["fields"].get("dependencies", "").lower()


def test_dependency_rejects_foreign_milestone(api: Api) -> None:
    api.sign_in_as("CLIENT")
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    m = _add_two_milestones(api, pid, sid)
    r = api.put(
        f"/api/v1/projects/{pid}/dependencies",
        json={
            "dependencies": [
                {
                    "predecessor_id": m[0]["id"],
                    "successor_id": "00000000-0000-4000-8000-000000000000",
                }
            ]
        },
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- CPM preview (§18.2)


def test_preview_matches_spec_18_2(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api)["id"]
    r = api.post(f"/api/v1/projects/{pid}/plan/preview", json={"milestones": ORDERING})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feasible"] is True
    assert data["duration"] == 24
    assert data["total_share_bp"] == 10000
    assert data["warnings"] == []
    assert ["Requirements", "Database", "Backend API", "Integration", "Testing"] in data[
        "critical_paths"
    ]


def test_preview_warns_on_bad_shares_and_cycle(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api)["id"]
    bad_shares = [{**m, "share_bp": 1000} for m in ORDERING]  # total 6000
    warn = api.post(f"/api/v1/projects/{pid}/plan/preview", json={"milestones": bad_shares}).json()
    assert any("100%" in w for w in warn["warnings"])
    cyclic = [
        {"key": "a", "duration_days": 2, "share_bp": 5000, "predecessor_keys": ["b"]},
        {"key": "b", "duration_days": 2, "share_bp": 5000, "predecessor_keys": ["a"]},
    ]
    out = api.post(f"/api/v1/projects/{pid}/plan/preview", json={"milestones": cyclic}).json()
    assert out["feasible"] is False
    assert out["cycle"]


def test_preview_warns_when_over_deadline(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api, deadline_days=5)["id"]
    out = api.post(f"/api/v1/projects/{pid}/plan/preview", json={"milestones": ORDERING}).json()
    assert any("deadline" in w for w in out["warnings"])


# --------------------------------------------------------------------------- publish & lifecycle


def _ready_to_publish(api: Api) -> str:
    """Build a complete, valid plan and verify payment; returns the project id."""
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    api.put(f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]})
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    )
    return pid


def test_publish_requires_payment_then_succeeds(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _ready_to_publish(api)
    blocked = api.post(f"/api/v1/projects/{pid}/publish", json={})
    assert blocked.status_code == 422
    assert "payment_method" in blocked.json()["error"]["fields"]
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204
    ok = api.post(f"/api/v1/projects/{pid}/publish", json={})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["status"] == "BIDDING"
    assert body["current_baseline_id"] is not None


def test_publish_rejects_incomplete_shares(api: Api) -> None:
    api.sign_in_as("CLIENT")
    api.post("/api/v1/me/payment-method/verify")
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    api.put(f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]})
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Only", "duration_days": 3, "share_bp": 5000, "skill_ids": [sid]}
            ]
        },
    )
    r = api.post(f"/api/v1/projects/{pid}/publish", json={})
    assert r.status_code == 422
    assert "milestones" in r.json()["error"]["fields"]


def test_publish_without_slots_rejected(api: Api) -> None:
    api.sign_in_as("CLIENT")
    api.post("/api/v1/me/payment-method/verify")
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "One", "duration_days": 3, "share_bp": 10000, "skill_ids": [sid]}
            ]
        },
    )
    r = api.post(f"/api/v1/projects/{pid}/publish", json={})
    assert r.status_code == 422
    assert "slots" in r.json()["error"]["fields"]


def test_publish_over_deadline_needs_acknowledgement(api: Api) -> None:
    api.sign_in_as("CLIENT")
    api.post("/api/v1/me/payment-method/verify")
    sid = _skill_id(api)
    pid = _create_draft(api, deadline_days=5)["id"]
    api.put(f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]})
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    )
    blocked = api.post(f"/api/v1/projects/{pid}/publish", json={"acknowledge_schedule_risk": False})
    assert blocked.status_code == 422
    ok = api.post(f"/api/v1/projects/{pid}/publish", json={"acknowledge_schedule_risk": True})
    assert ok.status_code == 200
    assert ok.json()["status"] == "BIDDING"


def test_editing_after_publish_is_rejected(api: Api) -> None:
    api.sign_in_as("CLIENT")
    api.post("/api/v1/me/payment-method/verify")
    sid = _skill_id(api)
    pid = _ready_to_publish(api)
    assert api.post(f"/api/v1/projects/{pid}/publish", json={}).status_code == 200
    patched = api.patch(f"/api/v1/projects/{pid}", json={"summary": "x"})
    assert patched.status_code == 409
    assert patched.json()["error"]["code"] == "INVALID_STATE"
    slots = api.put(
        f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]}
    )
    assert slots.status_code == 409


def test_extend_bidding_capped(api: Api) -> None:
    api.sign_in_as("CLIENT")
    api.post("/api/v1/me/payment-method/verify")
    pid = _ready_to_publish(api)
    assert api.post(f"/api/v1/projects/{pid}/publish", json={}).status_code == 200
    assert api.post(f"/api/v1/projects/{pid}/extend-bidding").status_code == 200
    assert api.post(f"/api/v1/projects/{pid}/extend-bidding").status_code == 200
    third = api.post(f"/api/v1/projects/{pid}/extend-bidding")
    assert third.status_code == 409


def test_cancel_draft_then_cannot_cancel_again(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api)["id"]
    ok = api.post(f"/api/v1/projects/{pid}/cancel", json={"reason": "Changed plans."})
    assert ok.status_code == 200
    assert ok.json()["status"] == "CANCELLED"
    again = api.post(f"/api/v1/projects/{pid}/cancel", json={"reason": "again"})
    assert again.status_code == 409


def test_payment_verify_is_idempotent(api: Api) -> None:
    api.sign_in_as("CLIENT")
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204


def test_get_plan_returns_schedule(api: Api) -> None:
    api.sign_in_as("CLIENT")
    sid = _skill_id(api)
    pid = _create_draft(api)["id"]
    m = _add_two_milestones(api, pid, sid)
    api.put(
        f"/api/v1/projects/{pid}/dependencies",
        json={"dependencies": [{"predecessor_id": m[0]["id"], "successor_id": m[1]["id"]}]},
    )
    r = api.get(f"/api/v1/projects/{pid}/plan")
    assert r.status_code == 200
    assert r.json()["duration"] == 15  # 5 + 10 in series


# --------------------------------------------------------------------------- IDOR / sealing


def test_foreign_client_cannot_see_or_edit_project(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid = _create_draft(api)["id"]
    api.sign_in_as("CLIENT")  # a different client on the same client
    assert api.get(f"/api/v1/projects/{pid}").status_code == 404
    assert api.patch(f"/api/v1/projects/{pid}", json={"summary": "x"}).status_code == 404
    assert api.post(f"/api/v1/projects/{pid}/cancel", json={"reason": "x"}).status_code == 404


def test_developer_cannot_use_project_endpoints(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    body = {"title": "abcde", "budget_paisa": 1, "deadline_days": 1, "team_size": 2}
    assert api.post("/api/v1/projects", json=body).status_code == 403
    assert api.get("/api/v1/projects").status_code == 403
