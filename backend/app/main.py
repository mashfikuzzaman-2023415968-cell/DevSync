"""FastAPI application factory and middleware chain (spec §14.10).

Middleware order (outermost first) — Starlette runs the *last added* middleware
first, so they are added in reverse below:

1. Request id  2. Trusted host  3. Body size limit  4. Security headers
5. Session load  6. CSRF  7. Rate limit   (5–7 arrive in Phase 1)
8. Timeout guard  9. Router  10. Exception handlers
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Route

from app.api.v1 import health
from app.core.config import Settings, get_settings, validate_production
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware, metrics_endpoint
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
    UnhandledExceptionMiddleware,
)

API_PREFIX = "/api/v1"


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
    )

    app.include_router(health.router, prefix=API_PREFIX)
    # Internal only: Nginx denies /metrics from outside (spec §15.7).
    app.router.routes.append(Route("/metrics", metrics_endpoint, include_in_schema=False))

    install_exception_handlers(app)

    # Added innermost → outermost.
    app.add_middleware(UnhandledExceptionMiddleware)  # 10 (safety net for unknown errors)
    app.add_middleware(TimeoutMiddleware)  # 8
    # 5–7 (session, CSRF, rate limit) are inserted here in Phase 1.
    app.add_middleware(SecurityHeadersMiddleware)  # 4
    app.add_middleware(BodySizeLimitMiddleware)  # 3
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)  # 2
    app.add_middleware(RequestIdMiddleware)  # 1
    app.add_middleware(MetricsMiddleware)  # observes the whole chain
    return app


def app_factory() -> FastAPI:
    """Entry point for Gunicorn/Uvicorn (`app.main:app_factory` with `--factory`)."""
    return create_app()
