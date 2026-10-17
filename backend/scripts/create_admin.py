"""Create an administrator (spec §2.1: admins are created only by admins / this CLI).

Usage (inside the worker container, which has the worker DB role):
    make create-admin
Prompts for email, name and password; prints the TOTP provisioning URI and the
recovery codes **once**. Nothing secret is logged.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

import pyotp

from app.core.config import get_settings
from app.core.security import password_problems
from app.services.testing.seed import create_user


def main() -> int:
    """Interactive admin creation."""
    settings = get_settings()
    email = input("Admin email: ").strip()
    name = input("Display name: ").strip() or "Administrator"
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.")
        return 1
    problems = password_problems(password, [email, name])
    if problems:
        print("Password rejected: " + " ".join(problems))
        return 1
    result = asyncio.run(
        create_user(
            settings, role="ADMIN", email=email, phone=None, password=password,
            display_name=name, verified=True, with_totp=True, actor="cli",
        )
    )  # fmt: skip
    uri = pyotp.TOTP(result["totp_secret"]).provisioning_uri(name=email, issuer_name="DevSync")
    print("\nAdmin created. Add this to your authenticator app (shown once):")
    print(f"  {uri}")
    print("\nRecovery codes (store them offline; each works once):")
    for code in result["recovery_codes"]:
        print(f"  {code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
