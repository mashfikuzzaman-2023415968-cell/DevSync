"""Login, lockout, adaptive CAPTCHA, sessions, CSRF and cookies (spec §14.4, §14.6, §16.4)."""

from __future__ import annotations

import hashlib
import os
import statistics
import time
from datetime import timedelta

import pytest
import redis

from app.core import clock
from app.core.security import hash_password, verify_password
from tests.helpers import STRONG_PASSWORD, Api, unique_email

pytestmark = [pytest.mark.security, pytest.mark.api]


def clear_limits() -> None:
    """Forget rate-limit windows and delays but keep failure counters and sessions."""
    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    try:
        for pattern in ("rl:*", "auth:delay:*"):
            for key in client.scan_iter(pattern):
                client.delete(key)
    finally:
        client.close()


def login(api: Api, email: str, password: str, **extra: object) -> object:
    return api.post("/api/v1/auth/login", json={"email": email, "password": password, **extra})


# --------------------------------------------------------------------------- login basics


def test_uniform_error_for_wrong_password_and_unknown_email(api: Api) -> None:
    user = api.seed("CLIENT")
    wrong = login(api, user.email, "wrong password entirely 99")
    unknown = login(api, unique_email(), "wrong password entirely 99")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_password_check_timing_does_not_reveal_accounts() -> None:
    """Unknown accounts still cost one Argon2 verify (median difference < 50 ms over 50
    interleaved samples each, so background load affects both series equally)."""
    stored = hash_password("some real password 123!")

    def sample(stored_hash: str | None) -> float:
        start = time.perf_counter()
        verify_password(stored_hash, "attempted password 456!")
        return time.perf_counter() - start

    existing: list[float] = []
    missing: list[float] = []
    for _ in range(50):
        existing.append(sample(stored))
        missing.append(sample(None))
    assert abs(statistics.median(existing) - statistics.median(missing)) < 0.05


def test_login_success_sets_hardened_cookies(api: Api) -> None:
    user = api.seed("DEVELOPER")
    r = login(api, user.email, user.password)
    assert r.status_code == 200
    assert r.json() == {"status": "SIGNED_IN", "redirect_to": "/dev", "pre_auth": None}
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("__Host-ds_session="))
    for flag in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/"):
        assert flag in session
    assert "Domain" not in session
    csrf_cookie = next(c for c in cookies if c.startswith("__Host-ds_csrf="))
    assert "SameSite=Strict" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie


def test_return_to_is_validated(api: Api) -> None:
    user = api.seed("CLIENT")
    for target, expected in (
        ("//evil.com", "/client"),
        ("/client/projects/new", "/client/projects/new"),
    ):
        api.client.cookies.clear()
        clear_limits()
        r = login(api, user.email, user.password, return_to=target)
        assert r.json()["redirect_to"] == expected


def test_session_fixation_token_changes_on_login(api: Api) -> None:
    user = api.seed("CLIENT")
    api.replace_cookie("__Host-ds_session", "attacker-chosen-token-value")
    r = login(api, user.email, user.password)
    assert r.status_code == 200
    assert api.client.cookies.get("__Host-ds_session") != "attacker-chosen-token-value"


def test_suspended_session_cookie_is_ignored(api: Api) -> None:
    api.replace_cookie("__Host-ds_session", "x" * 43)
    assert api.get("/api/v1/me").status_code == 401


# --------------------------------------------------------------------------- abuse controls


def test_adaptive_captcha_after_three_failures(api: Api) -> None:
    user = api.seed("CLIENT")
    for _ in range(3):
        clear_limits()
        assert login(api, user.email, "wrong password entirely 99").status_code == 401
    clear_limits()
    r = login(api, user.email, user.password)  # correct password but no CAPTCHA now
    assert r.status_code == 403
    assert r.json()["error"]["captcha_required"] is True
    clear_limits()
    assert login(api, user.email, user.password, captcha="test-bypass").status_code == 200


def test_progressive_delay_after_five_failures(api: Api) -> None:
    user = api.seed("CLIENT")
    for _ in range(5):
        api.request(
            "POST",
            "/api/v1/auth/login",
            json={
                "email": user.email,
                "password": "wrong password entirely 99",
                "captcha": "test-bypass",
            },
        )
        for key in redis.Redis.from_url(os.environ["REDIS_URL"]).scan_iter("rl:*"):
            redis.Redis.from_url(os.environ["REDIS_URL"]).delete(key)
    r = login(api, user.email, user.password, captcha="test-bypass")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_lockout_after_ten_failures_and_email_notice(api: Api) -> None:
    user = api.seed("CLIENT")
    for _ in range(10):
        clear_limits()
        r = login(api, user.email, "wrong password entirely 99", captcha="test-bypass")
        assert r.status_code in {401, 423}
    clear_limits()
    r = login(api, user.email, user.password, captcha="test-bypass")
    assert r.status_code == 423
    assert r.json()["error"]["code"] == "ACCOUNT_LOCKED"
    assert 1 <= r.json()["error"]["locked_minutes"] <= 15
    link = api.get(
        "/api/v1/__test__/email-link", params={"to": user.email, "template": "account_locked"}
    ).json()["link"]
    assert link


