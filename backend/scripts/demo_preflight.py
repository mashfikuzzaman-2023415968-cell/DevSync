"""Pre-presentation checks, ~30 minutes before a demo (spec §17.0): Docker is up, the HTTPS edge
answers, there is enough disk, and the seed is loaded. Run on the host: `make demo-preflight`.

Network checks go through the running edge (`https://localhost`) rather than the database, so no
DB port needs exposing. Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import json
import shutil
import ssl
import subprocess
import urllib.request

EDGE = "https://localhost"
MIN_FREE_GB = 2.0


def _ok(label: str, passed: bool, detail: str = "") -> bool:
    print(f"  [{'OK ' if passed else 'FAIL'}] {label}{f': {detail}' if detail else ''}")
    return passed


def _get_json(path: str) -> object:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # dev/demo cert is locally trusted; we only read public data
    with urllib.request.urlopen(f"{EDGE}{path}", timeout=5, context=ctx) as r:  # noqa: S310
        return json.loads(r.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser(description="DevSync demo preflight")
    parser.add_argument("--stage", type=int, default=1)
    parser.parse_args()
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

    passed = all(checks)
    print(f"demo-preflight: {'ready' if passed else 'NOT ready'} ({sum(checks)}/{len(checks)})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
