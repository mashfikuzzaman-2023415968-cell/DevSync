"""Client error reports (spec §15.7): sanitize and log, never store or echo.

The browser already truncates and sends only the path, but nothing from the client is trusted:
control characters are removed (no log injection through odd bytes), query strings and fragments
are dropped from the path (they can hold tokens), anything that looks like a secret is masked by
the logging redaction processor, and lengths are capped again.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger
from app.schemas.public import ClientErrorReport

log = get_logger(__name__)

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]")
# Long opaque strings (tokens, hashes, session ids) are masked in messages and stacks.
_SECRETISH = re.compile(r"[A-Za-z0-9_\-]{32,}")
MAX_STACK_LINES = 20


def clean_text(value: str, limit: int) -> str:
    value = _CONTROL.sub("", value)
    value = _SECRETISH.sub("[redacted]", value)
    return value[:limit]


def clean_path(path: str) -> str:
    path = _CONTROL.sub("", path).split("?", 1)[0].split("#", 1)[0]
    path = _SECRETISH.sub("[redacted]", path)
    return path[:300] if path.startswith("/") else "/"


def sanitize(report: ClientErrorReport) -> dict[str, str | None]:
    stack = None
    if report.stack:
        lines = clean_text(report.stack, 4000).splitlines()[:MAX_STACK_LINES]
        stack = "\n".join(lines)
    return {
        "message": clean_text(report.message, 500),
        "stack": stack,
        "path": clean_path(report.path),
        "kind": report.kind,
        "client_request_id": report.request_id,
    }


def record_client_error(report: ClientErrorReport, user_id: str | None) -> None:
    log.warning("client_error", user=user_id, **sanitize(report))
