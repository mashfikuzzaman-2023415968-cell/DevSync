"""Discussion threads and posts over HTTP (spec §10.2 Discussion, §14.13 row 9; D146).

Covered: a thread starts with its first post and floats up with new posts; the injection corpus
comes back unchanged in titles and posts; mentions keep participants only and tell them; the
title, body and mention bounds and mass assignment; replies stay in their thread and record
`comment.replied` (entity `DISCUSSION_POST`) under the §9.1.4 rule; edit within 15 minutes (a
revision kept) and refused after; soft delete hides the text and the post count drops; another
author's post is not yours (404); who may read and write (client yes, admin 403, former members,
other clients and outsiders 404, nothing written once the project is finished); paging and
unknown parameters; threads and posts share the 60/hour `comment` limit with comments.

Modules driven: `app/api/v1/discussion.py`, `app/services/discussion.py`,
`app/schemas/comments.py` (ThreadCreate, PostCreate).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.helpers import Api
from tests.security.formation_world import BASE, _code, _sql
from tests.security.test_profiles_files import INJECTION
from tests.security.workspace_world import (
    act_as,
    events,
    reset_limits,
    set_project_status,
    started_project,
)

pytestmark = [pytest.mark.security, pytest.mark.api]


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    world = started_project(api, migration_url)
    world["url"] = migration_url
    act_as(api, world["lead"])
    return world


def _new_thread(api: Api, w: dict[str, Any], title: str = "Release checklist", **extra: Any) -> Any:
    body = {"title": title, "body": "Draft below", **extra}
    return api.post(f"{BASE}/projects/{w['pid']}/threads", json=body)


def _thread(api: Api, w: dict[str, Any], title: str = "Release checklist") -> dict[str, Any]:
    r = _new_thread(api, w, title)
    assert r.status_code == 201, r.text
    return dict(r.json())


def _post(api: Api, thread: dict[str, Any], body: str = "Agreed", **extra: Any) -> Any:
    return api.post(f"{BASE}/threads/{thread['id']}/posts", json={"body": body, **extra})


def _posts(api: Api, thread: dict[str, Any]) -> list[dict[str, Any]]:
    r = api.get(f"{BASE}/threads/{thread['id']}/posts")
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def _threads(api: Api, w: dict[str, Any]) -> list[dict[str, Any]]:
    r = api.get(f"{BASE}/projects/{w['pid']}/threads")
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def test_a_thread_starts_with_its_first_post_and_floats_up(api: Api, w: dict[str, Any]) -> None:
    first = _thread(api, w, "Release checklist")
    assert first["post_count"] == 1
    assert first["created_by"]["id"] == w["lead"].user_id
    second = _thread(api, w, "API naming")
    assert [t["title"] for t in _threads(api, w)] == ["API naming", "Release checklist"]
    act_as(api, w["member"])
    assert _post(api, first).status_code == 201
    listed = _threads(api, w)
    assert [t["title"] for t in listed] == ["Release checklist", "API naming"]
    assert listed[0]["post_count"] == 2
    assert listed[0]["last_post_at"] >= second["last_post_at"]
    posts = _posts(api, first)
    assert [(p["body"], p["target_type"], p["target_id"]) for p in posts] == [
        ("Draft below", "DISCUSSION_POST", first["id"]),
        ("Agreed", "DISCUSSION_POST", first["id"]),
    ]
    posted = events(w["url"], w["pid"], "comment.posted")
    assert len(posted) == 3
    assert {e["data"]["target_type"] for e in posted} == {"DISCUSSION_POST"}


def test_injection_corpus_comes_back_unchanged(api: Api, w: dict[str, Any]) -> None:
    thread = _thread(api, w)
    for text in INJECTION:
        r = _post(api, thread, text)
        assert r.status_code == 201, r.text
        assert r.json()["body"] == text
    assert [p["body"] for p in _posts(api, thread)][1:] == INJECTION
    titled = _new_thread(api, w, "<script>alert(1)</script>")
    assert titled.status_code == 201
    assert titled.json()["title"] == "<script>alert(1)</script>"


def test_mentions_keep_participants_only(api: Api, w: dict[str, Any]) -> None:
    ids = [w["member"].user_id, w["outsider"].user_id, w["former"].user_id, w["client"].user_id]
    r = _new_thread(api, w, "Who reviews?", mention_ids=ids)
    assert r.status_code == 201, r.text
    first = _posts(api, r.json())[0]
    assert [m["id"] for m in first["mentions"]] == [w["member"].user_id, w["client"].user_id]
    act_as(api, w["outsider"])
    mine = api.get(f"{BASE}/notifications").json()["items"]
    assert not [n for n in mine if n["type"] == "MENTIONED"]
    act_as(api, w["member"])
    mentioned = [
        n for n in api.get(f"{BASE}/notifications").json()["items"] if n["type"] == "MENTIONED"
    ]
    assert mentioned
    assert mentioned[0]["link_path"] == f"/w/{w['pid']}/discussion?thread={r.json()['id']}"


def test_bounds_and_mass_assignment(api: Api, w: dict[str, Any]) -> None:
    assert _new_thread(api, w, "ab").status_code == 422
    assert _new_thread(api, w, "abc").status_code == 201
    assert _new_thread(api, w, "t" * 120).status_code == 201
    assert _new_thread(api, w, "t" * 121).status_code == 422
    thread = _thread(api, w)
    eleven = [str(uuid.uuid4()) for _ in range(11)]
    assert _post(api, thread, mention_ids=eleven).status_code == 422
    assert _post(api, thread, mention_ids=eleven[:10]).status_code == 201
    assert _post(api, thread, mention_ids=[w["member"].user_id] * 2).status_code == 422
    assert _post(api, thread, "x" * 4000).status_code == 201
    assert _post(api, thread, "x" * 4001).status_code == 422
    assert _post(api, thread, "").status_code == 422
    for field in ({"author_id": w["member"].user_id}, {"thread_id": thread["id"]}):
        assert _post(api, thread, **field).status_code == 422
    assert _new_thread(api, w, "Extra", created_by=w["member"].user_id).status_code == 422
    unknown = {"id": str(uuid.uuid4())}
    assert _post(api, unknown).status_code == 404


def test_replies_stay_in_their_thread_and_count_as_reply_evidence(
    api: Api, w: dict[str, Any]
) -> None:
    a = _thread(api, w, "Thread A")
    b = _thread(api, w, "Thread B")
    question = _post(api, a, "Can you check paging?", mention_ids=[w["member"].user_id]).json()
    act_as(api, w["member"])
    assert _post(api, a, "Done", reply_to_id=question["id"]).status_code == 201
    replied = events(w["url"], w["pid"], "comment.replied")
    assert len(replied) == 1
    assert replied[0]["data"]["to_author_id"] == w["lead"].user_id
    act_as(api, w["client"])  # not mentioned: no reply evidence
    assert _post(api, a, "Thanks", reply_to_id=question["id"]).status_code == 201
    assert len(events(w["url"], w["pid"], "comment.replied")) == 1
    wrong = _post(api, b, "Hi", reply_to_id=question["id"])
    assert (wrong.status_code, _code(wrong)) == (422, "VALIDATION_ERROR")


def test_edit_within_fifteen_minutes_and_delete(api: Api, w: dict[str, Any]) -> None:
    thread = _thread(api, w)
    p = _post(api, thread, "First thought").json()
    edited = api.patch(f"{BASE}/posts/{p['id']}", json={"body": "Second thought"})
    assert (edited.status_code, edited.json()["edited"]) == (200, True)
    stale = api.patch(
        f"{BASE}/posts/{p['id']}", json={"body": "Old copy"}, headers={"If-Match": "1"}
    )
    assert (stale.status_code, _code(stale)) == (409, "VERSION_CONFLICT")
    revisions = _sql(
        w["url"], "SELECT body FROM discussion_post_revisions WHERE post_id = :p", p=p["id"]
    )
    assert [row[0] for row in revisions] == ["First thought"]
    act_as(api, w["member"])
    assert api.patch(f"{BASE}/posts/{p['id']}", json={"body": "Not mine"}).status_code == 404
    assert api.delete(f"{BASE}/posts/{p['id']}").status_code == 404
    act_as(api, w["lead"])
    _sql(w["url"], "ALTER TABLE discussion_posts DISABLE TRIGGER discussion_posts_revision")
    try:
        _sql(
            w["url"],
            "UPDATE discussion_posts SET created_at = now() - interval '16 minutes' WHERE id = :p",
            p=p["id"],
        )
    finally:
        _sql(w["url"], "ALTER TABLE discussion_posts ENABLE TRIGGER discussion_posts_revision")
    late = api.patch(f"{BASE}/posts/{p['id']}", json={"body": "Too late"})
    assert (late.status_code, _code(late)) == (409, "EDIT_WINDOW_CLOSED")
    assert api.delete(f"{BASE}/posts/{p['id']}").status_code == 204
    gone = next(x for x in _posts(api, thread) if x["id"] == p["id"])
    assert (gone["deleted"], gone["body"], gone["mentions"]) == (True, "", [])
    assert _threads(api, w)[0]["post_count"] == 1  # only the opening post is left
    assert api.delete(f"{BASE}/posts/{p['id']}").status_code == 404


def test_who_may_read_and_write(api: Api, w: dict[str, Any]) -> None:
    thread = _thread(api, w)
    act_as(api, w["client"])
    assert _post(api, thread, "From the client").status_code == 201
    assert _new_thread(api, w, "Client question").status_code == 201
    for who in ("outsider", "former", "other_client"):
        act_as(api, w[who])
        assert api.get(f"{BASE}/projects/{w['pid']}/threads").status_code == 404, who
        assert _new_thread(api, w).status_code == 404, who
        assert api.get(f"{BASE}/threads/{thread['id']}/posts").status_code == 404, who
        assert _post(api, thread).status_code == 404, who
    api.sign_in_as("ADMIN")
    assert api.get(f"{BASE}/projects/{w['pid']}/threads").status_code == 403
    assert _new_thread(api, w).status_code == 403
    # RLS hides thread rows from admins entirely, so reading a thread is simply not found;
    # writing is refused earlier, by the account gate (admins never write in a workspace).
    assert api.get(f"{BASE}/threads/{thread['id']}/posts").status_code == 404
    assert _post(api, thread).status_code == 403
    act_as(api, w["member"])
    set_project_status(w["url"], w["pid"], "COMPLETED")
    assert len(_posts(api, thread)) == 2  # still readable
    r = _post(api, thread)
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")
    assert _new_thread(api, w).status_code == 409


def test_paging_and_parameters(api: Api, w: dict[str, Any]) -> None:
    for n in range(3):
        _thread(api, w, f"Thread {n}")
    first = api.get(f"{BASE}/projects/{w['pid']}/threads?limit=2").json()
    assert [t["title"] for t in first["items"]] == ["Thread 2", "Thread 1"]
    rest = api.get(f"{BASE}/projects/{w['pid']}/threads?limit=2&cursor={first['next_cursor']}")
    assert [t["title"] for t in rest.json()["items"]] == ["Thread 0"]
    thread = first["items"][0]
    for n in range(2):
        _post(api, thread, f"Reply {n}")
    page = api.get(f"{BASE}/threads/{thread['id']}/posts?limit=2").json()
    more = api.get(f"{BASE}/threads/{thread['id']}/posts?cursor={page['next_cursor']}").json()
    assert [p["body"] for p in page["items"] + more["items"]] == [
        "Draft below",
        "Reply 0",
        "Reply 1",
    ]
    for query in ("cursor=bm9wZQ", "limit=0", "limit=101", "sort=new", "limit=2&limit=3"):
        r = api.get(f"{BASE}/projects/{w['pid']}/threads?{query}")
        assert r.status_code in (400, 422), (query, r.status_code)


def test_threads_and_posts_share_the_comment_limit(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    reset_limits(api)
    api.csrf_token()

    def headers() -> dict[str, str]:
        return {"X-CSRF-Token": api.client.cookies["__Host-ds_csrf"]}

    opened = api.post(
        f"{BASE}/projects/{w['pid']}/threads",
        json={"title": "Busy thread", "body": "Start"},
        headers=headers(),
    )
    assert opened.status_code == 201, opened.text
    thread = opened.json()
    for i in range(59):  # 1 thread + 59 posts = 60 in the hour
        r = api.post(
            f"{BASE}/threads/{thread['id']}/posts", json={"body": f"Post {i}"}, headers=headers()
        )
        assert r.status_code == 201, (i, r.text)
    over = api.post(
        f"{BASE}/comments",
        json={"target_type": "MILESTONE", "target_id": w["m1"], "body": "One more"},
        headers=headers(),
    )
    assert (over.status_code, _code(over)) == (429, "RATE_LIMITED")
