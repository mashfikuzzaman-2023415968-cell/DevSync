"""Pre-presentation checks, ~30 minutes before a demo (spec §17.0): Docker is up, the HTTPS edge
answers, there is enough disk, the seed is loaded, and the seeded client can actually sign in
through the login API (the `.local` demo emails once failed validation there, D54). Run on the
host: `make demo-preflight`.

Network checks go through the running edge (`https://localhost`) rather than the database, so no
DB port needs exposing. Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

EDGE = "https://localhost"
MIN_FREE_GB = 2.0
ROOT = Path(__file__).resolve().parent.parent.parent


def _ok(label: str, passed: bool, detail: str = "") -> bool:
    print(f"  [{'OK ' if passed else 'FAIL'}] {label}{f': {detail}' if detail else ''}")
    return passed


def _tls() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # dev/demo cert is locally trusted; demo accounts only
    return ctx


def _get_json(path: str) -> object:
    with urllib.request.urlopen(f"{EDGE}{path}", timeout=5, context=_tls()) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _client_account(stage: int) -> tuple[str, str] | None:
    """(email, password) of the seeded client from `runs/demos/accounts-N.txt` (gitignored)."""
    path = ROOT / "runs" / "demos" / f"accounts-{stage}.txt"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[0] == "client":
            return parts[1], parts[2].strip()
    return None


def _can_sign_in(email: str, password: str) -> tuple[bool, str]:
    """Sign in through the real login API (CSRF cookie + header + Origin), then sign out."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=_tls())
    )
    opener.open(f"{EDGE}/api/v1/auth/csrf", timeout=5)
    token = next((c.value for c in jar if c.name == "__Host-ds_csrf"), "")
    headers = {"Content-Type": "application/json", "X-CSRF-Token": token, "Origin": EDGE}
    body = json.dumps(
        {"email": email, "password": password, "started_at_ms": int(time.time() * 1000) - 5000}
    ).encode()
    request = urllib.request.Request(  # noqa: S310 - fixed https URL
        f"{EDGE}/api/v1/auth/login", data=body, headers=headers, method="POST"
    )
    try:
        with opener.open(request, timeout=10) as r:
            status = json.loads(r.read().decode()).get("status")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} for {email}"
    # Signing in rotates the session and re-issues the CSRF cookie; sign out with the new one.
    headers["X-CSRF-Token"] = next((c.value for c in jar if c.name == "__Host-ds_csrf"), "")
    opener.open(
        urllib.request.Request(  # noqa: S310 - fixed https URL
            f"{EDGE}/api/v1/auth/logout", data=b"", headers=headers, method="POST"
        ),
        timeout=5,
    )
    return status == "SIGNED_IN", f"{email} signed in" if status == "SIGNED_IN" else str(status)


def main() -> int:
    parser = argparse.ArgumentParser(description="DevSync demo preflight")
    parser.add_argument("--stage", type=int, default=1)
    args = parser.parse_args()
    print("demo-preflight:")
    checks: list[bool] = []

    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        checks.append(_ok("Docker is running", True))
    except (subprocess.CalledProcessError, FileNotFoundError):
        checks.append(_ok("Docker is running", False, "start Docker Desktop"))

    free_gb = shutil.disk_usage("/").free / 1e9
    checks.append(_ok("Disk space", free_gb >= MIN_FREE_GB, f"{free_gb:.1f} GB free"))

    try:
        health = _get_json("/api/v1/health")
        checks.append(_ok("HTTPS edge answers", isinstance(health, dict)))
    except Exception as exc:
        checks.append(_ok("HTTPS edge answers", False, f"{type(exc).__name__}: run `make demo-up`"))

    try:
        page = _get_json("/api/v1/public/projects?q=ordering")
        items = page.get("items", []) if isinstance(page, dict) else []
        seeded = any(
            isinstance(i, dict) and i.get("title") == "Online ordering system" for i in items
        )
        checks.append(
            _ok(
                "Seed loaded",
                seeded,
                "found the ordering-system project" if seeded else "run `make demo-reset`",
            )
        )
    except Exception as exc:
        checks.append(_ok("Seed loaded", False, f"{type(exc).__name__}"))

    account = _client_account(args.stage)
    if account is None:
        checks.append(_ok("Demo client signs in", False, "no accounts file: run `make demo-reset`"))
    else:
        try:
            checks.append(_ok("Demo client signs in", *_can_sign_in(*account)))
        except Exception as exc:
            checks.append(_ok("Demo client signs in", False, type(exc).__name__))

    passed = all(checks)
    print(f"demo-preflight: {'ready' if passed else 'NOT ready'} ({sum(checks)}/{len(checks)})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
