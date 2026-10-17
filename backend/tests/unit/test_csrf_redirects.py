"""CSRF tokens/origin checks and the open-redirect validator (spec §14.6)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core import csrf
from app.core.redirects import is_safe_path, role_home, safe_redirect

pytestmark = pytest.mark.unit

KEY = b"k" * 32
ORIGIN = "https://devsync.example"


def test_token_round_trip() -> None:
    token = csrf.issue_token(KEY)
    assert csrf.token_is_valid(token, KEY)
    assert not csrf.token_is_valid(token, b"other" * 8)


@pytest.mark.parametrize("bad", ["", "nodot", "a.b.c", "x" * 300, "abc.def"])
def test_malformed_tokens_are_invalid(bad: str) -> None:
    assert not csrf.token_is_valid(bad, KEY)


@pytest.mark.parametrize(
    ("origin", "referer", "ok"),
    [
        (ORIGIN, None, True),
        (None, ORIGIN + "/client", True),
        ("https://evil.example", None, False),
        ("http://devsync.example", None, False),
        ("https://devsync.example:8443", None, False),
        ("null", None, False),
        (None, None, False),
        ("null", "https://evil.example/x", False),
    ],
)
def test_origin_check(origin: str | None, referer: str | None, ok: bool) -> None:
    assert csrf.origin_allowed(origin, referer, ORIGIN) is ok


def test_full_request_check() -> None:
    token = csrf.issue_token(KEY)
    common = {"key": KEY, "origin": ORIGIN, "referer": None, "public_origin": ORIGIN}
    assert csrf.request_is_valid(cookie_token=token, header_token=token, **common)
    assert not csrf.request_is_valid(cookie_token=token, header_token=None, **common)
    assert not csrf.request_is_valid(cookie_token=None, header_token=token, **common)
    other = csrf.issue_token(KEY)
    assert not csrf.request_is_valid(cookie_token=token, header_token=other, **common)
    forged = token.split(".")[0] + ".forgedsignature"
    assert not csrf.request_is_valid(cookie_token=forged, header_token=forged, **common)


@pytest.mark.parametrize(
    "target",
    ["/", "/client", "/client/projects/new", "/dev/bids/abc-123", "/admin", "/p/123", "/verify"],
)
def test_safe_paths(target: str) -> None:
    assert is_safe_path(target)


@pytest.mark.parametrize(
    "target",
    [
        "//evil.com",
        "https://evil.com",
        "/\\evil.com",
        "javascript:alert(1)",
        "/%2F%2Fevil.com",
        "/client\n/x",
        "/unknown-route",
        "",
        None,
        "client",
        "/" + "a" * 600,
        "/%5Cevil.com",
    ],
)
def test_unsafe_paths_fall_back_to_role_home(target: str | None) -> None:
    assert not is_safe_path(target)
    assert safe_redirect(target, "CLIENT") == "/client"


def test_role_homes_and_pending() -> None:
    assert role_home("DEVELOPER") == "/dev"
    assert role_home("ADMIN") == "/admin"
    assert role_home(None) == "/"
    assert role_home("CLIENT", "PENDING") == "/verify"
    assert safe_redirect("/client", "CLIENT", "PENDING") == "/verify"


@given(st.text(max_size=200))
def test_property_safe_redirect_never_leaves_the_site(target: str) -> None:
    result = safe_redirect(target, "DEVELOPER")
    assert result.startswith("/")
    assert not result.startswith("//")
    assert "\\" not in result
    assert "://" not in result
