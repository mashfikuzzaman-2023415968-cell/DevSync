"""Middleware steps 5–7 of §14.10: session load, CSRF, global rate limit.

- **Session (5):** reads `__Host-ds_session`, loads the server-side session, rotates the
  token when it is 15 minutes old (sending the new cookie), and places a `Principal`
  in `request.state.principal`. Suspended/deleted accounts are treated as signed out.
- **CSRF (6):** every unsafe `/api/` request needs a matching, valid `X-CSRF-Token`
  and an Origin/Referer equal to `PUBLIC_ORIGIN`.
- **Rate limit (7):** global per-user (120/min) or per-IP (60/min) limit; route-level
  scopes (login, registration…) are applied by dependencies in the routers.
"""

from __future__ import annotations

import json
from http.cookies import SimpleCookie
from typing import Any

from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import csrf
from app.core.authz import Principal
from app.core.clock import get_clock
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode, error_body
from app.core.logging import get_logger
from app.core.ratelimit import RateLimited, RateLimiter, RateLimitUnavailable, Rule
from app.core.redis import get_redis
from app.core.security import derive_key
from app.core.sessions import SESSION_COOKIE, SessionPolicy, SessionStore
from app.core.settings_cache import active_settings
from app.db.context import DbContext, set_context
from app.db.session import open_session

log = get_logger(__name__)
API_PREFIX = "/api/"
EXEMPT_FROM_GLOBAL_LIMIT = ("/api/v1/health",)
INACTIVE_STATUSES = frozenset({"SUSPENDED", "DELETED"})
MAX_TOKEN_LENGTH = 128  # 32 random bytes are 43 characters; anything far longer is junk


def session_cookie(token: str, max_age: int) -> str:
    """`Set-Cookie` value for the session (spec §14.4 flags; `__Host-` = no Domain, Path=/)."""
    return f"{SESSION_COOKIE}={token}; Path=/; Max-Age={max_age}; Secure; HttpOnly; SameSite=Lax"


def clear_session_cookie() -> str:
    """`Set-Cookie` value that deletes the session cookie."""
    return f"{SESSION_COOKIE}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax"


def csrf_cookie(token: str) -> str:
    """Readable CSRF cookie (SameSite=Strict, §14.6)."""
    return f"{csrf.CSRF_COOKIE}={token}; Path=/; Secure; SameSite=Strict"


def _cookies(scope: Scope) -> dict[str, str]:
    jar: SimpleCookie = SimpleCookie()
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            try:
                jar.load(value.decode("latin-1"))
            except Exception:  # malformed cookie header: ignore it entirely
                return {}
    return {k: m.value for k, m in jar.items()}


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


def client_ip(scope: Scope) -> str:
    """Client address as seen after the trusted proxy (Gunicorn/Uvicorn forwarded IPs)."""
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


