"""Request bodies are JSON only, depth-limited and finite (spec §10.1, §14.7, §16.4)."""

from __future__ import annotations

import json

import pytest

from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]

ME = "/api/v1/me"
GOOD = {"display_name": "Nadia Rahman"}


def _code(r: object) -> str:
    return str(r.json()["error"]["code"])  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/xml",
        "application/json; charset=iso-8859-1",
        None,  # a body without any content type
    ],
)
def test_non_json_body_is_415(api: Api, content_type: str | None) -> None:
    api.sign_in_as("CLIENT")
    headers = {"Content-Type": content_type} if content_type else {}
    r = api.patch(ME, content=json.dumps(GOOD).encode(), headers=headers)
    assert r.status_code == 415
    assert _code(r) == "UNSUPPORTED_MEDIA_TYPE"
    assert r.json()["error"]["request_id"]
    # Nothing changed.
    assert api.get(ME).json()["display_name"] != "Nadia Rahman"


def test_json_body_with_charset_is_accepted(api: Api) -> None:
    api.sign_in_as("CLIENT")
    r = api.patch(
        ME,
        content=json.dumps(GOOD).encode(),
        headers={"Content-Type": "application/json; charset=UTF-8"},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Nadia Rahman"


def test_anonymous_415_is_still_refused_by_csrf_first(api: Api) -> None:
    r = api.patch(ME, content=b"x", headers={"Content-Type": "text/plain"}, csrf=False)
    assert r.status_code == 403
    assert _code(r) == "CSRF_FAILED"


def _nested(depth: int) -> str:
    return '{"display_name": "Nadia", "x": ' + "[" * (depth - 1) + "]" * (depth - 1) + "}"


def test_nesting_depth_limit(api: Api) -> None:
    api.sign_in_as("CLIENT")
    headers = {"Content-Type": "application/json"}
    # 20 levels pass the depth rule (the schema then refuses the unknown field: 422 from Pydantic).
    at_limit = api.patch(ME, content=_nested(20), headers=headers)
    assert at_limit.status_code == 422
    assert "x" in at_limit.json()["error"]["fields"]
    over = api.patch(ME, content=_nested(21), headers=headers)
    assert over.status_code == 422
    assert over.json()["error"]["fields"] == {"body": "Nesting is limited to 20 levels."}
    deep = api.patch(ME, content="[" * 200_000, headers=headers)
    assert deep.status_code == 422
    assert _code(deep) == "VALIDATION_ERROR"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nan_and_infinity_are_refused(api: Api, constant: str) -> None:
    api.sign_in_as("DEVELOPER")
    body = '{"hours_per_week": ' + constant + "}"
    r = api.patch(
        "/api/v1/me/developer-profile", content=body, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["fields"] == {"body": "NaN and Infinity are not allowed."}


def test_malformed_json_is_still_422(api: Api) -> None:
    api.sign_in_as("CLIENT")
    r = api.patch(ME, content=b'{"display_name": ', headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert _code(r) == "VALIDATION_ERROR"


def test_upload_endpoints_take_multipart_only(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    path = "/api/v1/me/certificates"
    # A form without the file: FastAPI's own 422 (multipart still reaches the route).
    form = api.post(path, files={"title": (None, "Cert"), "issuer": (None, "Issuer")})
    assert form.status_code == 422
    # JSON or url-encoded bodies are not accepted on an upload endpoint.
    as_json = api.post(path, json={"title": "Cert", "issuer": "Issuer"})
    assert as_json.status_code == 415
    urlenc = api.post(path, data={"title": "Cert", "issuer": "Issuer"})
    assert urlenc.status_code == 415


def test_bodiless_unsafe_requests_still_work(api: Api) -> None:
    api.sign_in_as("CLIENT")
    assert api.post("/api/v1/auth/logout").status_code == 204


def test_unknown_routes_and_methods_keep_404_and_405(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.put("/api/v1/me/certificates", content=b"x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 405
    r = api.post("/api/v1/no-such-route", content=b"x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 404
