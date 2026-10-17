"""Nginx edge behaviour against the running test stack (spec §14.3, §15.3, Phase 0 tests).

Run from the `tests` container on the `edge` network: EDGE_BASE_URL=https://nginx:8443.
The dev certificate is self-signed, so TLS verification is off here only.
"""

from __future__ import annotations

import os
import re
import ssl

import httpx
import pytest

pytestmark = pytest.mark.edge

BASE = os.environ.get("EDGE_BASE_URL", "")
HTTP = os.environ.get("EDGE_HTTP_URL", "")
HOST = {"Host": "localhost"}

# style-src carries a per-response nonce (DECISIONS D23); everything else is fixed.
EXPECTED_CSP = re.compile(
    r"default-src 'self'; script-src 'self'; style-src 'self' 'nonce-(?P<nonce>[0-9a-f]{32})'; "
    r"img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
    r"base-uri 'none'; form-action 'self'; object-src 'none'; upgrade-insecure-requests"
)

if not BASE:
    pytest.skip("EDGE_BASE_URL not set (edge tests run in the test stack)", allow_module_level=True)


@pytest.fixture(scope="module")
def edge() -> httpx.Client:
    return httpx.Client(base_url=BASE, verify=False, headers=HOST, timeout=10)


def test_http_redirects_to_https() -> None:
    r = httpx.get(f"{HTTP}/some/page?x=1", headers=HOST, follow_redirects=False, timeout=10)
    assert r.status_code == 301
    assert r.headers["location"] == "https://localhost/some/page?x=1"


def test_spa_has_exact_csp_and_security_headers(edge: httpx.Client) -> None:
    r = edge.get("/")
    assert r.status_code == 200
    assert EXPECTED_CSP.fullmatch(r.headers["content-security-policy"])
    assert "unsafe-inline" not in r.headers["content-security-policy"]
    assert r.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert r.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=(), payment=()"
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_style_nonce_matches_the_page_and_changes_per_response(edge: httpx.Client) -> None:
    nonces = []
    for path in ("/", "/login", "/some/unknown/page"):
        r = edge.get(path)
        match = EXPECTED_CSP.fullmatch(r.headers["content-security-policy"])
        assert match
        nonce = match.group("nonce")
        assert f'<meta name="csp-nonce" content="{nonce}"' in r.text
        assert "__CSP_NONCE__" not in r.text
        nonces.append(nonce)
    assert len(set(nonces)) == len(nonces)


def test_server_version_is_hidden(edge: httpx.Client) -> None:
    server = edge.get("/").headers.get("server", "")
    assert not any(ch.isdigit() for ch in server)


def test_api_health_through_nginx(edge: httpx.Client) -> None:
    r = edge.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-request-id"]
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/metrics", "/api/v1/health/ready"])
def test_internal_endpoints_are_not_reachable(edge: httpx.Client, path: str) -> None:
    assert edge.get(path).status_code == 404


def test_trace_is_blocked(edge: httpx.Client) -> None:
    assert edge.request("TRACE", "/").status_code == 405


def test_unknown_method_is_blocked(edge: httpx.Client) -> None:
    assert edge.request("PROPFIND", "/api/v1/health").status_code == 405


def test_oversize_body_is_413(edge: httpx.Client) -> None:
    r = edge.post("/api/v1/health", content=b"x" * (1024 * 1024 + 1))
    assert r.status_code == 413


def test_spa_fallback_serves_index(edge: httpx.Client) -> None:
    r = edge.get("/some/client/route")
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_unknown_host_is_rejected_by_api(edge: httpx.Client) -> None:
    r = edge.get("/api/v1/health", headers={"Host": "evil.example"})
    assert r.status_code == 400


def test_tls_1_1_is_refused() -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.maximum_version = ssl.TLSVersion.TLSv1_1
    ctx.minimum_version = ssl.TLSVersion.TLSv1
    host, port = BASE.removeprefix("https://").split(":")
    import socket  # noqa: PLC0415

    with (
        socket.create_connection((host, int(port)), timeout=5) as sock,
        pytest.raises(ssl.SSLError),
    ):
        ctx.wrap_socket(sock, server_hostname="localhost")
