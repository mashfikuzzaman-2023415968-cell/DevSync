"""Pure-ASGI middleware for the §14.10 chain: request id, body limit, headers, timeout.

These are written as raw ASGI middleware (not `BaseHTTPMiddleware`) so they can
stream, cannot buffer large bodies into memory, and work with SSE later.
"""

from __future__ import annotations

import asyncio
import re
import secrets
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import SAFE_MESSAGES, ErrorCode, error_body
from app.core.logging import get_logger, request_id_var

log = get_logger(__name__)

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
