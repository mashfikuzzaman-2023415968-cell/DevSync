"""Pure-ASGI middleware for the §14.10 chain: request id, body limit, headers, timeout.

These are written as raw ASGI middleware (not `BaseHTTPMiddleware`) so they can
stream, cannot buffer large bodies into memory, and work with SSE later.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import SAFE_MESSAGES, ErrorCode, error_body
from app.core.logging import get_logger, request_id_var
from app.core.metrics import route_template
from app.core.netutil import IPNetwork, ip_in_networks, trusted_client_ip
from app.core.security import derive_key, hmac_sha256

log = get_logger(__name__)
access_log = get_logger("devsync.access")

REQUEST_ID_HEADER = b"x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

MAX_JSON_BODY_BYTES = 256 * 1024
DEFAULT_ROUTE_TIMEOUT_SECONDS = 10.0

# Exact headers for API responses (Nginx adds the same set for static files, §14.3).
API_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"x-frame-options", b"DENY"),
    (
        b"content-security-policy",
        b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    ),
    # The API and the admin area are never indexed; robots.txt does not name them (§14.17).
    (b"x-robots-tag", b"noindex, nofollow"),
]

ASGIHandler = Callable[[Scope, Receive, Send], Awaitable[None]]


async def _send_json_error(send: Send, status: int, code: ErrorCode, message: str) -> None:
    """Emit a complete JSON error response directly from middleware."""
    import json  # noqa: PLC0415 - local import keeps module import cheap

    body = json.dumps(error_body(code, message)).encode()
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


class RequestIdMiddleware:
    """Step 1: accept a well-formed `X-Request-ID` from Nginx or generate one; echo it back."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER, b"").decode("latin-1")
        rid = incoming if _SAFE_REQUEST_ID.match(incoming) else "req_" + secrets.token_hex(12)
        token = request_id_var.set(rid)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER, rid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)


# Multipart upload endpoints (POST only) accept files up to MAX_UPLOAD_MB (spec §14.9); the
# same paths get a larger `client_max_body_size` in Nginx.
UPLOAD_PATHS = re.compile(
    r"^/api/v1/(?:me/portfolio/[^/]+/images|me/certificates|me/external-reviews)$"
)
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class BodySizeLimitMiddleware:
    """Step 3: reject bodies over the limit (by Content-Length and while streaming) → 413."""

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = MAX_JSON_BODY_BYTES,
        upload_max_bytes: int | None = None,
    ) -> None:
        self.app = app
        self.default_max = max_bytes
        self.upload_max = upload_max_bytes or max_bytes

    def limit_for(self, scope: Scope) -> int:
        """The body limit for this request: larger only for POSTs to an upload endpoint."""
        if scope.get("method") == "POST" and UPLOAD_PATHS.match(scope.get("path", "")):
            return self.upload_max
        return self.default_max

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_bytes = self.limit_for(scope)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > max_bytes
            except ValueError:
                too_big = True
            if too_big:
                await _send_json_error(
                    send, 413, ErrorCode.PAYLOAD_TOO_LARGE, "The request is too large."
                )
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    raise _BodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLargeError:
            await _send_json_error(
                send, 413, ErrorCode.PAYLOAD_TOO_LARGE, "The request is too large."
            )


class _BodyTooLargeError(Exception):
    """Internal signal raised while streaming an oversized body."""


class SecurityHeadersMiddleware:
    """Step 4: add the API security headers and `Cache-Control: no-store` by default."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() not in {b"server"}
                ]
                present = {k.lower() for k, _ in headers}
                headers.extend(h for h in API_SECURITY_HEADERS if h[0] not in present)
                if b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class UnhandledExceptionMiddleware:
    """Innermost safety net: unknown exceptions become a generic 500 *inside* the chain.

    Starlette's own error middleware sits outside user middleware, so its 500
    would lack the request id and security headers. Catching here keeps every
    response uniform; the full trace is logged server-side only.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            log.error("unhandled_exception", exc_info=exc)
            if started:
                raise
            await _send_json_error(
                send, 500, ErrorCode.INTERNAL_ERROR, SAFE_MESSAGES[ErrorCode.INTERNAL_ERROR]
            )


class TimeoutMiddleware:
    """Step 8: cancel a request that exceeds the route timeout → 504 (only if nothing was sent)."""

    def __init__(self, app: ASGIApp, seconds: float = DEFAULT_ROUTE_TIMEOUT_SECONDS) -> None:
        self.app = app
        self.seconds = seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "").endswith("/stream"):
            await self.app(scope, receive, send)
            return
        started: MutableMapping[str, Any] = {"value": False}

        async def tracking_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                started["value"] = True
            await send(message)

        try:
            await asyncio.wait_for(self.app(scope, receive, tracking_send), timeout=self.seconds)
        except TimeoutError:
            if not started["value"]:
                await _send_json_error(
                    send, 504, ErrorCode.TIMEOUT, "The request took too long. Please try again."
                )


