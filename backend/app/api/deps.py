"""Shared FastAPI dependencies: DB session in the caller's RLS context, principal, limits.

Authorization decisions live in `app.core.authz`; these dependencies only
provide the inputs (who is calling, from where) and enforce per-route limits.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_middleware import client_ip
from app.core.authz import Principal, authorize
from app.core.clock import get_clock
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.core.ratelimit import RateLimiter, Rule, hash_key
from app.core.redis import get_redis
from app.core.sessions import SessionData
from app.core.settings_cache import active_settings
from app.db.context import DbContext
from app.db.session import open_session
from app.services.context import Ctx


def app_settings(request: Request) -> Settings:
    """Settings the app was built with."""
    settings: Settings = request.app.state.settings
    return settings


def principal_of(request: Request) -> Principal | None:
    """The signed-in caller, if any (set by SessionMiddleware)."""
    value = getattr(request.state, "principal", None)
    return value if isinstance(value, Principal) else None


def session_of(request: Request) -> tuple[str, SessionData] | None:
    """(token, session data) of the current session, if any."""
    token = getattr(request.state, "session_token", None)
    data = getattr(request.state, "session", None)
    if isinstance(token, str) and isinstance(data, SessionData):
        return token, data
    return None


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """DB session acting for the caller (GUEST when anonymous); rolled back unless committed."""
    p = principal_of(request)
    ctx = DbContext(user_id=p.user_id, role=p.role) if p else DbContext.guest()
    async with open_session(ctx) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def now() -> datetime:
    """Current time from the injectable clock."""
    return get_clock().now()


def redis_client() -> Redis:
    """This event loop's Redis client, for code already running on the loop."""
    return get_redis()


async def loop_redis() -> Redis:
    """The same as a dependency. Async so FastAPI calls it on the loop: a sync dependency runs in
    a worker thread with no loop and would get the loop-less client, which belongs to whichever
    loop first used it (two test clients in one process have two loops)."""
    return get_redis()


def require(action: str) -> Callable[[Request], Principal]:
    """Dependency: authorize `action` (no specific resource) and return the principal."""

    def dependency(request: Request) -> Principal:
        p = principal_of(request)
        authorize(p, action)
        if p is None:  # authorize() already raised; this narrows the type
            raise RuntimeError("unreachable")
        return p

    return dependency


def rate_limit(scope: str, *key_parts: str) -> Callable[[Request, AsyncSession], Awaitable[None]]:
    """Dependency: count this request in `scope` keyed by IP (+ user if signed in)."""

    async def dependency(request: Request, db: DbSession) -> None:
        limits = (await active_settings(db)).ratelimit
        rules = [Rule(r.limit, r.window_seconds) for r in getattr(limits, scope)]
        p = principal_of(request)
        parts = [client_ip(request.scope), *key_parts]
        if p is not None:
            parts.append(str(p.user_id))
        await RateLimiter(get_redis()).hit(scope, hash_key(*parts), rules)

    return dependency


def acting(action: str) -> Callable[[Request, AsyncSession], Ctx]:
    """Dependency: authorize `action` and return the service context (session, clock, caller)."""

    def dependency(request: Request, db: DbSession) -> Ctx:
        p = principal_of(request)
        authorize(p, action)
        if p is None:  # authorize() already raised; this narrows the type
            raise RuntimeError("unreachable")
        return Ctx(db=db, settings=app_settings(request), principal=p, now=now())

    return dependency


def only_query(*allowed: str) -> Callable[[Request], None]:
    """Dependency: refuse query parameters a list endpoint doesn't whitelist with 400, and any
    parameter given twice (§10.1 "unknown params → 400")."""
    names = frozenset(allowed)

    def dependency(request: Request) -> None:
        keys = [k for k, _ in request.query_params.multi_items()]
        unknown = sorted(set(keys) - names)
        repeated = sorted({k for k in keys if keys.count(k) > 1})
        if unknown or repeated:
            fields = dict.fromkeys(unknown, "Unknown parameter")
            fields.update(dict.fromkeys(repeated, "Given more than once"))
            raise DomainError(
                "This list doesn't take that parameter.", code=ErrorCode.BAD_REQUEST, fields=fields
            )

    return dependency
