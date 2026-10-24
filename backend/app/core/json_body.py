"""Request-body rules for the JSON API (spec §10.1, §14.7).

- A request body on `/api/v1` must be `application/json` (UTF-8): anything else → 415
  `UNSUPPORTED_MEDIA_TYPE`. Multipart is accepted only by POSTs to the upload endpoints
  (`UPLOAD_PATHS`), which FastAPI parses itself.
- JSON nesting deeper than `MAX_JSON_DEPTH` (20) → 422, checked by a linear scan *before*
  parsing, so a deeply nested body can never reach the recursive parser.
- `NaN`, `Infinity` and `-Infinity` (which Python's `json` accepts by default) → 422.

Bodies are already capped at 256 KB by `BodySizeLimitMiddleware` (outer), so buffering one
here is bounded. Empty bodies pass through untouched (FastAPI reports a missing required body as
422 itself), as does malformed JSON (FastAPI's own 422 `json_invalid`).
"""

from __future__ import annotations

import json

from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ErrorCode, error_body
from app.core.middleware import UPLOAD_PATHS

API_PREFIX = "/api/v1/"
MAX_JSON_DEPTH = 20
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_OPEN = frozenset(b"[{")
_CLOSE = frozenset(b"]}")
_QUOTE = ord('"')
_BACKSLASH = ord("\\")


class _NonFiniteNumberError(ValueError):
    """`NaN` / `Infinity` in a JSON body."""


def media_type(content_type: str) -> tuple[str, dict[str, str]]:
    """`"Application/JSON; charset=UTF-8"` → `("application/json", {"charset": "utf-8"})`."""
    main, *raw_params = content_type.split(";")
    params: dict[str, str] = {}
    for raw in raw_params:
        key, sep, value = raw.partition("=")
        if sep:
            params[key.strip().lower()] = value.strip().strip('"').lower()
    return main.strip().lower(), params


def is_json_content_type(content_type: str | None) -> bool:
    """Only `application/json`, optionally with `charset=utf-8` (the API is UTF-8 only)."""
    if not content_type:
        return False
    main, params = media_type(content_type)
    return main == "application/json" and params.get("charset", "utf-8") in {"utf-8", "utf8"}


def nesting_depth_exceeds(body: bytes, limit: int = MAX_JSON_DEPTH) -> bool:
    """True if arrays/objects nest deeper than `limit` (strings are skipped; linear time)."""
    depth = 0
    in_string = False
    escaped = False
    for byte in body:
        if in_string:
            if escaped:
                escaped = False
            elif byte == _BACKSLASH:
                escaped = True
            elif byte == _QUOTE:
                in_string = False
        elif byte == _QUOTE:
            in_string = True
        elif byte in _OPEN:
            depth += 1
            if depth > limit:
                return True
        elif byte in _CLOSE:
            depth -= 1
    return False


def _refuse_constant(name: str) -> object:
    raise _NonFiniteNumberError(name)


def has_non_finite_number(body: bytes) -> bool:
    """True if the JSON contains `NaN`/`Infinity`; malformed JSON returns False (FastAPI's)."""
    if b"NaN" not in body and b"Infinity" not in body:
        return False  # neither constant can appear, so skip the parse
    try:
        json.loads(body, parse_constant=_refuse_constant)
    except _NonFiniteNumberError:
        return True
    except ValueError:  # malformed JSON or bad UTF-8: FastAPI answers with its own 422
        return False
    return False


def _route_serves(scope: Scope) -> bool:
    """True if some route takes this method at this path. Otherwise the router answers 404/405
    without reading the body, so the body rules must not turn those into 415/422."""
    router = getattr(scope.get("app"), "router", None)
    if router is None:
        return True  # can't tell: enforce the rules (fail closed)
    for route in getattr(router, "routes", ()):
        match, _ = route.matches(scope)
        if match is Match.FULL:
            return True
    return False


async def _send_error(send: Send, code: ErrorCode, message: str, fields: dict[str, str]) -> None:
    status = 415 if code is ErrorCode.UNSUPPORTED_MEDIA_TYPE else 422
    body = json.dumps(error_body(code, message, fields or None)).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class JsonBodyMiddleware:
    """Enforce the JSON body rules above, then replay the buffered body to the app."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") not in _BODY_METHODS
            or not str(scope.get("path", "")).startswith(API_PREFIX)
            or not _route_serves(scope)
        ):
            await self.app(scope, receive, send)
            return
        content_type = None
        for key, value in scope.get("headers", []):
            if key.lower() == b"content-type":
                content_type = value.decode("latin-1")
                break
        upload = scope.get("method") == "POST" and bool(UPLOAD_PATHS.match(scope.get("path", "")))
        if upload and content_type and media_type(content_type)[0] == "multipart/form-data":
            await self.app(scope, receive, send)  # FastAPI parses the form; size capped outside
            return

        chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            more = bool(message.get("more_body", False))
        body = b"".join(chunks)

        if body:
            if upload or not is_json_content_type(content_type):
                await _send_error(
                    send,
                    ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                    "Send the request body as JSON (Content-Type: application/json).",
                    {},
                )
                return
            if nesting_depth_exceeds(body):
                await _send_error(
                    send,
                    ErrorCode.VALIDATION_ERROR,
                    "Some fields need attention.",
                    {"body": f"Nesting is limited to {MAX_JSON_DEPTH} levels."},
                )
                return
            if has_non_finite_number(body):
                await _send_error(
                    send,
                    ErrorCode.VALIDATION_ERROR,
                    "Some fields need attention.",
                    {"body": "NaN and Infinity are not allowed."},
                )
                return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