ADMIN_API_PREFIX = "/api/v1/admin"
# Path segments a canonical API path may contain (RFC 3986 pchar; encoded "/", "\", "." and
# NUL are refused separately).
_SAFE_SEGMENT = re.compile(rb"^[A-Za-z0-9\-_~!$&'()*+,;=:@.%]+$")
_UNSAFE_ESCAPE = re.compile(rb"%(?:2f|5c|2e|00)", re.IGNORECASE)
_SAFE_QUERY = re.compile(rb"^[A-Za-z0-9\-._~!$&'()*+,;=:@/?%]*$")


class AccessLogMiddleware:
    """One structured line per request (spec §14.12, §15.7), just inside the request-id step.

    Logged: method, route *template* (never the raw path, which may carry tokens), status,
    duration in ms, the request id and a keyed hash of the user id. Never logged: query
    strings, headers, cookies or bodies.
    """

    def __init__(self, app: ASGIApp, secret_key: str) -> None:
        self.app = app
        self.user_key = derive_key(secret_key, "log-user-id")

    def user_hash(self, user_id: object) -> str:
        """Stable, non-reversible id for correlating one user's requests (16 hex chars)."""
        return hmac_sha256(self.user_key, str(user_id)).hex()[:16]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = {"code": 500}

        async def recording_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        finally:
            principal = scope.get("state", {}).get("principal")
            access_log.info(
                "http_request",
                method=str(scope.get("method", "")),
                route=route_template(scope),
                status=status["code"],
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
                user_hash=self.user_hash(principal.user_id) if principal is not None else None,
            )


def is_admin_api_path(path: str) -> bool:
    """True for `/api/v1/admin` and everything below it."""
    return path == ADMIN_API_PREFIX or path.startswith(ADMIN_API_PREFIX + "/")


class AdminNetworkMiddleware:
    """`ADMIN_ALLOWED_CIDRS` (spec §14.17): admin API requests from other networks get the
    same 404 a non-admin gets, before any session or database work. Empty list = no limit.

    The client address comes from :func:`trusted_client_ip`, which believes
    `X-Forwarded-For` only from `TRUSTED_PROXY_IPS`; an unknown address is refused.
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed: tuple[IPNetwork, ...],
        trusted_proxies: tuple[IPNetwork, ...],
    ) -> None:
        self.app = app
        self.allowed = allowed
        self.trusted_proxies = trusted_proxies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and self.allowed
            and is_admin_api_path(str(scope.get("path", "")))
            and not ip_in_networks(trusted_client_ip(scope, self.trusted_proxies), self.allowed)
        ):
            log.warning("admin_network_refused")
            await _send_json_error(
                send, 404, ErrorCode.NOT_FOUND, SAFE_MESSAGES[ErrorCode.NOT_FOUND]
            )
            return
        await self.app(scope, receive, send)


def canonical_api_location(scope: Scope) -> bytes | None:
    """`Location` for an API path with trailing slashes, or None to leave the request alone.

    Only a same-origin *relative* path under `/api/` is produced: no `//`, no backslash, no
    dot segments, no encoded slash/backslash/dot/NUL, so it can never point elsewhere.
    """
    path = str(scope.get("path", ""))
    raw: bytes = scope.get("raw_path") or path.encode("utf-8")
    if not (path.startswith("/api/") and raw.startswith(b"/api/") and raw.endswith(b"/")):
        return None
    canonical = raw.rstrip(b"/")
    segments = canonical.split(b"/")[1:]
    if (
        not canonical.startswith(b"/api/")
        or _UNSAFE_ESCAPE.search(canonical)
        or any(s in {b"", b".", b".."} or not _SAFE_SEGMENT.match(s) for s in segments)
    ):
        return None
    query: bytes = scope.get("query_string", b"")
    if query and not _SAFE_QUERY.match(query):
        return None
    return canonical + (b"?" + query if query else b"")


class TrailingSlashRedirectMiddleware:
    """`/api/v1/me/` → 308 `/api/v1/me` (spec §10.1, §15.5): method, body and query kept.

    Anything that is not a clean API path falls through to the router (404).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        location = canonical_api_location(scope) if scope["type"] == "http" else None
        if location is None:
            await self.app(scope, receive, send)
            return
        await send(
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [
                    (b"location", location),
                    (b"content-length", b"0"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})