def test_lock_expires(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    user = api.seed("CLIENT")
    for _ in range(10):
        clear_limits()
        login(api, user.email, "wrong password entirely 99", captcha="test-bypass")
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(minutes=16))
    monkeypatch.setattr(clock, "_clock", later)
    clear_limits()
    assert login(api, user.email, user.password, captcha="test-bypass").status_code == 200


def test_login_rate_limit(api: Api) -> None:
    email = unique_email()
    statuses = [
        login(api, email, "wrong password entirely 99", captcha="test-bypass").status_code
        for _ in range(6)
    ]
    assert statuses[-1] == 429


# --------------------------------------------------------------------------- CSRF


@pytest.mark.parametrize(
    ("csrf", "origin", "headers"),
    [
        (False, "https://testserver", {}),
        (False, "https://testserver", {"X-CSRF-Token": "forged.value"}),
        (True, "https://evil.example", {}),
        (True, None, {}),
    ],
)
def test_csrf_rejections(api: Api, csrf: bool, origin: str | None, headers: dict[str, str]) -> None:
    api.sign_in_as("CLIENT")
    r = api.request("POST", "/api/v1/auth/logout", csrf=csrf, origin=origin, headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"
    assert api.get("/api/v1/me").status_code == 200  # still signed in


def test_anonymous_token_is_not_valid_for_a_session(api: Api) -> None:
    anonymous_token = api.csrf_token()
    api.sign_in_as("CLIENT")
    r = api.request(
        "POST", "/api/v1/auth/logout", csrf=False, headers={"X-CSRF-Token": anonymous_token}
    )
    assert r.status_code == 403


def _echoed_token(api: Api) -> str:
    r = api.client.get("/api/v1/auth/csrf")
    assert r.status_code == 204
    assert r.headers["cache-control"] == "no-store"
    echoed = str(r.headers["x-csrf-token"])
    assert echoed == api.client.cookies.get("__Host-ds_csrf")
    return echoed


def test_csrf_endpoint_echoes_the_anonymous_token(api: Api) -> None:
    echoed = _echoed_token(api)
    r = api.request(
        "POST",
        "/api/v1/auth/password/forgot",
        csrf=False,
        headers={"X-CSRF-Token": echoed},
        json={"email": unique_email(), "captcha": "test-bypass"},
    )
    assert r.status_code == 202, r.text


def test_csrf_endpoint_echoes_the_session_token(api: Api) -> None:
    api.sign_in_as("CLIENT")
    echoed = _echoed_token(api)
    r = api.request("POST", "/api/v1/auth/logout", csrf=False, headers={"X-CSRF-Token": echoed})
    assert r.status_code == 204, r.text


def test_echoed_token_without_its_cookie_is_rejected(api: Api) -> None:
    r = api.client.get("/api/v1/auth/csrf")
    echoed = r.headers["x-csrf-token"]
    api.replace_cookie("__Host-ds_csrf", api.csrf_token())  # a different, valid token
    rejected = api.request(
        "POST",
        "/api/v1/auth/password/forgot",
        csrf=False,
        headers={"X-CSRF-Token": echoed},
        json={"email": unique_email()},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "CSRF_FAILED"


# --------------------------------------------------------------------------- session lifecycle


def test_logout_invalidates_session(api: Api) -> None:
    api.sign_in_as("CLIENT")
    token = api.client.cookies.get("__Host-ds_session")
    assert api.post("/api/v1/auth/logout").status_code == 204
    api.replace_cookie("__Host-ds_session", token or "")
    assert api.get("/api/v1/me").status_code == 401


def test_logout_all_invalidates_other_browser(api: Api, api2: Api) -> None:
    user = api.sign_in_as("CLIENT")
    assert api2.login(user).status_code == 200
    assert api2.get("/api/v1/me").status_code == 200
    assert api.post("/api/v1/auth/logout-all").status_code == 204
    assert api2.get("/api/v1/me").status_code == 401
    assert api.get("/api/v1/me").status_code == 401


def test_sessions_list_and_revoke(api: Api, api2: Api) -> None:
    user = api.sign_in_as("DEVELOPER")
    assert api2.login(user).status_code == 200
    items = api.get("/api/v1/auth/sessions").json()["items"]
    assert len(items) == 2
    other = next(i for i in items if not i["current"])
    assert api.delete(f"/api/v1/auth/sessions/{other['id']}").status_code == 204
    assert api2.get("/api/v1/me").status_code == 401
    assert api.delete(f"/api/v1/auth/sessions/{other['id']}").status_code == 404


def test_idor_other_users_session_is_404(api: Api, api2: Api) -> None:
    api.sign_in_as("CLIENT")
    api2.sign_in_as("DEVELOPER")
    victim_session = api2.get("/api/v1/auth/sessions").json()["items"][0]["id"]
    assert api.delete(f"/api/v1/auth/sessions/{victim_session}").status_code == 404
    assert api2.get("/api/v1/me").status_code == 200


def test_rotation_after_fifteen_minutes_with_grace(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    api.sign_in_as("CLIENT")
    old = api.client.cookies.get("__Host-ds_session")
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(minutes=16))
    monkeypatch.setattr(clock, "_clock", later)
    r = api.get("/api/v1/me")
    assert r.status_code == 200
    new = api.client.cookies.get("__Host-ds_session")
    assert new
    assert new != old
    # The old token still works during the 30-second grace window.
    api.replace_cookie("__Host-ds_session", old or "")
    assert api.get("/api/v1/me").status_code == 200


def test_idle_timeout(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    api.sign_in_as("CLIENT")
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(minutes=31))
    monkeypatch.setattr(clock, "_clock", later)
    assert api.get("/api/v1/me").status_code == 401


def test_session_survives_redis_loss_via_database(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    token = api.client.cookies.get("__Host-ds_session") or ""
    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    try:
        client.delete("sess:" + hashlib.sha256(token.encode()).hexdigest())
    finally:
        client.close()
    assert api.get("/api/v1/me").status_code == 200


def test_get_requests_never_mutate(api: Api) -> None:
    api.sign_in_as("CLIENT")
    fingerprint_before = api.get("/api/v1/me").json()
    for path in ("/api/v1/me", "/api/v1/auth/sessions", "/api/v1/auth/csrf", "/api/v1/health"):
        api.get(path)
    assert api.get("/api/v1/me").json() == fingerprint_before
    assert len(api.get("/api/v1/auth/sessions").json()["items"]) == 1


# --------------------------------------------------------------------------- passwords


def test_forgot_password_is_uniform_and_reset_revokes_sessions(api: Api, api2: Api) -> None:
    from tests.security.test_registration_verification import email_token  # noqa: PLC0415

    user = api.seed("CLIENT")
    assert api2.login(user).status_code == 200
    known = api.post(
        "/api/v1/auth/password/forgot", json={"email": user.email, "captcha": "test-bypass"}
    )
    unknown = api.post(
        "/api/v1/auth/password/forgot", json={"email": unique_email(), "captcha": "test-bypass"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()

    token = email_token(api, user.email, "reset_password")
    new_password = "a brand new passphrase 77!"
    reset = api.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": new_password}
    )
    assert reset.status_code == 204
    assert api2.get("/api/v1/me").status_code == 401  # every session revoked
    clear_limits()  # four reset requests in a row would (correctly) hit the 3/hour limit
    assert (
        api.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": new_password}
        ).status_code
        == 400
    )
    clear_limits()
    assert login(api, user.email, new_password).status_code == 200


def test_reset_token_expires(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.security.test_registration_verification import email_token  # noqa: PLC0415

    user = api.seed("CLIENT")
    api.post("/api/v1/auth/password/forgot", json={"email": user.email, "captcha": "test-bypass"})
    token = email_token(api, user.email, "reset_password")
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(minutes=31))
    monkeypatch.setattr(clock, "_clock", later)
    r = api.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": "a brand new passphrase 77!"},
    )
    assert r.status_code == 400


def test_change_password(api: Api, api2: Api) -> None:
    user = api.sign_in_as("DEVELOPER")
    assert api2.login(user).status_code == 200
    wrong = api.post(
        "/api/v1/auth/password/change",
        json={"current_password": "not it at all 123", "new_password": "x"},
    )
    assert wrong.status_code == 401
    weak = api.post(
        "/api/v1/auth/password/change",
        json={"current_password": user.password, "new_password": "password123"},
    )
    assert weak.status_code == 422
    ok = api.post(
        "/api/v1/auth/password/change",
        json={"current_password": user.password, "new_password": "another strong phrase 31!"},
    )
    assert ok.status_code == 204
    assert api.get("/api/v1/me").status_code == 200  # this session continues
    assert api2.get("/api/v1/me").status_code == 401  # others are signed out


def test_password_reset_rate_limit(api: Api) -> None:
    statuses = [
        api.post(
            "/api/v1/auth/password/forgot", json={"email": unique_email(), "captcha": "test-bypass"}
        ).status_code
        for _ in range(4)
    ]
    assert statuses == [202, 202, 202, 429]


def test_strong_password_constant_is_valid() -> None:
    from app.core.security import password_problems  # noqa: PLC0415

    assert password_problems(STRONG_PASSWORD) == []
