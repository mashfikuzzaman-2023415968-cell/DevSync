"""Prometheus metrics (spec §15.7). `/metrics` is served on the app but blocked by Nginx.

Labels use the route *template* (e.g. `/api/v1/projects/{id}`), never the raw
path, so ids and user data never become label values.
"""

from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_LATENCY = Histogram(
    "devsync_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route", "status"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
REQUEST_ERRORS = Counter(
    "devsync_http_errors_total", "HTTP responses with status >= 500", ["method", "route"]
)


def _route_template(scope: Scope) -> str:
    """Full route template after matching, else "unmatched".

    FastAPI includes routers without rewriting their paths, so the matched
    route's template (`/health`, `/projects/{id}`) is relative to the include
    prefix. The prefix is recovered by rendering the template with the request's
    path parameters and stripping it from the end of the real path.
    """
    route = scope.get("route")
    template = getattr(route, "path_format", None)
    if not isinstance(template, str):
        return "unmatched"
    params = {k: str(v) for k, v in scope.get("path_params", {}).items()}
    try:
        rendered = template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template
    path = str(scope.get("path", ""))
    prefix = path[: -len(rendered)] if rendered and path.endswith(rendered) else ""
    return prefix + template


class MetricsMiddleware:
    """Records latency and 5xx counts per route template."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

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
            route = _route_template(scope)
            method = scope.get("method", "GET")
            REQUEST_LATENCY.labels(method, route, str(status["code"])).observe(
                time.perf_counter() - start
            )
            if status["code"] >= 500:  # noqa: PLR2004
                REQUEST_ERRORS.labels(method, route).inc()


async def metrics_endpoint(_request: Request) -> Response:
    """Prometheus text exposition."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
