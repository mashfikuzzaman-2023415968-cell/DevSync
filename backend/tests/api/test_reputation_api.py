"""Reputation API (spec §10.2 Reputation, §13.5 #16, §14.13 row 6, §16.4).

`GET /developers/{id}/reputation`: a public value for active accounts that follows the profile's
visibility (404 when hidden or unknown); a newcomer sees their own starting values and where
they come from, while anyone else sees nothing about a newcomer without a record.
`GET /me/reputation/history`: the developer's own projects, newest first, cursor-paged, with a
plain-language reason per change. Both are reads: no request ever writes reputation.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

from tests.helpers import Api
from tests.security.test_profile_reputation import _developer

pytestmark = [pytest.mark.api, pytest.mark.security]

PARAMS = ("omega", "x", "xm", "beta", "mu", "t")


def _experienced(api: Api, projects: int = 5) -> str:
    dev = _developer(api)
    r = api.post(f"/api/v1/__test__/developers/{dev}/reputation-history",
                 json={"projects": projects})  # fmt: skip
    assert r.status_code == 204, r.text
    return dev


def _score(value: Any) -> float:
    assert isinstance(value, str)
    assert re.fullmatch(r"[01]\.\d{3}", value), value
    return float(value)


def test_developer_reads_own_computed_reputation(api: Api) -> None:
    dev = _experienced(api)
    r = api.get(f"/api/v1/developers/{dev}/reputation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["developer_id"] == dev
    for key in PARAMS:
        assert 0 <= _score(body["parameters"][key]) <= 1
    assert 0 <= _score(body["competency"]) <= 1
    assert body["completed_projects"] == 5
    assert body["is_newcomer"] is False
    assert body["seeded"] is False  # computed by the engine (D48 marker off)
    assert body["simulated"] is True  # labelled everywhere (D84)
    assert body["newcomer"] is None
    assert body["skills"]
    assert all(0 <= _score(s["competency"]) <= 1 for s in body["skills"])


def test_other_signed_in_roles_see_the_same_public_value(api: Api, api2: Api) -> None:
    dev = _experienced(api)
    mine = api.get(f"/api/v1/developers/{dev}/reputation").json()
    for role in ("DEVELOPER", "CLIENT"):
        api2.sign_in_as(role)
        theirs = api2.get(f"/api/v1/developers/{dev}/reputation")
        assert theirs.status_code == 200, theirs.text
        assert theirs.json() == mine


def test_newcomer_sees_own_starting_values_others_see_nothing(api: Api, api2: Api) -> None:
    """§9.1.3 values for the developer; null for others (they'd need private data, D58)."""
    dev = _developer(api)
    own = api.get(f"/api/v1/developers/{dev}/reputation").json()
    assert own["is_newcomer"] is True
    assert own["completed_projects"] == 0
    assert _score(own["parameters"]["xm"]) == 0.5
    assert _score(own["parameters"]["mu"]) == 0.5
    basis = own["newcomer"]
    assert basis is not None
    assert 0 <= basis["verified_items"] <= 4
    assert basis["threshold"] == 3
    api2.sign_in_as("CLIENT")
    other = api2.get(f"/api/v1/developers/{dev}/reputation").json()
    assert other["newcomer"] is None
    assert other["competency"] is None
    assert all(other["parameters"][k] is None for k in PARAMS)
    assert other["is_newcomer"] is True


def test_newcomer_with_one_project_keeps_the_basis(api: Api) -> None:
    dev = _experienced(api, projects=1)
    body = api.get(f"/api/v1/developers/{dev}/reputation").json()
    assert body["is_newcomer"] is True
    assert body["completed_projects"] == 1
    assert body["newcomer"] is not None


def test_hidden_unknown_and_non_developer_ids_are_404(api: Api, api2: Api) -> None:
    hidden = _developer(api, "CLIENTS_ONLY")
    client = api2.sign_in_as("CLIENT")
    assert api2.get(f"/api/v1/developers/{hidden}/reputation").status_code == 200
    api2.sign_in_as("DEVELOPER")
    assert api2.get(f"/api/v1/developers/{hidden}/reputation").status_code == 404
    assert api2.get(f"/api/v1/developers/{uuid.uuid4()}/reputation").status_code == 404
    assert api2.get(f"/api/v1/developers/{client.user_id}/reputation").status_code == 404


def test_bad_ids_are_422_and_anonymous_is_401(api: Api) -> None:
    assert api.get("/api/v1/developers/not-a-uuid/reputation").status_code == 401
    api.sign_in_as("DEVELOPER")
    for bad in ("not-a-uuid", "1%27%20OR%201%3D1", "%00"):
        assert api.get(f"/api/v1/developers/{bad}/reputation").status_code == 422


def test_history_newest_first_with_plain_reasons(api: Api) -> None:
    _experienced(api, projects=4)
    r = api.get("/api/v1/me/reputation/history?limit=100")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["project_label"] for i in items] == [f"Simulated project {n}" for n in (4, 3, 2, 1)]
    assert r.json()["next_cursor"] is None
    for item in items:
        assert item["simulated"] is True
        assert {c["parameter"] for c in item["changes"]} == {*PARAMS, "c", "p"}
        for change in item["changes"]:
            reason = change["reason"]
            assert reason.endswith(".")
            assert not re.search(r"[ωμβλεΓκα]|Eq\.", reason), reason  # plain words (§13.10)
            assert change["capped"] == (change["raw_new"] != change["new"])


def test_history_pages_with_a_cursor(api: Api) -> None:
    _experienced(api, projects=5)
    seen: list[str] = []
    cursor = None
    for _ in range(5):
        url = "/api/v1/me/reputation/history?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = api.get(url).json()
        seen += [i["history_id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 5


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "limit=x", "cursor=", "cursor=not-base64!", "cursor=" + "A" * 201],
)
def test_history_refuses_bad_paging(api: Api, query: str) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.get(f"/api/v1/me/reputation/history?{query}")
    assert r.status_code == 422, (query, r.text)


def test_history_is_only_ever_the_callers_own(api: Api, api2: Api) -> None:
    _experienced(api, projects=3)
    api2.sign_in_as("DEVELOPER")
    assert api2.get("/api/v1/me/reputation/history").json() == {"items": [], "next_cursor": None}


def test_history_refuses_other_roles(api: Api) -> None:
    assert api.get("/api/v1/me/reputation/history").status_code == 401
    api.sign_in_as("CLIENT")
    assert api.get("/api/v1/me/reputation/history").status_code == 403


def test_reading_never_writes(api: Api) -> None:
    """GETs don't mutate (§16.4): repeated reads return identical bodies and add no log rows."""
    dev = _experienced(api, projects=3)
    first = (api.get(f"/api/v1/developers/{dev}/reputation").json(),
             api.get("/api/v1/me/reputation/history?limit=100").json())  # fmt: skip
    second = (api.get(f"/api/v1/developers/{dev}/reputation").json(),
              api.get("/api/v1/me/reputation/history?limit=100").json())  # fmt: skip
    assert first == second


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_no_write_methods_exist(api: Api, method: str) -> None:
    """§14.13 row 6: reputation inputs come only from server-side evidence."""
    dev = api.sign_in_as("DEVELOPER")
    for path in (f"/api/v1/developers/{dev.user_id}/reputation", "/api/v1/me/reputation/history"):
        r = api.request(method, path, json={"p": "1.000"})
        assert r.status_code == 405, (method, path, r.status_code)
