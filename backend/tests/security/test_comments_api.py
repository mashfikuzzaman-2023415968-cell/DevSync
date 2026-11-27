"""Comments over HTTP (spec §10.2, §12, §14.13 row 9, §17 Phase 9; D146, D149, D169).

Covered: the injection corpus stored and returned unchanged (rendered as text by the UI); a
mention of a non-member is ignored (not stored, not notified); the 11th mention is refused;
4000/4001 characters; edit inside 15 minutes (a revision kept) and refused after; soft delete
hides the text; replies stay on their target; `comment.replied` and `blocker.answered` follow the
§9.1.4–9.1.5 rules; who may comment (client yes, admin 403, outsiders 404); the shared 60/hour
limit at its boundary.

Modules driven: `app/api/v1/comments.py`, `app/services/comments.py`, `app/schemas/comments.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import Api
from tests.security.formation_world import BASE, _code, _sql
from tests.security.test_profiles_files import INJECTION
from tests.security.workspace_world import act_as, events, reset_limits, started_project

pytestmark = [pytest.mark.security, pytest.mark.api]


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    world = started_project(api, migration_url)
    world["url"] = migration_url
    act_as(api, world["lead"])
    task = api.post(
        f"{BASE}/milestones/{world['m1']}/tasks",
        json={
            "title": "Stock list API",
            "estimate_hours": "8.0",
            "difficulty": "MEDIUM",
            "assignee_id": world["member"].user_id,
        },
    )
    assert task.status_code == 201, task.text
    world["task"] = task.json()["id"]
    return world


def _comment(
    api: Api,
    w: dict[str, Any],
    body: str = "Looks good",
    *,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> Any:
    return api.post(
        f"{BASE}/comments",
        json={"target_type": "TASK", "target_id": w["task"], "body": body, **extra},
        headers=headers or {},
    )


def _thread(api: Api, w: dict[str, Any]) -> list[dict[str, Any]]:
    r = api.get(f"{BASE}/comments?target_type=TASK&target_id={w['task']}")
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def test_injection_corpus_comes_back_unchanged(api: Api, w: dict[str, Any]) -> None:
    for text in INJECTION:
        r = _comment(api, w, text)
        assert r.status_code == 201, r.text
        assert r.json()["body"] == text
    assert [c["body"] for c in _thread(api, w)] == INJECTION


def test_mentions_keep_participants_only(api: Api, w: dict[str, Any]) -> None:
    ids = [w["member"].user_id, w["outsider"].user_id, w["former"].user_id, w["client"].user_id]
    r = _comment(api, w, "@Nusrat @everyone", mention_ids=ids)
    assert r.status_code == 201, r.text
    kept = [m["id"] for m in r.json()["mentions"]]
    assert kept == [w["member"].user_id, w["client"].user_id]
    stored = _sql(w["url"], "SELECT mentions FROM comments WHERE id = :c", c=r.json()["id"])
    assert {str(x) for x in stored[0][0]} == set(kept)
    act_as(api, w["outsider"])
    assert not [
        n for n in api.get(f"{BASE}/notifications").json()["items"] if n["type"] == "MENTIONED"
    ]
    act_as(api, w["member"])
    assert [n for n in api.get(f"{BASE}/notifications").json()["items"] if n["type"] == "MENTIONED"]


def test_mention_and_length_bounds(api: Api, w: dict[str, Any]) -> None:
    import uuid  # noqa: PLC0415 - only here

    eleven = [str(uuid.uuid4()) for _ in range(11)]
    assert _comment(api, w, mention_ids=eleven).status_code == 422
    assert _comment(api, w, mention_ids=eleven[:10]).status_code == 201  # dropped, not refused
    twice = [w["member"].user_id, w["member"].user_id]
    assert _comment(api, w, mention_ids=twice).status_code == 422
    assert _comment(api, w, "x" * 4000).status_code == 201
    assert _comment(api, w, "x" * 4001).status_code == 422
    assert _comment(api, w, "").status_code == 422
    for field in ({"author_id": w["lead"].user_id}, {"deleted_at": None}, {"project_id": w["pid"]}):
        assert _comment(api, w, **field).status_code == 422


def test_edit_within_fifteen_minutes_and_delete(api: Api, w: dict[str, Any]) -> None:
    r = _comment(api, w, "First thought")
    c = r.json()
    assert c["can_edit"] is True
    edited = api.patch(f"{BASE}/comments/{c['id']}", json={"body": "Second thought"})
    assert (edited.status_code, edited.json()["edited"]) == (200, True)
    revisions = _sql(
        w["url"], "SELECT body FROM comment_revisions WHERE comment_id = :c", c=c["id"]
    )
    assert [row[0] for row in revisions] == ["First thought"]
    act_as(api, w["member"])
    other = api.patch(f"{BASE}/comments/{c['id']}", json={"body": "Not mine"})
    assert other.status_code == 404  # someone else's comment isn't yours to change (RLS hides it)
    assert api.delete(f"{BASE}/comments/{c['id']}").status_code == 404
    act_as(api, w["lead"])
    # Backdate the comment as the migrator, with the who/when guard (D169) off for this one
    # statement: the guard refuses exactly this change, which is what it is for.
    _sql(w["url"], "ALTER TABLE comments DISABLE TRIGGER comments_revision")
    try:
        _sql(
            w["url"],
            "UPDATE comments SET created_at = now() - interval '16 minutes' WHERE id = :c",
            c=c["id"],
        )
    finally:
        _sql(w["url"], "ALTER TABLE comments ENABLE TRIGGER comments_revision")
    late = api.patch(f"{BASE}/comments/{c['id']}", json={"body": "Too late"})
    assert (late.status_code, _code(late)) == (409, "EDIT_WINDOW_CLOSED")
    assert api.delete(f"{BASE}/comments/{c['id']}").status_code == 204
    gone = next(x for x in _thread(api, w) if x["id"] == c["id"])
    assert (gone["deleted"], gone["body"], gone["mentions"]) == (True, "", [])
    assert api.delete(f"{BASE}/comments/{c['id']}").status_code == 404


def test_replies_and_reply_evidence(api: Api, w: dict[str, Any]) -> None:
    question = _comment(api, w, "Can you check paging?", mention_ids=[w["member"].user_id]).json()
    act_as(api, w["member"])
    reply = _comment(api, w, "Done", reply_to_id=question["id"])
    assert reply.status_code == 201
    replied = events(w["url"], w["pid"], "comment.replied")
    assert len(replied) == 1
    assert replied[0]["data"]["to_author_id"] == w["lead"].user_id
    assert replied[0]["data"]["response_seconds"] >= 0
    act_as(api, w["client"])  # not mentioned: no reply evidence
    _comment(api, w, "Thanks", reply_to_id=question["id"])
    assert len(events(w["url"], w["pid"], "comment.replied")) == 1
    act_as(api, w["lead"])
    elsewhere = api.post(
        f"{BASE}/comments",
        json={
            "target_type": "MILESTONE",
            "target_id": w["m1"],
            "body": "Hi",
            "reply_to_id": question["id"],
        },
    )
    assert elsewhere.status_code == 422


def test_a_blocker_answered_counts_a_teammate_once(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    checkin = api.post(
        f"{BASE}/projects/{w['pid']}/checkins",
        json={"done": "a", "next": "b", "blockers": "No keys", "confidence": 2},
    ).json()
    target = {"target_type": "CHECKIN", "target_id": checkin["id"]}

    def reply(who: str) -> None:
        act_as(api, w[who])
        assert api.post(f"{BASE}/comments", json={**target, "body": "Try this"}).status_code == 201

    reply("member")  # the author: not help
    reply("client")  # the client: not a teammate
    assert events(w["url"], w["pid"], "blocker.answered") == []
    reply("lead")
    reply("lead")
    answered = events(w["url"], w["pid"], "blocker.answered")
    assert len(answered) == 1
    assert answered[0]["actor_id"] == w["lead"].user_id


def test_who_may_comment(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["client"])
    assert _comment(api, w).status_code == 201
    for who in ("outsider", "former", "other_client"):
        act_as(api, w[who])
        assert _comment(api, w).status_code == 404, who
        assert api.get(f"{BASE}/comments?target_type=TASK&target_id={w['task']}").status_code == 404
    api.sign_in_as("ADMIN")
    assert _comment(api, w).status_code == 403
    assert api.get(f"{BASE}/comments?target_type=TASK&target_id={w['task']}").status_code == 403


def test_a_client_comment_is_not_task_activity(api: Api, w: dict[str, Any]) -> None:
    before = _sql(w["url"], "SELECT last_activity_at FROM tasks WHERE id = :t", t=w["task"])
    act_as(api, w["client"])
    assert _comment(api, w).status_code == 201
    after = _sql(w["url"], "SELECT last_activity_at FROM tasks WHERE id = :t", t=w["task"])
    assert before == after
    act_as(api, w["member"])
    assert _comment(api, w).status_code == 201
    touched = _sql(w["url"], "SELECT last_activity_at FROM tasks WHERE id = :t", t=w["task"])
    assert touched[0][0] > before[0][0]


def test_sixty_comments_an_hour(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])  # sign-in state otherwise depends on test order
    reset_limits(api)
    # Fetch the CSRF cookie once and send whatever token the jar holds, so the 61 posts don't
    # need 61 token requests and the global 120/min API limit isn't what stops us.
    api.csrf_token()

    def headers() -> dict[str, str]:
        return {"X-CSRF-Token": api.client.cookies["__Host-ds_csrf"]}

    for i in range(60):
        r = _comment(api, w, f"Note {i}", headers=headers())
        assert r.status_code == 201, (i, r.text)
    over = _comment(api, w, "One more", headers=headers())
    assert (over.status_code, _code(over)) == (429, "RATE_LIMITED")
