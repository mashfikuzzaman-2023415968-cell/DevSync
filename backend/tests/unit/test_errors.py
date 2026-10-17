"""Error envelope and safe handlers (spec §10.1): no traces, request id present, codes mapped."""

from __future__ import annotations

import pytest
from app.core.errors import (
    STATUS_BY_CODE,
    DomainError,
    ErrorCode,
    InvalidStateTransition,
    NotFoundError,
    install_exception_handlers,
)
from app.core.middleware import RequestIdMiddleware, UnhandledExceptionMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

pytestmark = pytest.mark.unit


class Body(BaseModel):
    price_paisa: int


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("SELECT secret FROM users -- internal detail")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError

    @app.get("/state")
    async def state() -> None:
        raise InvalidStateTransition("FORMING", ["view"])

    @app.post("/validate")
    async def validate(body: Body) -> Body:
        return body

    install_exception_handlers(app)
    app.add_middleware(UnhandledExceptionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.fixture
def c() -> TestClient:
    return TestClient(build_app(), raise_server_exceptions=False)


def test_every_code_has_a_status() -> None:
    assert set(STATUS_BY_CODE) == set(ErrorCode)


def test_unknown_exception_is_generic_500_without_details(c: TestClient) -> None:
    r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["request_id"].startswith("req_")
    assert "SELECT" not in r.text
    assert "Traceback" not in r.text
    assert r.headers["cache-control"] == "no-store"


def test_domain_error_maps_to_status(c: TestClient) -> None:
    r = c.get("/missing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_invalid_state_includes_current_state_and_allowed_actions(c: TestClient) -> None:
    r = c.get("/state")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "INVALID_STATE"
    assert err["current_state"] == "FORMING"
    assert err["allowed_actions"] == ["view"]


def test_validation_errors_list_fields_without_echoing_input(c: TestClient) -> None:
    r = c.post("/validate", json={"price_paisa": "<script>alert(1)</script>"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "price_paisa" in err["fields"]
    assert "<script>" not in r.text


def test_unknown_route_uses_envelope(c: TestClient) -> None:
    r = c.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_uses_envelope(c: TestClient) -> None:
    r = c.delete("/missing")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_domain_error_default_message_and_override() -> None:
    assert DomainError().status_code == 400
    e = DomainError("custom", code=ErrorCode.RATE_LIMITED, fields={"a": "b"})
    assert e.status_code == 429
    assert e.message == "custom"
    assert e.fields == {"a": "b"}
