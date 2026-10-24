"""The reputation summary on developer profiles (spec §13.5 #7, §17 Phase 5, D44/D48/D55).

`GET /developers/{id}` and `GET /public/developers/{id}` carry `reputation` = {competency,
performance, is_newcomer, seeded} read from the stored snapshot in the caller's own session:
only after the profile itself is visible, never for anonymous visitors (snapshots are readable
only when signed in), and null C/P while a developer has no record yet.

Snapshots are SYSTEM-only to write through the app (§14.15), so tests insert them with the
migrator role.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]


def _snapshot(
    url: str,
    developer_id: str,
    *,
    c: str = "0.712",
    p: str = "0.768",
    completed: int = 6,
    settings_version: int | None = None,
) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO reputation_snapshots (id, developer_id, omega, x, xm, beta, mu, "
                    "t, c, p, completed_projects, distinct_clients, settings_version) VALUES "
                    "(:id, :dev, 0.6, 0.7, 0.66, 0.8, 0.7, 0.8, :c, :p, :n, 4, :v)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "dev": developer_id,
                    "c": c,
                    "p": p,
                    "n": completed,
                    "v": settings_version,
                },
            )
    finally:
        engine.dispose()


def _developer(api: Api, visibility: str = "PUBLIC") -> str:
    user = api.sign_in_as("DEVELOPER")
    r = api.patch(
        "/api/v1/me/developer-profile",
        json={"headline": "Backend developer", "visibility": visibility},
    )
    assert r.status_code == 200, r.text
    return user.user_id


def _rep(api: Api, path: str) -> Any:
    r = api.get(path)
    assert r.status_code == 200, r.text
    return r.json()["reputation"]


SEEDED_EXPERIENCED = {
    "competency": "0.712",
    "performance": "0.768",
    "is_newcomer": False,
    "seeded": True,
}


def test_owner_without_a_snapshot_is_a_newcomer_building_a_record(api: Api) -> None:
    dev = _developer(api)
    assert _rep(api, f"/api/v1/developers/{dev}") == {
        "competency": None,
        "performance": None,
        "is_newcomer": True,
        "seeded": False,
    }


def test_owner_sees_their_seeded_values(api: Api, migration_url: str) -> None:
    dev = _developer(api)
    _snapshot(migration_url, dev)
    assert _rep(api, f"/api/v1/developers/{dev}") == SEEDED_EXPERIENCED
    # The public endpoint gives a signed-in caller the same summary.
    assert _rep(api, f"/api/v1/public/developers/{dev}") == SEEDED_EXPERIENCED


def test_other_developer_and_client_see_a_public_profiles_reputation(
    api: Api, api2: Api, migration_url: str
) -> None:
    dev = _developer(api)
    _snapshot(migration_url, dev)
    api2.sign_in_as("DEVELOPER")
    assert _rep(api2, f"/api/v1/developers/{dev}") == SEEDED_EXPERIENCED
    api2.client.cookies.clear()
    api2.sign_in_as("CLIENT")
    assert _rep(api2, f"/api/v1/developers/{dev}") == SEEDED_EXPERIENCED
    assert _rep(api2, f"/api/v1/public/developers/{dev}") == SEEDED_EXPERIENCED


def test_anonymous_visitor_gets_the_profile_without_reputation(
    api: Api, api2: Api, migration_url: str
) -> None:
    dev = _developer(api)
    _snapshot(migration_url, dev)
    r = api2.get(f"/api/v1/public/developers/{dev}")
    assert r.status_code == 200, r.text
    assert r.json()["reputation"] is None
    assert "0.712" not in r.text
    # The signed-in endpoint stays closed to guests.
    assert api2.get(f"/api/v1/developers/{dev}").status_code == 401


def test_hidden_profile_leaks_no_reputation(api: Api, api2: Api, migration_url: str) -> None:
    dev = _developer(api, "CLIENTS_ONLY")
    _snapshot(migration_url, dev)
    r = api2.get(f"/api/v1/public/developers/{dev}")  # anonymous
    assert r.status_code == 404
    assert "0.712" not in r.text
    api2.sign_in_as("DEVELOPER")
    for path in (f"/api/v1/developers/{dev}", f"/api/v1/public/developers/{dev}"):
        r = api2.get(path)
        assert r.status_code == 404
        assert "0.712" not in r.text
    api2.client.cookies.clear()
    api2.sign_in_as("CLIENT")
    assert _rep(api2, f"/api/v1/developers/{dev}") == SEEDED_EXPERIENCED


def test_newcomer_with_a_stored_snapshot_shows_values_and_the_flag(
    api: Api, migration_url: str
) -> None:
    dev = _developer(api)
    _snapshot(migration_url, dev, c="0.5", p="0.45", completed=2)  # threshold is 3
    assert _rep(api, f"/api/v1/developers/{dev}") == {
        "competency": "0.500",
        "performance": "0.450",
        "is_newcomer": True,
        "seeded": True,
    }


def test_computed_snapshot_is_not_marked_seeded(api: Api, migration_url: str) -> None:
    dev = _developer(api)
    _snapshot(migration_url, dev, completed=3, settings_version=1)  # boundary: not a newcomer
    rep = _rep(api, f"/api/v1/developers/{dev}")
    assert rep["seeded"] is False
    assert rep["is_newcomer"] is False


def test_unknown_developer_is_not_found(api: Api) -> None:
    api.sign_in_as("CLIENT")
    assert api.get(f"/api/v1/developers/{uuid.uuid4()}").status_code == 404
    assert api.get("/api/v1/developers/not-a-uuid").status_code == 422
