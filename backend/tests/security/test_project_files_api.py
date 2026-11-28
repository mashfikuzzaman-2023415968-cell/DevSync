"""Project files over HTTP (spec §10.2 Files, §14.9, §16.4; D147, D173, D175).

Covered: participants (client, lead, member) upload, list and download; former members, other
clients and outsiders get 404 everywhere, admins 403 on the list and 404 on the download; §14.9
types only (polyglots, SVG, HTML, archives, executables, empty files refused; names take the
detected extension, Markdown keeps `.md`); per-type size limits; uploads only while the project
is in progress; delete by the uploader or the lead only (soft: never listed or served again,
audited, and the bytes survive the orphan cleanup); the evidence links in the list; paging and
unknown parameters; the daily byte budget (reserve, settle, 429 with `Retry-After`).

Modules driven: `app/api/v1/project_files.py`, `app/services/project_files.py`,
`app/schemas/project_files.py`, `app/uploads/pipeline.py` (PROJECT_FILE), `app/services/files.py`
(`purge_orphans` keeps project files).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import redis
from PIL import Image

from app.db.context import DbContext
from app.db.session import open_session
from app.services import files as files_svc
from app.services.project_files import budget_key
from app.uploads.storage import Storage
from tests.helpers import Api
from tests.security.formation_world import BASE, _code, _job, _sql
from tests.security.test_profiles_files import add_image, follow_download, new_item, pdf
from tests.security.workspace_world import act_as, audits, set_project_status, started_project

pytestmark = [pytest.mark.security, pytest.mark.api]
BUDGET = 500 * 1024 * 1024  # platform settings v6 default (D147)


@pytest.fixture
def w(api: Api, migration_url: str) -> dict[str, Any]:
    world = started_project(api, migration_url)
    world["url"] = migration_url
    return world


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (15, 118, 110)).save(buf, "PNG")
    return buf.getvalue()


def _upload(
    api: Api, w: dict[str, Any], data: bytes | None = None, name: str = "wireframe.png"
) -> Any:
    return api.post(
        f"{BASE}/projects/{w['pid']}/files",
        files={"file": (name, _png() if data is None else data, "application/octet-stream")},
    )


def _uploaded(api: Api, w: dict[str, Any], **kw: Any) -> dict[str, Any]:
    r = _upload(api, w, **kw)
    assert r.status_code == 201, r.text
    return dict(r.json())


def _names(api: Api, w: dict[str, Any]) -> list[str]:
    r = api.get(f"{BASE}/projects/{w['pid']}/files")
    assert r.status_code == 200, r.text
    return [f["name"] for f in r.json()["items"]]


def _redis() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"])


def test_participants_upload_list_and_download(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    mine = _uploaded(api, w, name="board.png")
    assert mine["name"] == "board.png"
    assert mine["mime"] == "image/png"
    assert mine["uploaded_by"] == {"id": w["member"].user_id, "name": mine["uploaded_by"]["name"]}
    assert mine["can_delete"] is True
    assert mine["links"] == []
    assert audits(w["url"], mine["id"], "project_file.upload") == 1
    for who in ("client", "lead"):
        act_as(api, w[who])
        assert "board.png" in _names(api, w)
        blob = follow_download(api, mine["id"])
        assert blob.status_code == 200
        assert blob.headers["content-type"] == "image/png"
        assert blob.headers["content-disposition"].startswith("attachment;")
    act_as(api, w["client"])
    theirs = _uploaded(api, w, name="brief.png")  # the client uploads too (§2.2)
    assert theirs["uploaded_by"]["id"] == w["client"].user_id


def test_non_participants_never_see_project_files(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    f = _uploaded(api, w)
    for who in ("former", "outsider", "other_client"):
        act_as(api, w[who])
        assert api.get(f"{BASE}/projects/{w['pid']}/files").status_code == 404, who
        assert _upload(api, w).status_code == 404, who
        r = api.get(f"{BASE}/files/{f['id']}/download", follow_redirects=False)
        assert r.status_code == 404, who
        assert api.delete(f"{BASE}/files/{f['id']}").status_code == 404, who
    api.sign_in_as("ADMIN")  # admins wait for the Phase 12 dispute context (D173)
    assert api.get(f"{BASE}/projects/{w['pid']}/files").status_code == 403
    assert _upload(api, w).status_code == 403
    r = api.get(f"{BASE}/files/{f['id']}/download", follow_redirects=False)
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (_png() + b"PK\x03\x04" + b"\x00" * 300, "polyglot.png"),
        (b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "x.svg"),
        (b"<html><script>alert(1)</script></html>", "page.html"),
        (b"PK\x03\x04" + b"\x00" * 100, "source.zip"),
        (b"MZ\x90\x00" + b"\x00" * 100, "tool.exe"),
        (pdf(b"1 0 obj<</S/JavaScript/JS(app.alert(1))>>endobj\n"), "scripted.pdf"),
        (b"", "empty.txt"),
    ],
)
def test_only_section_14_9_types_are_accepted(
    api: Api, w: dict[str, Any], data: bytes, name: str
) -> None:
    act_as(api, w["member"])
    r = _upload(api, w, data, name)
    assert r.status_code == 422, (name, r.text)
    assert r.json()["error"]["fields"]["file"]
    assert _names(api, w) == []


def test_names_follow_the_detected_type(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    assert _uploaded(api, w, data=_png(), name="evil.html")["name"] == "evil.png"
    notes = _uploaded(api, w, data=b"# Plan\n\n- [ ] stock table\n", name="notes.md")
    assert (notes["name"], notes["mime"]) == ("notes.md", "text/plain")
    assert _uploaded(api, w, data=b"plain words\n", name="readme")["name"] == "readme.txt"
    spec = _uploaded(api, w, data=pdf(), name="../../etc/spec.PDF")
    assert spec["mime"] == "application/pdf"
    assert "/" not in spec["name"]
    assert spec["name"].endswith(".pdf")


def test_per_type_size_limits(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    text_limit = 1024 * 1024
    assert _upload(api, w, b"a" * text_limit, "edge.txt").status_code == 201
    big_text = _upload(api, w, b"a" * (text_limit + 1), "big.txt")
    assert (big_text.status_code, _code(big_text)) == (413, "PAYLOAD_TOO_LARGE")
    big_pdf = _upload(api, w, pdf(b"%" + b"0" * (10 * 1024 * 1024) + b"\n"), "big.pdf")
    assert big_pdf.status_code == 413


def test_uploads_only_while_the_project_is_in_progress(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    f = _uploaded(api, w)
    set_project_status(w["url"], w["pid"], "COMPLETED")
    r = _upload(api, w)
    assert (r.status_code, _code(r)) == (409, "INVALID_STATE")
    assert api.delete(f"{BASE}/files/{f['id']}").status_code == 409
    listed = api.get(f"{BASE}/projects/{w['pid']}/files").json()["items"]
    assert [x["can_delete"] for x in listed] == [False]  # still readable, no longer changeable


def test_delete_rules_and_soft_delete(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    a = _uploaded(api, w, name="a.png")
    b = _uploaded(api, w, name="b.png")
    act_as(api, w["client"])
    c = _uploaded(api, w, name="c.png")
    items = api.get(f"{BASE}/projects/{w['pid']}/files").json()["items"]
    listed = {x["name"]: x["can_delete"] for x in items}
    assert listed == {"a.png": False, "b.png": False, "c.png": True}
    r = api.delete(f"{BASE}/files/{a['id']}")  # the client didn't upload it and isn't the lead
    assert (r.status_code, _code(r)) == (403, "ROLE_NOT_ALLOWED")
    act_as(api, w["member"])
    assert api.delete(f"{BASE}/files/{c['id']}").status_code == 403
    assert api.delete(f"{BASE}/files/{a['id']}").status_code == 204  # the uploader
    act_as(api, w["lead"])
    assert api.delete(f"{BASE}/files/{b['id']}").status_code == 204  # the lead
    act_as(api, w["client"])
    assert api.delete(f"{BASE}/files/{c['id']}").status_code == 204
    for gone in (a, b, c):
        assert api.delete(f"{BASE}/files/{gone['id']}").status_code == 404
        r = api.get(f"{BASE}/files/{gone['id']}/download", follow_redirects=False)
        assert r.status_code == 404
        assert audits(w["url"], gone["id"], "project_file.delete") == 1
    assert _names(api, w) == []
    rows = _sql(w["url"], "SELECT count(*) FROM files WHERE project_id = :p", p=w["pid"])
    assert rows[0][0] == 3  # soft: kept for disputes


def test_only_project_files_are_deleted_here(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    item = new_item(api)
    image = add_image(api, item["id"], _png(), "shot.png")
    assert image.status_code == 201, image.text
    image_id = image.json()["images"][0]["file"]["id"]
    assert api.delete(f"{BASE}/files/{image_id}").status_code == 404
    assert api.get(f"{BASE}/files/{image_id}/download", follow_redirects=False).status_code == 302


def test_deleted_project_files_survive_the_orphan_cleanup(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    f = _uploaded(api, w)
    assert api.delete(f"{BASE}/files/{f['id']}").status_code == 204
    key = _sql(w["url"], "SELECT storage_key FROM files WHERE id = :f", f=f["id"])[0][0]
    store = Storage(os.environ.get("UPLOAD_DIR", "/tmp/uploads"))  # noqa: S108 - test stack path

    async def purge() -> dict[str, int]:
        async with open_session(DbContext.system(), job=True) as db:
            return await files_svc.purge_orphans(db, store, datetime.now(UTC))

    _job(purge())
    assert _sql(w["url"], "SELECT count(*) FROM files WHERE id = :f", f=f["id"])[0][0] == 1
    assert Path(store.path_for(key)).exists()


def test_the_list_shows_tasks_that_use_a_file(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["lead"])
    task = api.post(
        f"{BASE}/milestones/{w['m1']}/tasks",
        json={
            "title": "UI kit",
            "estimate_hours": "4.0",
            "difficulty": "EASY",
            "assignee_id": w["member"].user_id,
        },
    )
    assert task.status_code == 201, task.text
    act_as(api, w["member"])
    f = _uploaded(api, w)
    for kind in ("SCREENSHOT", "FILE"):  # one task listed once, however it uses the file
        r = api.post(
            f"{BASE}/tasks/{task.json()['id']}/evidence", json={"kind": kind, "file_id": f["id"]}
        )
        assert r.status_code == 201, r.text
    listed = api.get(f"{BASE}/projects/{w['pid']}/files").json()["items"][0]
    assert listed["links"] == [
        {"task_id": task.json()["id"], "task_title": "UI kit", "milestone_title": "Build"}
    ]


def test_paging_and_parameters(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    for n in range(3):
        _uploaded(api, w, name=f"f{n}.png")
    first = api.get(f"{BASE}/projects/{w['pid']}/files?limit=2").json()
    assert [f["name"] for f in first["items"]] == ["f2.png", "f1.png"]
    rest = api.get(f"{BASE}/projects/{w['pid']}/files?limit=2&cursor={first['next_cursor']}")
    assert [f["name"] for f in rest.json()["items"]] == ["f0.png"]
    assert rest.json()["next_cursor"] is None
    for query in ("cursor=bm9wZQ", "limit=0", "limit=101", "sort=name", "limit=2&limit=3"):
        r = api.get(f"{BASE}/projects/{w['pid']}/files?{query}")
        assert r.status_code in (400, 422), (query, r.status_code)


def test_the_daily_byte_budget(api: Api, w: dict[str, Any]) -> None:
    act_as(api, w["member"])
    key = budget_key(uuid.UUID(w["member"].user_id), datetime.now(UTC))
    store = _redis()
    try:
        store.set(key, BUDGET - 1)  # one byte left: any upload is over
        r = _upload(api, w)
        assert (r.status_code, _code(r)) == (429, "RATE_LIMITED")
        retry = int(r.headers["retry-after"])
        assert 1 <= retry <= 24 * 3600  # until midnight in Dhaka
        assert int(store.get(key) or 0) == BUDGET - 1  # nothing charged for a refusal
        store.set(key, BUDGET - 200_000)  # room for a small file
        ok = _uploaded(api, w)
        assert int(store.get(key) or 0) == BUDGET - 200_000 + ok["size_bytes"]  # settled
        bad = _upload(api, w, b"MZ\x90\x00" + b"\x00" * 100, "tool.exe")
        assert bad.status_code == 422
        assert int(store.get(key) or 0) == BUDGET - 200_000 + ok["size_bytes"]  # given back
        assert 0 < store.ttl(key) <= 26 * 3600
    finally:
        store.delete(key)
