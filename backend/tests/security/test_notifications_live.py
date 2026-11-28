"""Notification preferences, delivery and the live stream (spec §10.2, §12, §14.13 row 9; D107,
D153, D162–D164).

Covered:
- preferences: every §12 row with its defaults (mentions email off); saving changes only the rows
  sent, is audited and is per user; an unknown category, an email on an in-app-only row, a row
  twice, an extra field or an empty list → 422;
- delivery: a mention with the in-app switch off writes no notification; the mention email is
  queued only once the email switch is on (opt-in), as the `mentioned` template;
- publishing: a committed notification is published to its owner's channel with only
  `{id, type, title}`; a rolled-back one never is;
- the stream: no session 401; a foreign `Origin` or `Sec-Fetch-Site: cross-site` 403; the fourth
  open stream (jobs included) 429 and slots come back when streams end; `Last-Event-ID` replays
  only the caller's newer notifications (an unknown id replays nothing); a notification published
  while the stream is open arrives; heartbeats; the stream ends by itself (`SSE_MAX_SECONDS`).

Modules driven: `app/api/v1/notifications.py`, `app/services/notifications.py`,
`app/services/notification_prefs.py`, `app/services/outbox.py`, `app/schemas/notifications.py`,
`app/core/notification_types.py`.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

import pytest
import redis

from app.api.v1 import notifications as stream_api
from app.core.job_events import MAX_STREAMS_PER_USER
from app.db.context import DbContext
from app.db.session import open_session
from app.services import notifications as svc
from tests.helpers import ORIGIN, Api
from tests.security.formation_world import BASE, _code, _job, _sql
from tests.security.workspace_world import act_as, audits, started_project

pytestmark = [pytest.mark.security, pytest.mark.api]


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    world = started_project(api, migration_url)
    world["url"] = migration_url
    act_as(api, world["lead"])
    task = api.post(
        f"{BASE}/milestones/{world['m1']}/tasks",
        json={"title": "Stock list API", "estimate_hours": "8.0", "difficulty": "MEDIUM"},
    )
    assert task.status_code == 201, task.text
    world["task"] = task.json()["id"]
    return world


def _redis() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"])


def _mention(api: Api, w: dict[str, Any], who: str = "member", text: str = "Can you check?") -> Any:
    act_as(api, w["lead"])
    r = api.post(
        f"{BASE}/comments",
        json={
            "target_type": "TASK",
            "target_id": w["task"],
            "body": text,
            "mention_ids": [w[who].user_id],
        },
    )
    assert r.status_code == 201, r.text
    return r


def _mine(api: Api, kind: str = "MENTIONED") -> list[dict[str, Any]]:
    items = api.get(f"{BASE}/notifications").json()["items"]
    return [n for n in items if n["type"] == kind]


def _outbox(url: str, email: str, template: str) -> int:
    rows = _sql(
        url,
        "SELECT count(*) FROM email_outbox WHERE to_email = :e AND template = :t",
        e=email,
        t=template,
    )
    return int(rows[0][0])


def _events(text: str) -> list[dict[str, Any]]:
    out = []
    for block in text.split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if ": " in line and line[0] != ":"
        )
        if fields.get("event") == "notification":
            out.append({"id": fields["id"], **json.loads(fields["data"])})
    return out


# --------------------------------------------------------------------------- preferences


def test_preferences_list_every_row_with_its_defaults(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    r = api.get(f"{BASE}/notification-preferences")
    assert r.status_code == 200, r.text
    rows = {i["category"]: i for i in r.json()["items"]}
    assert len(rows) == 13
    assert rows["mentions"] == {
        "category": "mentions",
        "label": "Someone mentioned you",
        "in_app": True,
        "email": False,
        "email_available": True,
    }
    assert (rows["blockers"]["email"], rows["blockers"]["email_available"]) == (False, False)
    assert rows["critical_risk"]["email"] is True


def test_saving_preferences_changes_only_the_rows_sent(
    api: Api, api2: Api, w: dict[str, Any]
) -> None:
    act_as(api, w["member"])
    r = api.put(
        f"{BASE}/notification-preferences",
        json={"items": [{"category": "mentions", "in_app": False, "email": True}]},
    )
    assert r.status_code == 200, r.text
    rows = {i["category"]: i for i in r.json()["items"]}
    assert (rows["mentions"]["in_app"], rows["mentions"]["email"]) == (False, True)
    assert rows["critical_risk"]["email"] is True  # untouched
    assert audits(w["url"], w["member"].user_id, "notification_preferences.update") == 1
    act_as(api2, w["lead"])  # someone else's switches are theirs
    other = {i["category"]: i for i in api2.get(f"{BASE}/notification-preferences").json()["items"]}
    assert other["mentions"]["in_app"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"items": [{"category": "nope", "in_app": True, "email": False}]},
        {"items": [{"category": "blockers", "in_app": True, "email": True}]},  # no email in §12
        {"items": [{"category": "mentions", "in_app": True, "email": False}] * 2},
        {"items": [{"category": "mentions", "in_app": True, "email": False, "user_id": "x"}]},
        {"items": [{"category": "mentions", "in_app": "maybe", "email": False}]},
        {"items": []},
        {},
    ],
)
def test_bad_preference_updates_are_refused(api: Api, w: dict[str, Any], body: Any) -> None:
    act_as(api, w["member"])
    r = api.put(f"{BASE}/notification-preferences", json=body)
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- delivery


def test_switches_decide_the_in_app_row_and_the_email(api: Api, w: dict[str, Any]) -> None:
    email = w["member"].email
    _mention(api, w, text="First")
    act_as(api, w["member"])
    assert len(_mine(api)) == 1
    assert _outbox(w["url"], email, "mentioned") == 0  # email is opt-in (D153)
    api.put(
        f"{BASE}/notification-preferences",
        json={"items": [{"category": "mentions", "in_app": False, "email": True}]},
    )
    _mention(api, w, text="Second")
    act_as(api, w["member"])
    assert len(_mine(api)) == 1  # no new in-app row
    assert _outbox(w["url"], email, "mentioned") == 1


def test_committed_notifications_are_published_and_rolled_back_ones_are_not(
    api: Api, w: dict[str, Any]
) -> None:
    member = uuid.UUID(w["member"].user_id)
    listener = _redis().pubsub()  # type: ignore[no-untyped-call]  # redis-py leaves it untyped
    listener.subscribe(svc.channel(member))
    try:
        listener.get_message(timeout=1)  # the subscribe confirmation

        async def rolled_back() -> None:
            async with open_session(DbContext.system(), job=True) as db:
                await svc.notify(db, member, "MENTIONED", title="Never", body="b", link="/")
                await db.rollback()

        _job(rolled_back())
        assert listener.get_message(timeout=0.5) is None
        _mention(api, w)
        message = listener.get_message(timeout=3)
        assert message is not None
        assert message["type"] == "message"
        data = json.loads(message["data"])
        assert set(data) == {"id", "type", "title"}
        assert data["type"] == "MENTIONED"
    finally:
        listener.close()


# --------------------------------------------------------------------------- the stream


def _stream(api: Api, **headers: str) -> Any:
    return api.get(f"{BASE}/notifications/stream", headers=headers)


@pytest.mark.parametrize(
    "headers",
    [{"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}],
)
def test_cross_site_streams_are_refused(
    api: Api, w: dict[str, Any], headers: dict[str, str]
) -> None:
    act_as(api, w["member"])
    r = _stream(api, **headers)
    assert (r.status_code, _code(r)) == (403, "CSRF_FAILED")


def test_no_session_no_stream(api: Api) -> None:
    api.client.cookies.clear()
    assert _stream(api).status_code == 401


def test_the_fourth_stream_is_refused_and_slots_come_back(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    key = f"sse:concurrent:{w['member'].user_id}"
    store = _redis()
    store.set(key, MAX_STREAMS_PER_USER)  # three streams (jobs or notifications) already open
    r = _stream(api)
    assert (r.status_code, _code(r)) == (429, "RATE_LIMITED")
    store.delete(key)
    ok = _stream(api, Origin=ORIGIN, **{"Sec-Fetch-Site": "same-origin"})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/event-stream")
    assert ok.headers["cache-control"] == "no-store"
    assert int(store.get(key) or 0) == 0  # the ended stream gave its slot back


def test_last_event_id_replays_only_your_newer_notifications(api: Api, w: dict[str, Any]) -> None:
    for n in range(3):
        _mention(api, w, text=f"Note {n}")
    _mention(api, w, who="client", text="For the client")
    act_as(api, w["member"])
    mine = list(reversed(_mine(api)))  # oldest first
    assert len(mine) == 3
    replay = _events(_stream(api, **{"Last-Event-ID": mine[0]["id"]}).text)
    assert [e["id"] for e in replay] == [mine[1]["id"], mine[2]["id"]]
    assert all(set(e) == {"id", "type", "title"} for e in replay)
    assert _events(_stream(api, **{"Last-Event-ID": str(uuid.uuid4())}).text) == []
    assert _events(_stream(api, **{"Last-Event-ID": "not-an-id"}).text) == []
    act_as(api, w["client"])  # someone else's id gives the client nothing of the member's
    assert _events(_stream(api, **{"Last-Event-ID": mine[0]["id"]}).text) == []


def test_a_live_notification_arrives_with_heartbeats(
    api: Api, w: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stream_api, "HEARTBEAT_SECONDS", 0.5)
    act_as(api, w["member"])
    member = uuid.UUID(w["member"].user_id)
    live = {"user_id": str(member), "id": str(uuid.uuid4()), "type": "MENTIONED", "title": "Hi"}
    other = {"user_id": w["lead"].user_id, "id": str(uuid.uuid4()), "type": "MENTIONED",
             "title": "Not yours"}  # fmt: skip
    timer = threading.Timer(0.8, lambda: svc.publish([live, other]))
    timer.start()
    began = time.monotonic()
    try:
        r = _stream(api)
    finally:
        timer.cancel()
    assert time.monotonic() - began < 10  # ended by itself (SSE_MAX_SECONDS in tests)
    assert r.text.startswith("retry: ")
    assert ": heartbeat" in r.text
    assert [e["id"] for e in _events(r.text)] == [live["id"]]
