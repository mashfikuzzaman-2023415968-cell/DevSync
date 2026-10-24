"""If-Match optimistic concurrency on plan replaces and profile PATCHes (spec §10.1, §16.4).

A stale version is 409 `VERSION_CONFLICT` and changes nothing; the right version saves and
returns the next one (plan replaces in the `X-Version` header, profiles in the body).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]


def _skill_id(api: Api) -> str:
    skills = api.get("/api/v1/skills").json()
    return str(skills[0].get("skill_id") or skills[0]["id"])


def _draft(api: Api) -> dict[str, Any]:
    r = api.post(
        "/api/v1/projects",
        json={
            "title": "Online ordering system",
            "summary": "Order and track restaurant orders.",
            "budget_paisa": 12_000_000,
            "deadline_days": 30,
            "team_size": 2,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def _milestones(sid: str) -> dict[str, Any]:
    return {
        "milestones": [
            {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
            {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
        ]
    }


def _version(api: Api, pid: str) -> int:
    return int(api.get(f"/api/v1/projects/{pid}").json()["version"])


def test_plan_replaces_check_if_match_and_return_the_new_version(api: Api) -> None:
    api.sign_in_as("CLIENT")
    project = _draft(api)
    pid, sid = project["id"], _skill_id(api)
    v = project["version"]

    slots = {"slots": [{"skill_id": sid, "count": 2}]}
    r = api.put(f"/api/v1/projects/{pid}/slots", json=slots, headers={"If-Match": str(v)})
    assert r.status_code == 200, r.text
    assert int(r.headers["X-Version"]) == v + 1 == _version(api, pid)
    v += 1

    r = api.put(
        f"/api/v1/projects/{pid}/milestones", json=_milestones(sid), headers={"If-Match": str(v)}
    )
    assert r.status_code == 200, r.text
    assert int(r.headers["X-Version"]) == v + 1
    v += 1
    ids = [m["id"] for m in r.json()]

    deps = {"dependencies": [{"predecessor_id": ids[0], "successor_id": ids[1]}]}
    r = api.put(f"/api/v1/projects/{pid}/dependencies", json=deps, headers={"If-Match": str(v)})
    assert r.status_code == 200, r.text
    assert int(r.headers["X-Version"]) == v + 1 == _version(api, pid)


@pytest.mark.parametrize("what", ["slots", "milestones", "dependencies"])
def test_stale_plan_replace_is_409_and_changes_nothing(api: Api, what: str) -> None:
    api.sign_in_as("CLIENT")
    project = _draft(api)
    pid, sid = project["id"], _skill_id(api)
    saved = api.put(f"/api/v1/projects/{pid}/milestones", json=_milestones(sid)).json()
    before = api.get(f"/api/v1/projects/{pid}/draft").json()
    current = _version(api, pid)
    bodies: dict[str, Any] = {
        "slots": {"slots": [{"skill_id": sid, "count": 3}]},
        "milestones": {"milestones": _milestones(sid)["milestones"][:1]},
        "dependencies": {
            "dependencies": [{"predecessor_id": saved[0]["id"], "successor_id": saved[1]["id"]}]
        },
    }
    for stale in (current - 1, current + 1, 0):
        r = api.put(
            f"/api/v1/projects/{pid}/{what}", json=bodies[what], headers={"If-Match": str(stale)}
        )
        assert r.status_code == 409, (stale, r.text)
        assert r.json()["error"]["code"] == "VERSION_CONFLICT"
        assert "X-Version" not in r.headers
    assert api.get(f"/api/v1/projects/{pid}/draft").json() == before
    assert _version(api, pid) == current


@pytest.mark.parametrize("value", ["abc", "-1", "1.5", "99999999999"])
def test_malformed_if_match_is_422(api: Api, value: str) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.patch(
        "/api/v1/me/developer-profile", json={"headline": "x"}, headers={"If-Match": value}
    )
    assert r.status_code == 422


def test_other_clients_project_is_404_even_with_the_right_version(api: Api, api2: Api) -> None:
    api.sign_in_as("CLIENT")
    project = _draft(api)
    api2.sign_in_as("CLIENT")
    sid = _skill_id(api2)
    r = api2.put(
        f"/api/v1/projects/{project['id']}/slots",
        json={"slots": [{"skill_id": sid, "count": 2}]},
        headers={"If-Match": str(project["version"])},
    )
    assert r.status_code == 404


def test_developer_profile_versions(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    path = "/api/v1/me/developer-profile"
    assert api.get(path).json()["version"] == 0  # never saved
    # A stale first save (someone already saved) and a first save both use If-Match.
    stale_first = api.patch(path, json={"headline": "A"}, headers={"If-Match": "1"})
    assert stale_first.status_code == 409
    assert api.get(path).json()["version"] == 0  # the 409 left no row behind
    first = api.patch(path, json={"headline": "A"}, headers={"If-Match": "0"})
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    second = api.patch(path, json={"bio": "B"}, headers={"If-Match": "1"})
    assert second.json()["version"] == 2
    # Another tab still holding version 1 is refused; nothing changes.
    stale = api.patch(path, json={"headline": "Overwritten"}, headers={"If-Match": "1"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert "changed elsewhere" in stale.json()["error"]["message"]
    now = api.get(path).json()
    assert (now["headline"], now["bio"], now["version"]) == ("A", "B", 2)
    # Without If-Match the save still works (and bumps the version).
    assert api.patch(path, json={"headline": "C"}).json()["version"] == 3


def test_client_profile_versions(api: Api) -> None:
    api.sign_in_as("CLIENT")
    path = "/api/v1/me/client-profile"
    assert api.get(path).json()["version"] == 0
    assert (
        api.patch(path, json={"organization": "Rahim"}, headers={"If-Match": "0"}).json()["version"]
        == 1
    )
    stale = api.patch(path, json={"organization": "Karim"}, headers={"If-Match": "0"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert api.get(path).json()["organization"] == "Rahim"


def test_profile_version_is_per_user(api: Api, api2: Api) -> None:
    api.sign_in_as("DEVELOPER")
    api.patch("/api/v1/me/developer-profile", json={"headline": "Mine"})
    api2.sign_in_as("DEVELOPER")
    # The other developer's own profile is unaffected by the first one's version.
    r = api2.patch(
        "/api/v1/me/developer-profile", json={"headline": "Theirs"}, headers={"If-Match": "0"}
    )
    assert r.status_code == 200
    assert r.json()["version"] == 1
