"""Generic job status and the live event stream (spec §10.3, §14.13, D107).

- a job is visible to its requester and admins only (others and unknown ids: 404);
- the stream sends the current state, then the worker's events in order, and ends on a final
  event; a reconnect with `Last-Event-ID` resumes after it; a finished job streams its state and
  closes at once;
- a foreign Origin or a cross-site `Sec-Fetch-Site` is refused (403), anonymous is 401;
- a user's fourth concurrent stream is refused (429) and closed streams give their slot back.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import redis
from sqlalchemy import create_engine, text

from app.core.job_events import ALLOWED_KEYS, MAX_STREAMS_PER_USER, events_key
from tests.helpers import Api, stack_settings

pytestmark = [pytest.mark.security, pytest.mark.api]
BASE = "/api/v1"


def make_job(migration_url: str, requested_by: str | None, status: str = "RUNNING") -> str:
    engine = create_engine(migration_url)
    with engine.begin() as conn:
        job_id = conn.execute(
            text(
                "INSERT INTO jobs (type, status, progress, requested_by) "
                "VALUES ('formation.run', CAST(:s AS job_status), 10, :u) RETURNING id"
            ),
            {"s": status, "u": uuid.UUID(requested_by) if requested_by else None},
        ).scalar_one()
    engine.dispose()
    return str(job_id)


def _redis() -> redis.Redis:
    return redis.Redis.from_url(stack_settings().REDIS_URL)


def push(job_id: str, *events: dict[str, Any]) -> None:
    r = _redis()
    for event in events:
        assert set(event) <= ALLOWED_KEYS
        r.rpush(events_key(uuid.UUID(job_id)), json.dumps(event))
    r.close()


def parse(body: str) -> list[tuple[str | None, str, dict[str, Any]]]:
    """(id, event name, data) for each event in an SSE body; comments and `retry` skipped."""
    out = []
    for block in body.strip().split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if line.startswith(":") or ": " not in line:
                continue
            key, value = line.split(": ", 1)
            fields[key] = value
        if "data" in fields:
            out.append(
                (fields.get("id"), fields.get("event", "message"), json.loads(fields["data"]))
            )
    return out


def stream(api: Api, job_id: str, **headers: str) -> Any:
    return api.get(f"{BASE}/jobs/{job_id}/events", headers=headers)


def test_status_is_for_the_requester_and_admins(api: Api, api2: Api, migrated: str) -> None:
    owner = api.sign_in_as("CLIENT")
    api2.sign_in_as("CLIENT")
    job = make_job(migrated, owner.user_id)
    r = api.get(f"{BASE}/jobs/{job}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "RUNNING"
    assert body["progress"] == 10
    assert set(body) == {"id", "type", "status", "progress", "error_code", "created_at",
                         "started_at", "finished_at"}  # fmt: skip
    assert api2.get(f"{BASE}/jobs/{job}").status_code == 404
    assert api2.get(f"{BASE}/jobs/{job}/events").status_code == 404
    assert api.get(f"{BASE}/jobs/{uuid.uuid4()}").status_code == 404
    assert api.get(f"{BASE}/jobs/not-a-uuid").status_code == 422
    system_job = make_job(migrated, None)
    assert api.get(f"{BASE}/jobs/{system_job}").status_code == 404


def test_admin_reads_any_job(api: Api, api2: Api, migrated: str) -> None:
    owner = api.sign_in_as("CLIENT")
    api2.sign_in_as("ADMIN")
    job = make_job(migrated, owner.user_id)
    assert api2.get(f"{BASE}/jobs/{job}").status_code == 200


def test_anonymous_is_refused(api: Api, migrated: str) -> None:
    job = make_job(migrated, None)
    assert api.get(f"{BASE}/jobs/{job}").status_code == 401
    assert api.get(f"{BASE}/jobs/{job}/events").status_code == 401


def test_stream_sends_state_then_events_and_ends_on_the_final_one(api: Api, migrated: str) -> None:
    owner = api.sign_in_as("CLIENT")
    job = make_job(migrated, owner.user_id)
    push(job, {"type": "iteration", "progress": 40, "iteration": 80, "best_fitness": 0.61},
         {"type": "done", "status": "SUCCEEDED", "progress": 100},
         {"type": "iteration", "progress": 100})  # after the end: never sent  # fmt: skip
    r = stream(api, job)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-accel-buffering"] == "no"
    events = parse(r.text)
    assert [e[1] for e in events] == ["status", "progress", "progress"]
    assert events[0][2] == {"status": "RUNNING", "progress": 10}
    assert [e[0] for e in events[1:]] == ["0", "1"]
    assert events[2][2]["status"] == "SUCCEEDED"
    # Resuming after event 0 replays only event 1.
    resumed = parse(stream(api, job, **{"Last-Event-ID": "0"}).text)
    assert [e[0] for e in resumed[1:]] == ["1"]
    # A nonsense Last-Event-ID starts from the beginning instead of failing.
    assert len(parse(stream(api, job, **{"Last-Event-ID": "-5"}).text)) == 3


def test_a_finished_job_streams_its_state_and_closes(api: Api, migrated: str) -> None:
    owner = api.sign_in_as("CLIENT")
    job = make_job(migrated, owner.user_id, status="FAILED")
    events = parse(stream(api, job).text)
    assert events == [(None, "status", {"status": "FAILED", "progress": 10})]


@pytest.mark.parametrize(
    "headers",
    [{"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"},
     {"Sec-Fetch-Site": "same-site"}],
)  # fmt: skip
def test_cross_site_streams_are_refused(api: Api, migrated: str, headers: dict[str, str]) -> None:
    owner = api.sign_in_as("CLIENT")
    job = make_job(migrated, owner.user_id, status="SUCCEEDED")
    r = stream(api, job, **headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"


def test_same_origin_headers_are_accepted(api: Api, migrated: str) -> None:
    owner = api.sign_in_as("CLIENT")
    job = make_job(migrated, owner.user_id, status="SUCCEEDED")
    r = stream(api, job, Origin=stack_settings().PUBLIC_ORIGIN, **{"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


def test_fourth_concurrent_stream_is_refused_and_slots_come_back(api: Api, migrated: str) -> None:
    owner = api.sign_in_as("CLIENT")
    job = make_job(migrated, owner.user_id, status="SUCCEEDED")
    key = f"sse:concurrent:{owner.user_id}"
    r = _redis()
    r.set(key, MAX_STREAMS_PER_USER)  # three streams already open elsewhere
    refused = stream(api, job)
    assert refused.status_code == 429
    assert int(r.get(key) or 0) == MAX_STREAMS_PER_USER  # the refusal took no slot
    r.set(key, MAX_STREAMS_PER_USER - 1)
    assert stream(api, job).status_code == 200
    assert int(r.get(key) or 0) == MAX_STREAMS_PER_USER - 1  # closed stream gave it back
    r.delete(key)
    r.close()
