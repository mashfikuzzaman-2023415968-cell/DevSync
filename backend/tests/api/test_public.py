"""Homepage stats and client error reports (spec §13.11 #3, §15.7)."""

from __future__ import annotations

import json
import os

import pytest
import redis

from tests.helpers import Api

pytestmark = [pytest.mark.api, pytest.mark.security]

REPORT = {"message": "TypeError: x is undefined", "path": "/settings", "kind": "render"}


def _clear_limits() -> None:
    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    for key in client.scan_iter("rl:*"):
        client.delete(key)


def _clear_stats_cache() -> None:
    redis.Redis.from_url(os.environ["REDIS_URL"]).delete("public:stats:v1")


def test_stats_count_only_active_developers_and_never_show_zero(api: Api) -> None:
    _clear_stats_cache()
    before = api.get("/api/v1/public/stats")
    assert before.status_code == 200
    assert before.headers["cache-control"] == "public, max-age=300"
    assert before.json().get("developers") != 0  # absent rather than zero
    start = before.json().get("developers", 0)
    _clear_stats_cache()
    api.seed("DEVELOPER", verified=True)
    api.seed("DEVELOPER", verified=False)  # pending: not counted
    api.seed("CLIENT", verified=True)  # clients are not developers
    after = api.get("/api/v1/public/stats").json()
    assert after == {"developers": start + 1}


def test_stats_are_cached_for_five_minutes(api: Api) -> None:
    _clear_stats_cache()
    first = api.get("/api/v1/public/stats").json()
    api.seed("DEVELOPER", verified=True)
    assert api.get("/api/v1/public/stats").json() == first
    ttl = redis.Redis.from_url(os.environ["REDIS_URL"]).ttl("public:stats:v1")
    assert 0 < ttl <= 300


def test_stats_expose_nothing_but_the_count(api: Api) -> None:
    _clear_stats_cache()
    api.seed("DEVELOPER", verified=True)
    body = api.get("/api/v1/public/stats").json()
    assert set(body) <= {"developers"}
    raw = redis.Redis.from_url(os.environ["REDIS_URL"]).get("public:stats:v1")
    cached = json.loads(raw or "{}")
    assert set(cached) <= {"developers"}


def test_client_error_report_is_accepted(api: Api) -> None:
    _clear_limits()
    r = api.post("/api/v1/client-errors", json=REPORT)
    assert r.status_code == 204
    assert r.content == b""


def test_client_error_needs_csrf_and_same_origin(api: Api) -> None:
    _clear_limits()
    assert api.post("/api/v1/client-errors", json=REPORT, csrf=False).status_code == 403
    assert (
        api.post("/api/v1/client-errors", json=REPORT, origin="https://evil.example").status_code
        == 403
    )


@pytest.mark.parametrize(
    "body",
    [
        {**REPORT, "role": "ADMIN"},
        {**REPORT, "path": "https://evil.example/x"},
        {**REPORT, "kind": "anything"},
        {"message": "only a message"},
    ],
)
def test_client_error_rejects_bad_reports(api: Api, body: dict[str, object]) -> None:
    _clear_limits()
    r = api.post("/api/v1/client-errors", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_error_rejects_oversized_bodies(api: Api) -> None:
    _clear_limits()
    padded = {**REPORT, "stack": "x" * 3990, "message": "m" * 500}
    big = json.dumps({**padded, "pad": "p" * 9000})
    r = api.post("/api/v1/client-errors", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_client_errors_are_rate_limited(api: Api) -> None:
    _clear_limits()
    statuses = [api.post("/api/v1/client-errors", json=REPORT).status_code for _ in range(11)]
    assert statuses[:10] == [204] * 10
    assert statuses[10] == 429
