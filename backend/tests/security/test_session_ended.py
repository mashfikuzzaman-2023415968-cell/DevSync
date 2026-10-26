"""A 401 says why a session no longer works: expired or suspended (spec §13.4, §14.4).

Only a request that *carried* a session cookie gets SESSION_EXPIRED / ACCOUNT_SUSPENDED;
anonymous requests keep the plain UNAUTHENTICATED, and a deleted account never reads as
suspended. Login of a suspended account says so only after the right password.
"""

from __future__ import annotations

import hashlib
import os
from datetime import timedelta

import pytest
import redis
from sqlalchemy import create_engine, text

from app.core import clock
from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]


def _code(r: object) -> str:
    return str(r.json()["error"]["code"])  # type: ignore[attr-defined]


def _set_status(migration_url: str, user_id: str, status: str, api: Api) -> None:
    engine = create_engine(migration_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET status = :s WHERE id = :id"), {"s": status, "id": user_id}
        )
    engine.dispose()
    # The cached session still says ACTIVE; drop it so the next request reads the database.
    token = api.client.cookies.get("__Host-ds_session") or ""
    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    try:
        client.delete("sess:" + hashlib.sha256(token.encode()).hexdigest())
    finally:
        client.close()


def test_anonymous_is_plain_unauthenticated(api: Api) -> None:
    r = api.get("/api/v1/me")
    assert r.status_code == 401
    assert _code(r) == "UNAUTHENTICATED"


def test_unknown_or_expired_cookie_is_session_expired_once(api: Api) -> None:
    api.replace_cookie("__Host-ds_session", "x" * 43)
    r = api.get("/api/v1/me")
    assert r.status_code == 401
    assert _code(r) == "SESSION_EXPIRED"
    # Worded for both a timeout and a sign-out from another device; the code says which case.
    assert "session ended" in r.json()["error"]["message"]
    # The cookie was cleared, so the next request is simply anonymous.
    assert _code(api.get("/api/v1/me")) == "UNAUTHENTICATED"


def test_idle_timeout_reads_as_session_expired(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    api.sign_in_as("CLIENT")
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(minutes=31))
    monkeypatch.setattr(clock, "_clock", later)
    r = api.get("/api/v1/projects")
    assert r.status_code == 401
    assert _code(r) == "SESSION_EXPIRED"


def test_suspended_account_session_reads_as_suspended(api: Api, migration_url: str) -> None:
    user = api.sign_in_as("DEVELOPER")
    _set_status(migration_url, user.user_id, "SUSPENDED", api)
    r = api.get("/api/v1/me")
    assert r.status_code == 401
    assert _code(r) == "ACCOUNT_SUSPENDED"
    assert "suspended" in r.json()["error"]["message"]


def test_deleted_account_session_is_not_called_suspended(api: Api, migration_url: str) -> None:
    user = api.sign_in_as("DEVELOPER")
    _set_status(migration_url, user.user_id, "DELETED", api)
    r = api.get("/api/v1/me")
    assert r.status_code == 401
    assert _code(r) == "SESSION_EXPIRED"


def test_public_routes_are_unaffected_by_an_ended_cookie(api: Api) -> None:
    api.replace_cookie("__Host-ds_session", "x" * 43)
    assert api.get("/api/v1/public/stats").status_code == 200


def test_suspended_login_needs_the_right_password_to_say_so(api: Api, migration_url: str) -> None:
    user = api.seed("CLIENT")
    _set_status(migration_url, user.user_id, "SUSPENDED", api)
    api.get("/api/v1/__test__/ratelimits/reset")
    wrong = api.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "not the password 123"}
    )
    assert _code(wrong) == "INVALID_CREDENTIALS"  # no enumeration of the account's status
    api.get("/api/v1/__test__/ratelimits/reset")
    right = api.login(user)
    assert right.status_code == 401
    assert _code(right) == "ACCOUNT_SUSPENDED"
