"""Sealed-bid API behaviour and authorization (spec §10 Bids, §14.5).

Builds a real BIDDING project through the API, then checks: a developer can place/edit/withdraw a
bid; only one active bid per project; bids are sealed (another developer sees nothing, and cannot
read/edit/delete someone else's bid → 404); the client sees all bids with eligibility; invalid
state and mass-assignment are refused.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import Api

pytestmark = pytest.mark.api


def _skill_id(api: Api) -> str:
    skills = api.get("/api/v1/skills").json()
    assert skills, "seeded skills expected"
    return skills[0].get("skill_id") or skills[0]["id"]


def _publish_project(api: Api) -> tuple[str, str]:
    """Create, plan, verify payment and publish a project; return (project_id, slot_id)."""
    sid = _skill_id(api)
    pid = api.post(
        "/api/v1/projects",
        json={
            "title": "Online ordering system",
            "summary": "Order and track restaurant orders.",
            "budget_paisa": 12_000_000,
            "deadline_days": 30,
            "team_size": 2,
        },
    ).json()["id"]
    slots = api.put(
        f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]}
    ).json()
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    )
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204
    assert api.post(f"/api/v1/projects/{pid}/publish", json={}).status_code == 200
    return pid, slots[0]["id"]


def _bid_body(slot_id: str, **over: Any) -> dict[str, Any]:
    body = {"slot_id": slot_id, "price_paisa": 1_800_000, "days_needed": 20}
    body.update(over)
    return body


def test_place_edit_and_withdraw_a_bid(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish_project(api)

    api.sign_in_as("DEVELOPER")
    created = api.post(f"/api/v1/projects/{pid}/bids", json=_bid_body(slot_id))
    assert created.status_code == 201, created.text
    bid_id = created.json()["id"]
    assert created.json()["status"] == "ACTIVE"

    # Edit.
    edited = api.patch(f"/api/v1/bids/{bid_id}", json={"price_paisa": 1_700_000})
    assert edited.status_code == 200
    assert edited.json()["price_paisa"] == 1_700_000

    # It appears in my bids.
    assert any(b["id"] == bid_id for b in api.get("/api/v1/me/bids").json())

    # Withdraw.
    assert api.delete(f"/api/v1/bids/{bid_id}").status_code == 204


def test_one_active_bid_per_project(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish_project(api)
    api.sign_in_as("DEVELOPER")
    assert api.post(f"/api/v1/projects/{pid}/bids", json=_bid_body(slot_id)).status_code == 201
    dup = api.post(f"/api/v1/projects/{pid}/bids", json=_bid_body(slot_id))
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "INVALID_STATE"


def test_bids_are_sealed_between_developers(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish_project(api)

    api.sign_in_as("DEVELOPER")
    bid_id = api.post(f"/api/v1/projects/{pid}/bids", json=_bid_body(slot_id)).json()["id"]

    # A different developer sees nothing of it and cannot touch it (sealed → 404).
    api.sign_in_as("DEVELOPER")
    assert api.get("/api/v1/me/bids").json() == []
    assert api.patch(f"/api/v1/bids/{bid_id}", json={"price_paisa": 1}).status_code == 404
    assert api.delete(f"/api/v1/bids/{bid_id}").status_code == 404


def test_client_sees_all_bids_with_eligibility(api: Api) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish_project(api)
    api.sign_in_as("DEVELOPER")
    api.post(f"/api/v1/projects/{pid}/bids", json=_bid_body(slot_id))

    # Back to the owning client.
    api.login(client)
    view = api.get(f"/api/v1/projects/{pid}/bids")
    assert view.status_code == 200, view.text
    body = view.json()
    assert len(body["bids"]) == 1
    assert "eligible" in body["bids"][0]
    assert any(c["slot_id"] == slot_id for c in body["coverage"])


def test_developer_cannot_read_the_client_bids_view(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, _slot = _publish_project(api)
    api.sign_in_as("DEVELOPER")
    # Wrong role for the all-bids view → 403 (sealed; a developer never sees the full list).
    assert api.get(f"/api/v1/projects/{pid}/bids").status_code == 403


def test_eligibility_preview_returns_a_verdict(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish_project(api)
    api.sign_in_as("DEVELOPER")
    # 31 days > the 30-day deadline: the days check fails and the bid is ineligible. (The top
    # reason for this skill-less newcomer is SKILL_MISMATCH, which has higher precedence; the
    # per-reason exactness is covered by the filtering unit tests.)
    r = api.post(
        f"/api/v1/projects/{pid}/bids/eligibility", json=_bid_body(slot_id, days_needed=31)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eligible"] is False
    assert body["reason"] is not None
    assert any(c["name"] == "days" and not c["ok"] for c in body["checks"])


def test_mass_assignment_is_rejected(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish_project(api)
    api.sign_in_as("DEVELOPER")
    r = api.post(f"/api/v1/projects/{pid}/bids", json=_bid_body(slot_id, status="SELECTED"))
    assert r.status_code == 422


def test_bid_on_unknown_project_is_404(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.post(
        "/api/v1/projects/00000000-0000-4000-8000-000000000000/bids",
        json=_bid_body("00000000-0000-4000-8000-000000000001"),
    )
    assert r.status_code == 404
