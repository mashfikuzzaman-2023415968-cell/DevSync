"""Generate `.env` with strong random secrets (`make env`, spec §16.6).

Never overwrites an existing `.env` unless `--force` is given, so a teammate's
secrets are not lost. Values are hex/base64 so they are safe inside URLs.
Standard library only (runs on the host).
"""

from __future__ import annotations

import base64
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / ".env"


def render() -> str:
    """Return `.env` content: non-secret values from `.env.example`, secrets generated."""
    generated = {
        "SECRET_KEY": base64.b64encode(secrets.token_bytes(64)).decode(),
        "CAPTCHA_HMAC_KEY": secrets.token_hex(32),
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "DEVSYNC_MIGRATOR_PASSWORD": secrets.token_hex(24),
        "DEVSYNC_APP_PASSWORD": secrets.token_hex(24),
        "DEVSYNC_WORKER_PASSWORD": secrets.token_hex(24),
        "DEVSYNC_READONLY_PASSWORD": secrets.token_hex(24),
        "REDIS_PASSWORD": secrets.token_hex(24),
    }
    lines = []
    for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key = raw.split("=", 1)[0].strip()
        if key in generated and not raw.lstrip().startswith("#"):
            lines.append(f"{key}={generated[key]}")
        else:
            lines.append(raw)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    """CLI entry point."""
    if TARGET.exists() and "--force" not in argv:
        print(".env already exists; keeping it (use `make env FORCE=1` to regenerate)")
        return 0
    TARGET.write_text(render(), encoding="utf-8")
    TARGET.chmod(0o600)
    print("wrote .env with fresh secrets (permissions 600; never commit it)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
