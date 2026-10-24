"""ADMIN_ALLOWED_CIDRS against the real stack (spec §14.17) and the access log's user hash.

A TOTP-verified admin session is useless from outside the allowlist: the admin API answers
404 exactly as it does for non-admins, so the area is not confirmed to exist.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.logging import configure_logging
from app.main import create_app
from tests.conftest import _flush_redis
from tests.helpers import Api, stack_available, stack_settings

pytestmark = [pytest.mark.security, pytest.mark.api]

INSIDE = "203.0.113.9"
OUTSIDE = "198.51.100.1"
NGINX = "172.18.0.5"  # inside the default TRUSTED_PROXY_IPS (172.16.0.0/12)


@pytest.fixture
def clients(migrated: str) -> Iterator[dict[str, Api]]:
    """One app with an allowlist, reached from inside, outside and through the proxy."""
    if not stack_available():
        pytest.skip("needs the test compose stack")
    _flush_redis()
    app = create_app(stack_settings(ADMIN_ALLOWED_CIDRS=f"{INSIDE}/32, 2001:db8::/32"))
    peers = {"inside": INSIDE, "outside": OUTSIDE, "proxy": NGINX, "v6": "2001:db8::5"}
    opened = {
        name: TestClient(app, base_url="https://testserver", client=(ip, 50000))
        for name, ip in peers.items()
    }
    for c in opened.values():
        c.__enter__()
    try:
        yield {name: Api(c) for name, c in opened.items()}
    finally:
        for c in opened.values():
            c.__exit__(None, None, None)


def _share_session(source: Api, target: Api) -> None:
    for cookie in source.client.cookies.jar:
        target.client.cookies.set(cookie.name, cookie.value or "", domain=cookie.domain)


def test_admin_inside_the_allowlist_works(clients: dict[str, Api]) -> None:
    inside = clients["inside"]
    inside.sign_in_as("ADMIN")
    r = inside.get("/api/v1/admin/session")
    assert r.status_code == 200, r.text
    assert r.json()["totp_verified"] is True


def test_admin_session_from_outside_gets_the_non_admin_404(clients: dict[str, Api]) -> None:
    inside, outside = clients["inside"], clients["outside"]
    inside.sign_in_as("ADMIN")
    _share_session(inside, outside)
    assert outside.get("/api/v1/me").status_code == 200  # the session itself is valid
    refused = outside.get("/api/v1/admin/session")
    # A signed-in developer gets this same body from the router.
    dev = clients["v6"]
    dev.sign_in_as("DEVELOPER")
    hidden = dev.get("/api/v1/admin/session")
    assert refused.status_code == hidden.status_code == 404
    assert refused.json()["error"]["code"] == hidden.json()["error"]["code"] == "NOT_FOUND"
    assert refused.json()["error"]["message"] == hidden.json()["error"]["message"]


def test_spoofed_forwarded_for_from_outside_is_ignored(clients: dict[str, Api]) -> None:
    inside, outside = clients["inside"], clients["outside"]
    inside.sign_in_as("ADMIN")
    _share_session(inside, outside)
    r = outside.get("/api/v1/admin/session", headers={"X-Forwarded-For": INSIDE})
    assert r.status_code == 404


@pytest.mark.parametrize(("forwarded", "status"), [(INSIDE, 200), (OUTSIDE, 404)])
def test_forwarded_for_from_the_trusted_proxy_decides(
    clients: dict[str, Api], forwarded: str, status: int
) -> None:
    inside, proxy = clients["inside"], clients["proxy"]
    inside.sign_in_as("ADMIN")
    _share_session(inside, proxy)
    r = proxy.get("/api/v1/admin/session", headers={"X-Forwarded-For": forwarded})
    assert r.status_code == status


def test_ipv6_admin_inside_the_allowlist_works(clients: dict[str, Api]) -> None:
    v6 = clients["v6"]
    v6.sign_in_as("ADMIN")
    assert v6.get("/api/v1/admin/session").status_code == 200


def test_access_log_hashes_the_user_id(
    clients: dict[str, Api], capsys: pytest.CaptureFixture[str]
) -> None:
    # Another test may have left structlog at a higher level (an app built with production
    # settings configures logging on startup), which would drop the line we are asserting on.
    configure_logging("INFO")
    inside = clients["inside"]
    user = inside.sign_in_as("DEVELOPER")
    capsys.readouterr()
    assert inside.get("/api/v1/me").status_code == 200
    out = capsys.readouterr().out
    lines: list[dict[str, Any]] = []
    for line in out.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("event") == "http_request":
            lines.append(entry)
    assert len(lines) == 1
    assert lines[0]["route"] == "/api/v1/me"
    assert isinstance(lines[0]["user_hash"], str)
    assert len(lines[0]["user_hash"]) == 16
    assert user.user_id not in out
    assert user.email not in out
