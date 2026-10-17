"""Helpers for API and security tests against the real stack (Postgres + Redis).

`Api` wraps a TestClient on `https://testserver` so `__Host-` cookies work, and
adds the CSRF header and Origin automatically for unsafe methods (tests that
check CSRF itself pass `csrf=False`).
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pyotp
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings

ORIGIN = "https://testserver"
STRONG_PASSWORD = "correct horse battery staple 42!"


def stack_available() -> bool:
    """True inside the test compose stack."""
    return bool(os.environ.get("DATABASE_URL") and os.environ.get("REDIS_URL"))


def stack_settings(**overrides: Any) -> Settings:
    """Settings for the in-process app pointed at the stack's Postgres/Redis."""
    values: dict[str, Any] = {
        "DEVSYNC_ENV": Environment.TEST,
        "ALLOWED_HOSTS": "testserver",
        "PUBLIC_ORIGIN": ORIGIN,
        "SECRET_KEY": os.environ.get("SECRET_KEY", "test-secret-key-" * 4),
        "CAPTCHA_HMAC_KEY": os.environ.get("CAPTCHA_HMAC_KEY", "test-captcha-key-" * 2),
        "SMS_PROVIDER": "noop",
    }
    values.update(overrides)
    return Settings(**values)


def unique_email(prefix: str = "user") -> str:
    """Fresh email per test (tests share one database)."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def unique_phone() -> str:
    """Fresh Bangladeshi mobile number in E.164."""
    return "+88017" + str(uuid.uuid4().int)[:8]


@dataclass
class SeededUser:
    """A user created through the test seed router."""

    user_id: str
    email: str
    password: str
    role: str
    phone: str | None = None
    totp_secret: str | None = None
    recovery_codes: list[str] = field(default_factory=list)


class Api:
    """HTTPS test client with automatic CSRF handling."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def replace_cookie(self, name: str, value: str) -> None:
        """Overwrite a cookie the way the server would (same domain/path), never duplicating it."""
        jar = self.client.cookies.jar
        for cookie in list(jar):
            if cookie.name == name:
                jar.clear(cookie.domain, cookie.path, cookie.name)
        self.client.cookies.set(name, value, domain="testserver.local", path="/")

    def csrf_token(self) -> str:
        """Fetch (or refresh) the CSRF cookie and return its value."""
        r = self.client.get("/api/v1/auth/csrf")
        assert r.status_code == 204, r.text
        token = self.client.cookies.get("__Host-ds_csrf")
        assert token
        return token

    def request(
        self, method: str, path: str, *, csrf: bool = True, origin: str | None = ORIGIN, **kw: Any
    ) -> Any:
        """Send a request; unsafe methods get `X-CSRF-Token` and `Origin` unless disabled."""
        headers = dict(kw.pop("headers", {}) or {})
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            if csrf:
                headers.setdefault("X-CSRF-Token", self.csrf_token())
            if origin:
                headers.setdefault("Origin", origin)
        return self.client.request(method, path, headers=headers, **kw)

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.request("POST", path, **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self.request("PATCH", path, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.request("DELETE", path, **kw)

    # ----------------------------------------------------------------- shortcuts

    def seed(
        self,
        role: str,
        *,
        verified: bool = True,
        with_totp: bool = True,
        password: str = STRONG_PASSWORD,
    ) -> SeededUser:
        """Create a user via the test-only router."""
        email = unique_email(role.lower())
        phone = None if role == "ADMIN" else unique_phone()
        r = self.post(
            "/api/v1/__test__/seed/user",
            json={
                "role": role,
                "email": email,
                "phone": phone,
                "password": password,
                "verified": verified,
                "with_totp": with_totp,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        return SeededUser(
            user_id=body["user_id"],
            email=email,
            password=password,
            role=role,
            phone=phone,
            totp_secret=body["totp_secret"],
            recovery_codes=body["recovery_codes"],
        )

    def login(self, user: SeededUser, **extra: Any) -> Any:
        """Password login (+ TOTP for admins with a secret). Returns the final response."""
        r = self.post(
            "/api/v1/auth/login",
            json={
                "email": user.email,
                "password": user.password,
                "captcha": "test-bypass",
                **extra,
            },
        )
        if r.status_code == 200 and r.json().get("status") == "TOTP_REQUIRED":
            assert user.totp_secret
            code = pyotp.TOTP(user.totp_secret).now()
            r = self.post(
                "/api/v1/auth/login/totp", json={"pre_auth": r.json()["pre_auth"], "code": code}
            )
        return r

    def sign_in_as(self, role: str, **seed_kw: Any) -> SeededUser:
        """Seed and sign in; asserts success."""
        user = self.seed(role, **seed_kw)
        r = self.login(user)
        assert r.status_code == 200, r.text
        return user


def wait_for_next_totp_window(secret: str) -> str:
    """Code from the next 30-second window (for replay tests that need a fresh step)."""
    totp = pyotp.TOTP(secret)
    first = totp.now()
    deadline = time.time() + 31
    while time.time() < deadline:
        code = totp.now()
        if code != first:
            return code
        time.sleep(0.5)
    return totp.now()
