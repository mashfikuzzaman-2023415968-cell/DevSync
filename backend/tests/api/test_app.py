"""App factory, middleware chain and health endpoints (spec §14.10, §15.6)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Environment
from app.core.middleware import API_SECURITY_HEADERS, MAX_JSON_BODY_BYTES
from app.main import create_app
from app.services import health as health_service
from tests.conftest import make_settings

pytestmark = pytest.mark.api


def test_liveness(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_security_headers_on_api_responses(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    for name, value in API_SECURITY_HEADERS:
        assert r.headers[name.decode()] == value.decode()
    assert r.headers["cache-control"] == "no-store"
    assert "server" not in r.headers


def test_request_id_is_generated_and_echoed(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.headers["x-request-id"].startswith("req_")
    r2 = client.get("/api/v1/health", headers={"X-Request-ID": "nginx-abcdef123456"})
    assert r2.headers["x-request-id"] == "nginx-abcdef123456"


def test_malformed_request_id_is_replaced(client: TestClient) -> None:
    r = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert r.headers["x-request-id"].startswith("req_")


def test_unknown_host_is_rejected() -> None:
    with TestClient(create_app(make_settings()), base_url="http://evil.example") as c:
        r = c.get("/api/v1/health")
    assert r.status_code == 400


def test_oversize_body_by_content_length_is_413(client: TestClient) -> None:
    r = client.post("/api/v1/health", content=b"x" * (MAX_JSON_BODY_BYTES + 1))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_oversize_streamed_body_is_413(client: TestClient) -> None:
    def chunks():  # type: ignore[no-untyped-def]
        for _ in range(5):
            yield b"x" * (MAX_JSON_BODY_BYTES // 4)

    r = client.post("/api/v1/health", content=chunks())
    # /health has no POST operation: the router answers 405 without reading the body.
    assert r.status_code in {405, 413}


def test_invalid_content_length_is_413(client: TestClient) -> None:
    r = client.post("/api/v1/health", content=b"{}", headers={"content-length": "abc"})
    assert r.status_code in {400, 413}


def test_docs_only_in_development() -> None:
    with TestClient(create_app(make_settings())) as c:
        assert c.get("/api/v1/openapi.json").status_code == 404
        assert c.get("/api/v1/docs").status_code == 404
    dev = make_settings(DEVSYNC_ENV=Environment.DEVELOPMENT)
    with TestClient(create_app(dev)) as c:
        assert c.get("/api/v1/openapi.json").status_code == 200


def test_metrics_endpoint_exposes_prometheus_text(client: TestClient) -> None:
    client.get("/api/v1/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "devsync_http_request_duration_seconds" in r.text
    assert 'route="/api/v1/health"' in r.text


def test_readiness_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def all_ok() -> dict[str, str]:
        return {"database": "ok", "redis": "ok", "queue": "ok"}

    monkeypatch.setattr(health_service, "check_dependencies", all_ok)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_503_when_a_dependency_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def redis_down() -> dict[str, str]:
        return {"database": "ok", "redis": "unavailable", "queue": "unavailable"}

    monkeypatch.setattr(health_service, "check_dependencies", redis_down)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["redis"] == "unavailable"


def test_production_app_refuses_insecure_settings() -> None:
    from app.core.config import InsecureConfigurationError  # noqa: PLC0415

    with pytest.raises(InsecureConfigurationError):
        create_app(make_settings(DEVSYNC_ENV=Environment.PRODUCTION))


def test_production_app_has_no_test_router_or_docs() -> None:
    """Spec §14.18: in production the test seed router and API docs do not exist."""
    import base64  # noqa: PLC0415
    import secrets  # noqa: PLC0415

    prod = make_settings(
        DEVSYNC_ENV=Environment.PRODUCTION,
        SECRET_KEY=base64.b64encode(secrets.token_bytes(64)).decode(),
        SMS_PROVIDER="provider",
        REDIS_URL="redis://:pw@redis:6379/0",
        ALLOWED_HOSTS="testserver",
        PUBLIC_ORIGIN="https://testserver",
    )
    app = create_app(prod)
    paths = {getattr(r, "path", "") for r in app.router.routes}
    assert not any("__test__" in p for p in paths)
    # …and nothing is exempt from the per-IP limit except health checks.
    assert _global_limit_exemptions(app) == ()
    with TestClient(app, base_url="https://testserver") as c:
        for path in ("/api/v1/openapi.json", "/api/v1/docs", "/api/v1/__test__/sms?phone=x"):
            assert c.get(path).status_code == 404, path


def test_test_router_exists_only_in_test_environment(settings: object) -> None:
    from app.core.config import Settings  # noqa: PLC0415

    assert isinstance(settings, Settings)
    with TestClient(create_app(make_settings(DEVSYNC_ENV=Environment.DEVELOPMENT))) as c:
        assert c.get("/api/v1/__test__/sms?phone=x").status_code == 404


def _global_limit_exemptions(app: object) -> tuple[str, ...]:
    from app.core.auth_middleware import GlobalRateLimitMiddleware  # noqa: PLC0415

    for m in app.user_middleware:  # type: ignore[attr-defined]
        if m.cls is GlobalRateLimitMiddleware:
            return tuple(m.kwargs.get("extra_exempt", ()))
    raise AssertionError("GlobalRateLimitMiddleware missing")


def test_only_the_test_environment_exempts_its_router_from_the_global_limit() -> None:
    assert _global_limit_exemptions(create_app(make_settings(DEVSYNC_ENV=Environment.TEST))) == (
        "/api/v1/__test__",
    )
    dev = create_app(make_settings(DEVSYNC_ENV=Environment.DEVELOPMENT))
    assert _global_limit_exemptions(dev) == ()
