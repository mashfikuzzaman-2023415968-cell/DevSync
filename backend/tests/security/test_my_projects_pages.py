"""`GET /projects` (the client's My projects) is cursor-paginated (spec §10.1, §16.4)."""

from __future__ import annotations

import base64

import pytest

from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]

LIST = "/api/v1/projects"


def _create(api: Api, n: int) -> list[str]:
    ids = []
    for i in range(n):
        r = api.post(
            LIST,
            json={
                "title": f"Project {i}",
                "summary": "Order and track restaurant orders.",
                "budget_paisa": 12_000_000,
                "deadline_days": 30,
                "team_size": 2,
            },
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
        api.get("/api/v1/__test__/ratelimits/reset")  # project creation is rate-limited
    return ids


def test_pages_walk_every_project_once_newest_first(api: Api) -> None:
    api.sign_in_as("CLIENT")
    created = _create(api, 5)
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params: dict[str, object] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        r = api.get(LIST, params=params)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"items", "next_cursor"}
        assert len(body["items"]) <= 2
        seen.extend(p["id"] for p in body["items"])
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert seen == list(reversed(created))  # newest first, no repeats or gaps


def test_exact_page_has_no_next_cursor(api: Api) -> None:
    api.sign_in_as("CLIENT")
    _create(api, 2)
    body = api.get(LIST, params={"limit": 2}).json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is None
    assert api.get(LIST).json()["next_cursor"] is None  # default limit 20


def test_empty_list(api: Api) -> None:
    api.sign_in_as("CLIENT")
    assert api.get(LIST).json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("limit", [0, -1, 101, "x"])
def test_limit_bounds(api: Api, limit: object) -> None:
    api.sign_in_as("CLIENT")
    assert api.get(LIST, params={"limit": limit}).status_code == 422


def _b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode()


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64!",
        _b64("mine|yesterday|x"),
        _b64("newest|2026-10-24T00:00:00+00:00|7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c"),  # search's
        _b64("mine|2026-10-24T00:00:00|7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c"),  # no time zone
        "x" * 201,
    ],
)
def test_bad_cursors_are_422(api: Api, cursor: str) -> None:
    api.sign_in_as("CLIENT")
    r = api.get(LIST, params={"cursor": cursor})
    assert r.status_code == 422
    assert "cursor" in r.json()["error"]["fields"]


def test_a_cursor_never_reveals_another_clients_projects(api: Api, api2: Api) -> None:
    api.sign_in_as("CLIENT")
    _create(api, 3)
    cursor = api.get(LIST, params={"limit": 1}).json()["next_cursor"]
    assert cursor
    api2.sign_in_as("CLIENT")
    mine = _create(api2, 1)
    # The other client's cursor only positions the page; the rows are still the caller's own.
    items = api2.get(LIST, params={"cursor": cursor}).json()["items"]
    assert {p["id"] for p in items} <= set(mine)


def test_developers_and_anonymous_are_refused(api: Api) -> None:
    assert api.get(LIST).status_code == 401
    api.sign_in_as("DEVELOPER")
    assert api.get(LIST).status_code == 403
