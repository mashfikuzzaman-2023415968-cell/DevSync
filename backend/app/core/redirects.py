"""Open-redirect prevention for `return_to` and notification links (spec §14.6).

A target is accepted only if it is a relative app path: it starts with a single
`/`, contains no `//` at the start, no backslash, no scheme, no control or
whitespace characters, is at most 512 characters, and matches a known frontend
route pattern. Anything else falls back to the role's home page.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

MAX_LENGTH = 512

ROLE_HOME: dict[str, str] = {
    "CLIENT": "/client",
    "DEVELOPER": "/dev",
    "ADMIN": "/admin",
    "PENDING": "/verify",
}

# Frontend route patterns users may be sent back to (extended as phases add screens).
_SEGMENT = r"[A-Za-z0-9._~-]+"
ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"/",
        r"/projects",
        rf"/p/{_SEGMENT}",
        rf"/d/{_SEGMENT}",
        r"/verify",
        r"/settings",
        r"/notifications",
        rf"/client(/{_SEGMENT})*",
        rf"/dev(/{_SEGMENT})*",
        rf"/admin(/{_SEGMENT})*",
        rf"/w/{_SEGMENT}(/{_SEGMENT})*",
    )
)
_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f\\]")


def is_safe_path(target: str | None) -> bool:
    """True if `target` is a same-site app path matching a known route."""
    if not target or len(target) > MAX_LENGTH:
        return False
    decoded = unquote(target)
    for candidate in (target, decoded):
        if not candidate.startswith("/") or candidate.startswith("//"):
            return False
        if _FORBIDDEN_CHARS.search(candidate):
            return False
    # A single leading "/" (checked above) means urlsplit finds no scheme or host.
    path = urlsplit(target).path
    return any(p.fullmatch(path) for p in ROUTE_PATTERNS)


def role_home(role: str | None, status: str | None = None) -> str:
    """Landing page for a role (PENDING users go to verification)."""
    if status == "PENDING":
        return ROLE_HOME["PENDING"]
    return ROLE_HOME.get(role or "", "/")


def safe_redirect(target: str | None, role: str | None, status: str | None = None) -> str:
    """`target` if safe, else the role home (PENDING users always go to /verify)."""
    if status == "PENDING":
        return ROLE_HOME["PENDING"]
    return target if target is not None and is_safe_path(target) else role_home(role, status)
