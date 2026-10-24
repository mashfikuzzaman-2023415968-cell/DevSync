"""Trailing-slash 308s, X-Robots-Tag, the admin network allowlist and the access log.

Spec §10.1/§15.5 (canonical paths), §14.17 (admin hidden, noindex, ADMIN_ALLOWED_CIDRS),
§14.12/§15.7 (one structured, redacted log line per request).
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.middleware import AdminNetworkMiddleware, canonical_api_location
from app.core.netutil import parse_networks, trusted_client_ip
from app.main import create_app
from tests.conftest import make_settings

pytestmark = pytest.mark.api


def _client(settings: Settings, ip: str = "testclient") -> TestClient:
    return TestClient(
        create_app(settings),
        base_url="https://testserver",
        raise_server_exceptions=False,
        follow_redirects=False,
        client=(ip, 50000),
    )


@pytest.fixture
def plain() -> Iterator[TestClient]:
    with _client(make_settings()) as c:
        yield c


# ------------------------------------------------------------ trailing slash → 308 (§15.5)


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_trailing_slash_is_a_relative_308_for_every_method(plain: TestClient, method: str) -> None:
    r = plain.request(method, "/api/v1/health/", content=b'{"a": 1}')
    assert r.status_code == 308  # 308 keeps the method and the body
    assert r.headers["location"] == "/api/v1/health"
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert r.headers["cache-control"] == "no-store"


def test_query_is_kept_and_extra_slashes_collapse(plain: TestClient) -> None:
    r = plain.get("/api/v1/projects/search///?q=web%20app&limit=5")
    assert r.status_code == 308
    assert r.headers["location"] == "/api/v1/projects/search?q=web%20app&limit=5"


def test_following_the_redirect_reaches_the_route(plain: TestClient) -> None:
    r = plain.get("/api/v1/health/", follow_redirects=True)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    [
        "/api//evil.com/",
        "/api/v1//evil.com/",
        "/api/%2F%2Fevil.com/",
        "/api/%5Cevil.com/",
        "/api/v1/../../evil/",
        "/api/v1/%2e%2e/evil/",
        "/api/",
    ],
)
def test_suspicious_paths_are_never_redirected(plain: TestClient, path: str) -> None:
    r = plain.get(path)
    assert r.status_code != 308, r.headers.get("location")
    assert "location" not in r.headers


@pytest.mark.parametrize(
    ("raw_path", "path", "query"),
    [
        (b"//evil.com/", "//evil.com/", b""),
        (b"/api/v1/x/", "/api/v1/x/", b"a=\r\nSet-Cookie:x"),
        (b"/api/v1/x%2F", "/api/v1/x/", b""),  # an encoded slash would redirect to itself
        (b"/api/v1/\\evil.com/", "/api/v1/\\evil.com/", b""),
        (b"/apix/", "/apix/", b""),
    ],
)
def test_location_builder_refuses_open_redirects(raw_path: bytes, path: str, query: bytes) -> None:
    scope = {"type": "http", "path": path, "raw_path": raw_path, "query_string": query}
    assert canonical_api_location(scope) is None


def test_location_is_always_relative_and_under_the_api() -> None:
    scope = {"type": "http", "path": "/api/v1/me/", "raw_path": b"/api/v1/me/", "query_string": b""}
    assert canonical_api_location(scope) == b"/api/v1/me"


def test_non_api_trailing_slash_gets_no_absolute_redirect(plain: TestClient) -> None:
    r = plain.get("/metrics/")
    assert r.status_code == 404
    assert "location" not in r.headers


# --------------------------------------------------------------- X-Robots-Tag (§14.17)


@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/admin/session", "/api/v1/nope"])
def test_api_and_admin_responses_carry_noindex(plain: TestClient, path: str) -> None:
    r = plain.get(path) if path == "/api/v1/health" else plain.get(path + "/")
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


# --------------------------------------------- ADMIN_ALLOWED_CIDRS (§14.17), no DB needed


def _scope(peer: str, xff: str | None = None, path: str = "/api/v1/admin/session") -> Any:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return {"type": "http", "path": path, "client": (peer, 1234), "headers": headers}


async def _call(mw: AdminNetworkMiddleware, scope: Any) -> int:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b""}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await mw(scope, receive, send)
    return int(sent[0]["status"])


async def _inner(_scope: Any, _receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


PROXIES = parse_networks("172.16.0.0/12")


@pytest.mark.parametrize(
    ("allowed", "peer", "xff", "status"),
    [
        ("203.0.113.0/24", "203.0.113.9", None, 200),  # inside, direct
        ("203.0.113.0/24", "198.51.100.1", None, 404),  # outside, direct
        ("203.0.113.0/24", "172.18.0.5", "203.0.113.9", 200),  # inside, via the proxy
        ("203.0.113.0/24", "172.18.0.5", "198.51.100.1", 404),  # outside, via the proxy
        ("203.0.113.0/24", "198.51.100.1", "203.0.113.9", 404),  # spoofed XFF, untrusted peer
        ("203.0.113.0/24", "172.18.0.5", "garbage", 404),  # junk XFF from the proxy
        ("203.0.113.0/24", "testclient", None, 404),  # no valid address at all
        ("2001:db8::/32", "2001:db8::7", None, 200),  # IPv6 inside
        ("2001:db8::/32", "2001:db9::7", None, 404),  # IPv6 outside
        ("203.0.113.0/24", "::ffff:203.0.113.9", None, 200),  # IPv4-mapped IPv6
        ("", "198.51.100.1", None, 200),  # empty list = every network
    ],
)
async def test_admin_allowlist_decisions(allowed: str, peer: str, xff: str, status: int) -> None:
    mw = AdminNetworkMiddleware(_inner, allowed=parse_networks(allowed), trusted_proxies=PROXIES)
    assert await _call(mw, _scope(peer, xff)) == status


@pytest.mark.parametrize(
    "path", ["/api/v1/health", "/api/v1/administrators", "/api/v1/me", "/admin/session"]
)
async def test_allowlist_only_guards_the_admin_api(path: str) -> None:
    mw = AdminNetworkMiddleware(
        _inner, allowed=parse_networks("203.0.113.0/24"), trusted_proxies=PROXIES
    )
    assert await _call(mw, _scope("198.51.100.1", path=path)) == 200


@pytest.mark.parametrize("path", ["/api/v1/admin", "/api/v1/admin/", "/api/v1/admin/x/y"])
async def test_every_admin_api_path_is_guarded(path: str) -> None:
    mw = AdminNetworkMiddleware(
        _inner, allowed=parse_networks("203.0.113.0/24"), trusted_proxies=PROXIES
    )
    assert await _call(mw, _scope("198.51.100.1", path=path)) == 404


def test_trusted_client_ip_uses_the_right_most_forwarded_entry() -> None:
    scope = _scope("172.18.0.5", "198.51.100.1, 203.0.113.9")
    assert trusted_client_ip(scope, PROXIES) == "203.0.113.9"
    assert trusted_client_ip(_scope("10.1.1.1", "203.0.113.9"), PROXIES) == "10.1.1.1"
    assert ipaddress.ip_address(trusted_client_ip(_scope("::1"), PROXIES) or "") == (
        ipaddress.ip_address("::1")
    )


def test_outside_admin_request_gets_the_ordinary_404(plain: TestClient) -> None:
    settings = make_settings(ADMIN_ALLOWED_CIDRS="203.0.113.0/24")
    with _client(settings, ip="198.51.100.1") as c:
        refused = c.get("/api/v1/admin/session")
        trailing = c.get("/api/v1/admin/session/")
    assert refused.status_code == 404
    assert refused.json()["error"]["code"] == "NOT_FOUND"
    assert refused.json()["error"]["message"] == "We couldn't find that."
    assert refused.headers["x-robots-tag"] == "noindex, nofollow"
    # The slash redirect must not confirm the area exists to outsiders.
    assert trailing.status_code == 404


# ------------------------------------------------------------ access log (§14.12, §15.7)


def _access_lines(out: str) -> list[dict[str, Any]]:
    lines = []
    for line in out.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("event") == "http_request":
            lines.append(entry)
    return lines


def test_one_access_line_per_request(plain: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    r = plain.get("/api/v1/health", headers={"X-Request-ID": "nginx-abcdef123456"})
    lines = _access_lines(capsys.readouterr().out)
    assert len(lines) == 1, lines
    entry = lines[0]
    assert entry["method"] == "GET"
    assert entry["route"] == "/api/v1/health"
    assert entry["status"] == r.status_code == 200
    assert entry["request_id"] == "nginx-abcdef123456"
    assert isinstance(entry["duration_ms"], int | float)
    assert entry["duration_ms"] >= 0
    assert entry["user_hash"] is None


def test_access_line_never_contains_secrets_or_raw_paths(
    plain: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "tok_" + "s3cr3t" * 8
    capsys.readouterr()
    plain.get(
        f"/api/v1/health/?token={secret}&email=a.person@example.com",
        headers={
            "Authorization": f"Bearer {secret}",
            "Cookie": f"__Host-ds_session={secret}",
            "X-CSRF-Token": secret,
        },
    )
    out = capsys.readouterr().out
    lines = _access_lines(out)
    assert len(lines) == 1
    assert lines[0]["status"] == 308
    assert lines[0]["route"] == "unmatched"  # never the raw path
    for leaked in (secret, "a.person@example.com", "token=", "__Host-ds_session"):
        assert leaked not in out


def test_rejected_host_is_logged_too(capsys: pytest.CaptureFixture[str]) -> None:
    with TestClient(create_app(make_settings()), base_url="http://evil.example") as c:
        capsys.readouterr()
        assert c.get("/api/v1/health").status_code == 400
    lines = _access_lines(capsys.readouterr().out)
    assert [e["status"] for e in lines] == [400]
