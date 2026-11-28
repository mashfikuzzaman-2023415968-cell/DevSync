"""A signed-in session for the DAST scan (gate step 17, D157). Runs in the `tests` container.

Seeds a fresh, verified developer through the test-only router and signs in through Nginx, as
a browser would (HTTPS, `Host: localhost`, same-origin `Origin`, CSRF token). Prints one JSON
line `{"cookie": "..."}` for `zap_scan.py`, which hands it to ZAP and never writes it to a log.
The test stack's certificate is self-signed, so TLS verification is off for this target only.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import uuid

import httpx

BASE = os.environ.get("EDGE_BASE_URL", "https://nginx:8443")
# The test stack's PUBLIC_ORIGIN (docker-compose.test.yml), as a browser on it would send.
HEADERS = {"Host": "localhost:8443", "Origin": "https://localhost:8443"}
OK = 200


def _code(r: httpx.Response) -> str:
    """The error code only (never the body: it could echo input)."""
    try:
        return str(r.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return "no error body"


def main() -> int:
    with httpx.Client(base_url=BASE, verify=False, headers=HEADERS, timeout=30) as client:  # noqa: S501 - self-signed test-stack certificate, this target only

        def token() -> str:
            r = client.get("/api/v1/auth/csrf")
            r.raise_for_status()
            return str(r.headers.get("x-csrf-token") or client.cookies.get("__Host-ds_csrf"))

        email = f"zap-{uuid.uuid4().hex[:10]}@example.com"
        phone = "+88017" + str(uuid.uuid4().int)[:8]
        password = f"zap scan {secrets.token_urlsafe(18)} 9!"  # new each run, never shown
        seeded = client.post(
            "/api/v1/__test__/seed/user",
            json={
                "role": "DEVELOPER",
                "email": email,
                "phone": phone,
                "password": password,
                "verified": True,
                "with_totp": False,
            },
            headers={"X-CSRF-Token": token()},
        )
        if seeded.status_code != OK:
            print(
                f"zap_session: seeding failed ({seeded.status_code} {_code(seeded)})",
                file=sys.stderr,
            )
            return 1
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "captcha": "test-bypass"},
            headers={"X-CSRF-Token": token()},
        )
        if login.status_code != OK:
            print(
                f"zap_session: sign-in failed ({login.status_code} {_code(login)})",
                file=sys.stderr,
            )
            return 1
        cookies = {k: v for k, v in client.cookies.items() if k.startswith("__Host-ds_")}
        if "__Host-ds_session" not in cookies:
            print("zap_session: no session cookie", file=sys.stderr)
            return 1
        cookie = "; ".join(f"{k}={v}" for k, v in sorted(cookies.items()))
        print(json.dumps({"cookie": cookie, "user_id": seeded.json().get("user_id")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
