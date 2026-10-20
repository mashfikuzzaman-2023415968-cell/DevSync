"""FastAPI application factory and middleware chain (spec §14.10).

Middleware order (outermost first) — Starlette runs the *last added* middleware
first, so they are added in reverse below:

1. Request id  2. Trusted host  3. Body size limit  4. Security headers
5. Session load  6. CSRF  7. Rate limit  8. Timeout guard  9. Router  10. Exception handlers

The test-only router is mounted only when DEVSYNC_ENV=test (spec §16.2, §14.18).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Route

from app.api.v1 import (
    admin,
    auth,
    bids,
    captcha,
    files,
    health,
    marketplace,
    me,
    profiles,
    projects,
    public,
    skill_tests,
)
from app.core.auth_middleware import CsrfMiddleware, GlobalRateLimitMiddleware, SessionMiddleware
from app.core.config import Environment, Settings, get_settings, validate_production
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware, metrics_endpoint
from app.core.middleware import (
    MULTIPART_OVERHEAD_BYTES,
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
    UnhandledExceptionMiddleware,
)
from app.core.redis import close_redis
from app.db.session import dispose_engines

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Graceful shutdown: close DB pools and the Redis client (spec §15.6)."""
    yield
    await dispose_engines()
    await close_redis()


# Responses the middleware chain can produce on any matching operation (§14.10), declared
# centrally so the contract (and schemathesis) knows every status a route may return.
_GLOBAL_RESPONSES = {
    "429": ("RATE_LIMITED", "Too many requests. Please wait and try again."),
    "413": ("PAYLOAD_TOO_LARGE", "The request is too large."),
}
_UNSAFE_RESPONSES = {"403": ("CSRF_FAILED", "Your session form expired. Refresh and try again.")}
_NO_GLOBAL_LIMIT = ("/api/v1/health",)


def _with_global_responses(app: FastAPI) -> Callable[[], dict[str, Any]]:
    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
        for path, item in schema.get("paths", {}).items():
            for method, op in item.items():
                extra = {} if path.startswith(_NO_GLOBAL_LIMIT) else dict(_GLOBAL_RESPONSES)
                if method in {"post", "put", "patch", "delete"}:
                    extra.update(_UNSAFE_RESPONSES)
                for status, (code, message) in extra.items():
                    op.setdefault("responses", {}).setdefault(status, {
                        "description": message,
                        "content": {"application/json": {
                            "schema": error_ref,
                            "example": {"error": {"code": code, "message": message,
                                                  "request_id": "req_123"}},
                        }},
                    })  # fmt: skip
        app.openapi_schema = schema
        return schema

    return openapi


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app. Fails closed on insecure production settings."""
    settings = settings or get_settings()
    validate_production(settings)
    configure_logging(settings.LOG_LEVEL)

    docs = settings.docs_enabled
    app = FastAPI(
        title="DevSync API",
        version="0.0.0",
        debug=False,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        lifespan=lifespan,
    )

    app.state.settings = settings
    for module in (
        health,
        captcha,
        public,
        auth,
        me,
        admin,
        profiles,
        files,
        skill_tests,
        projects,
        marketplace,
        bids,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    if settings.DEVSYNC_ENV is Environment.TEST:
        from app.api.v1 import test_seed  # noqa: PLC0415 - imported only in the test environment

        app.include_router(test_seed.router, prefix=API_PREFIX)
    # Internal only: Nginx denies /metrics from outside (spec §15.7).
    app.router.routes.append(Route("/metrics", metrics_endpoint, include_in_schema=False))

    install_exception_handlers(app)
    app.openapi = _with_global_responses(app)  # type: ignore[method-assign]

    # Added innermost → outermost.
    app.add_middleware(UnhandledExceptionMiddleware)  # 10 (safety net for unknown errors)
    app.add_middleware(TimeoutMiddleware)  # 8
    # The test-only router (DEVSYNC_ENV=test) is outside the per-IP limit so E2E helpers keep
    # working; it does not exist in any other environment.
    test_prefix = (f"{API_PREFIX}/__test__",) if settings.DEVSYNC_ENV is Environment.TEST else ()
    app.add_middleware(GlobalRateLimitMiddleware, extra_exempt=test_prefix)  # 7
    app.add_middleware(CsrfMiddleware, settings=settings)  # 6
    app.add_middleware(SessionMiddleware, settings=settings)  # 5
    app.add_middleware(SecurityHeadersMiddleware)  # 4
    app.add_middleware(
        BodySizeLimitMiddleware,
        upload_max_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024 + MULTIPART_OVERHEAD_BYTES,
    )  # 3
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)  # 2
    app.add_middleware(RequestIdMiddleware)  # 1
    app.add_middleware(MetricsMiddleware)  # observes the whole chain
    return app


def app_factory() -> FastAPI:
    """Entry point for Gunicorn/Uvicorn (`app.main:app_factory` with `--factory`)."""
    return create_app()
