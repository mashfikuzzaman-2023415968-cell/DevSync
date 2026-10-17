"""Authorization matrix: every API route × every role (spec §2.2, §14.5, §16.4).

Adding a route without an entry here fails `test_every_route_has_a_matrix_entry`.
For each role the test asserts the exact gate outcome:
- anonymous → 401 (admin area → 404, public routes → passes the gate),
- wrong role → 403 (admin/TOTP area → 404 so it isn't confirmed to exist),
- PENDING accounts → 403 VERIFICATION_REQUIRED where an active account is needed,
- allowed roles → anything except 401/403/404 (validation or state errors are fine;
  routes addressing a specific object may answer 404 for a random id — IDOR is
  tested separately with real objects).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core.config import Environment, Settings
from app.main import create_app
from tests.helpers import STRONG_PASSWORD, Api

pytestmark = [pytest.mark.security, pytest.mark.api]

ANON, PENDING, CLIENT, DEV, ADMIN = "anonymous", "pending", "client", "developer", "admin"
EVERYONE = {ANON, PENDING, CLIENT, DEV, ADMIN}
SIGNED_IN = {PENDING, CLIENT, DEV, ADMIN}
ACTIVE = {CLIENT, DEV, ADMIN}
HIDDEN = "hidden"  # non-allowed roles get 404 (admin area)

# (method, path) -> (allowed roles, how the others are refused, object-scoped?)
MATRIX: dict[tuple[str, str], tuple[set[str], str, bool]] = {
    ("GET", "/api/v1/health"): (EVERYONE, "", False),
    ("GET", "/api/v1/health/ready"): (EVERYONE, "", False),
    ("GET", "/api/v1/captcha/challenge"): (EVERYONE, "", False),
    ("GET", "/api/v1/auth/csrf"): (EVERYONE, "", False),
    ("POST", "/api/v1/auth/register"): (EVERYONE, "", False),
    ("POST", "/api/v1/auth/login"): (EVERYONE, "", False),
    ("POST", "/api/v1/auth/login/totp"): (EVERYONE, "", False),
    ("POST", "/api/v1/auth/email/verify"): (EVERYONE, "", False),
    ("POST", "/api/v1/auth/password/forgot"): (EVERYONE, "", False),
    ("POST", "/api/v1/auth/password/reset"): (EVERYONE, "", False),
    ("POST", "/api/v1/auth/logout"): (SIGNED_IN, "auth", False),
    ("POST", "/api/v1/auth/logout-all"): (SIGNED_IN, "auth", False),
    ("GET", "/api/v1/auth/sessions"): (SIGNED_IN, "auth", False),
    ("DELETE", "/api/v1/auth/sessions/{session_id}"): (SIGNED_IN, "auth", True),
    ("POST", "/api/v1/auth/otp/send"): (SIGNED_IN, "auth", False),
    ("POST", "/api/v1/auth/otp/verify"): (SIGNED_IN, "auth", False),
    ("POST", "/api/v1/auth/email/resend"): (SIGNED_IN, "auth", False),
    ("POST", "/api/v1/auth/password/change"): (ACTIVE, "auth", False),
    ("POST", "/api/v1/auth/totp/setup"): ({ADMIN}, HIDDEN, False),
    ("POST", "/api/v1/auth/totp/confirm"): ({ADMIN}, HIDDEN, False),
    ("POST", "/api/v1/auth/recovery-codes/regenerate"): ({ADMIN}, HIDDEN, False),
    ("POST", "/api/v1/auth/step-up"): ({ADMIN}, HIDDEN, False),
    ("GET", "/api/v1/me"): (SIGNED_IN, "auth", False),
    ("PATCH", "/api/v1/me"): (ACTIVE, "auth", False),
    ("GET", "/api/v1/admin/session"): ({ADMIN}, HIDDEN, False),
}

BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/api/v1/auth/otp/verify"): {"code": "123456"},
    ("POST", "/api/v1/auth/totp/confirm"): {"code": "123456"},
    ("POST", "/api/v1/auth/step-up"): {"code": "123456"},
    ("POST", "/api/v1/auth/password/change"): {
        "current_password": STRONG_PASSWORD,
        "new_password": "another strong phrase 31!",
    },
    ("PATCH", "/api/v1/me"): {"display_name": "Matrix"},
}


def _openapi_routes() -> set[tuple[str, str]]:
    app = create_app(
        Settings(DEVSYNC_ENV=Environment.DEVELOPMENT, ALLOWED_HOSTS="testserver",
                 SECRET_KEY="k" * 64, CAPTCHA_HMAC_KEY="c" * 32)
    )  # fmt: skip
    return {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }


def test_every_route_has_a_matrix_entry() -> None:
    routes = _openapi_routes()
    missing = routes - MATRIX.keys()
    stale = MATRIX.keys() - routes
    assert not missing, f"routes without an authorization-matrix entry: {sorted(missing)}"
    assert not stale, f"matrix entries for routes that no longer exist: {sorted(stale)}"


def _become(api: Api, role: str) -> None:
    if role == ANON:
        return
    if role == PENDING:
        api.sign_in_as("DEVELOPER", verified=False)
    else:
        api.sign_in_as({"client": "CLIENT", "developer": "DEVELOPER", "admin": "ADMIN"}[role])


# Signing out ends the session, so those two run last for each role.
_LAST = {("POST", "/api/v1/auth/logout"), ("POST", "/api/v1/auth/logout-all")}
PROTECTED = sorted(
    ((k, v) for k, v in MATRIX.items() if v[0] != EVERYONE), key=lambda kv: kv[0] in _LAST
)
# Error codes that mean "refused by the authorization gate" (anything else is business logic,
# e.g. a wrong TOTP code or a missing step-up, which proves the gate let the role through).
GATE_CODES = {"UNAUTHENTICATED", "ROLE_NOT_ALLOWED", "VERIFICATION_REQUIRED", "CSRF_FAILED"}


def _code(r: Any) -> str | None:
    try:
        return str(r.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return None


@pytest.mark.parametrize("role", [ANON, PENDING, CLIENT, DEV, ADMIN])
def test_matrix(api: Api, role: str) -> None:
    _become(api, role)
    failures = []
    for (method, path), (allowed, refusal, object_scoped) in PROTECTED:
        if (method, path) in _LAST:
            api.client.cookies.clear()
            _become(api, role)  # each sign-out route gets a fresh session
        url = path.replace("{session_id}", str(uuid.uuid4()))
        body = BODIES.get((method, path))
        r = api.request(method, url, json=body) if body is not None else api.request(method, url)
        status = r.status_code
        if role in allowed:
            ok = _code(r) not in GATE_CODES and (status != 404 or object_scoped)
        elif refusal == HIDDEN:
            ok = status == 404
        elif role == ANON:
            ok = status == 401
        elif role == PENDING:
            ok = status == 403 and r.json()["error"]["code"] == "VERIFICATION_REQUIRED"
        else:
            ok = status == 403
        if not ok:
            failures.append(f"{role} {method} {path} -> {status}")
    assert not failures, failures