async def send_error(
    send: Send, error: DomainError, extra_headers: dict[str, str] | None = None
) -> None:
    """Emit a domain error as a JSON response from middleware."""
    body = json.dumps(error_body(error.code, error.message, error.fields, error.extra)).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"),
    ]
    for k, v in (extra_headers or {}).items():
        headers.append((k.lower().encode(), v.encode()))
    await send({"type": "http.response.start", "status": error.status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def _with_cookies(send: Send, cookies: list[str]) -> Send:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start" and cookies:
            headers = list(message.get("headers", []))
            headers.extend((b"set-cookie", c.encode("latin-1")) for c in cookies)
            message["headers"] = headers
        await send(message)

    return wrapped


class SessionMiddleware:
    """Step 5: load the server-side session and expose `request.state.principal`."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.policy = SessionPolicy(settings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(API_PREFIX):
            await self.app(scope, receive, send)
            return
        state: dict[str, Any] = scope.setdefault("state", {})
        state["principal"] = None
        token = _cookies(scope).get(SESSION_COOKIE)
        cookies: list[str] = []
        if token and len(token) <= MAX_TOKEN_LENGTH:
            await self._load(token, state, cookies)
        await self.app(scope, receive, _with_cookies(send, cookies))

    async def _load(self, token: str, state: dict[str, Any], cookies: list[str]) -> None:
        now = get_clock().now()
        store = SessionStore(get_redis(), self.policy)
        async with open_session(DbContext.guest()) as db:
            data = await store.load(db, token, now)
            if data is None or data.status in INACTIVE_STATUSES:
                cookies.append(clear_session_cookie())
                return
            await set_context(db, DbContext(user_id=data.user_id, role=data.role))
            if self.policy.needs_rotation(data, now):
                token, data = await store.rotate(db, token, data, now)
                max_age = int((data.expires_at - now).total_seconds())
                cookies.append(session_cookie(token, max_age))
                cookies.append(csrf_cookie(csrf.issue_token(data.csrf_secret)))
            else:
                data = await store.touch(db, token, data, now)
            await db.commit()
        state["session_token"] = token
        state["session"] = data
        state["principal"] = Principal(
            user_id=data.user_id,
            role=data.role,
            status=data.status,
            session_id=data.session_id,
            totp_verified=data.totp_verified,
            step_up_until=data.step_up_until,
        )


def _is_existing_operation(scope: Scope) -> bool:
    """True if some route fully matches this path *and* method."""
    app = scope.get("app")
    router = getattr(app, "router", None)
    for route in getattr(router, "routes", []):
        match, _ = route.matches(scope)
        if match is Match.FULL:
            return True
    return False


class CsrfMiddleware:
    """Step 6: double-submit token + Origin check on unsafe API requests."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.public_origin = settings.PUBLIC_ORIGIN
        self.anon_key = derive_key(settings.SECRET_KEY, "csrf-anonymous")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method", "GET") not in csrf.UNSAFE_METHODS
            or not scope.get("path", "").startswith(API_PREFIX)
        ):
            await self.app(scope, receive, send)
            return
        if not _is_existing_operation(scope):
            # Unknown path or method: nothing can change state; the router answers 404/405.
            await self.app(scope, receive, send)
            return
        session = scope.get("state", {}).get("session")
        key = session.csrf_secret if session is not None else self.anon_key
        ok = csrf.request_is_valid(
            cookie_token=_cookies(scope).get(csrf.CSRF_COOKIE),
            header_token=_header(scope, b"x-csrf-token"),
            key=key,
            origin=_header(scope, b"origin"),
            referer=_header(scope, b"referer"),
            public_origin=self.public_origin,
        )
        if not ok:
            log.warning("csrf_rejected", path=scope.get("path"))
            await send_error(send, DomainError(code=ErrorCode.CSRF_FAILED))
            return
        await self.app(scope, receive, send)


class GlobalRateLimitMiddleware:
    """Step 7: 120 requests/min per user, 60/min per anonymous IP (§14.8)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not path.startswith(API_PREFIX)
            or path.startswith(EXEMPT_FROM_GLOBAL_LIMIT)
        ):
            await self.app(scope, receive, send)
            return
        principal = scope.get("state", {}).get("principal")
        async with open_session(DbContext.guest()) as db:
            limits = (await active_settings(db)).ratelimit
        if principal is not None:
            scope_name, key = "api_authenticated", str(principal.user_id)
            rules = limits.api_authenticated
        else:
            scope_name, key = "api_anonymous", client_ip(scope)
            rules = limits.api_anonymous
        try:
            await RateLimiter(get_redis()).hit(
                scope_name, key, [Rule(r.limit, r.window_seconds) for r in rules]
            )
        except RateLimited as exc:
            await send_error(send, exc, {"Retry-After": str(exc.retry_after)})
            return
        except RateLimitUnavailable as exc:
            await send_error(send, exc)
            return
        await self.app(scope, receive, send)
