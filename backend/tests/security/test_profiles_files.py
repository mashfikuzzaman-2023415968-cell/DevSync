"""Profiles, portfolio, evidence and file downloads over HTTP (spec §17 Phase 3, §14.9,
§14.13 row 3, §16.4: uploads, IDOR, mass assignment, injection, visibility, PII)."""

from __future__ import annotations

import io
import os
import uuid
from datetime import timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from app.core import clock
from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]

INJECTION = [
    "<script>alert(1)</script>",
    "'; DROP TABLE users; --",
    "{{7*7}}",
    "${jndi:ldap://x}",
    "\u202eevil",  # right-to-left override
]


def jpeg_with_gps(size: tuple[int, int] = (120, 80)) -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif.get_ifd(0x8825)[2] = (Fraction(23), Fraction(48), Fraction(30))
    buf = io.BytesIO()
    Image.new("RGB", size, (15, 118, 110)).save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def pdf(body: bytes = b"1 0 obj<</Type/Catalog>>endobj\n") -> bytes:
    return b"%PDF-1.7\n" + body + b"trailer<<>>\n%%EOF\n"


def upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads"))  # noqa: S108 - test stack path


def new_item(api: Api, title: str = "Clinic booking app", **kw: Any) -> dict[str, Any]:
    r = api.post("/api/v1/me/portfolio", json={"title": title, **kw})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def add_image(api: Api, item_id: str, data: bytes, name: str = "shot.jpg") -> Any:
    return api.post(
        f"/api/v1/me/portfolio/{item_id}/images", files={"file": (name, data, "image/jpeg")}
    )


def skill_ids(api: Api) -> list[str]:
    r = api.get("/api/v1/skills")
    assert r.status_code == 200, r.text
    return [s["id"] for s in r.json()]


def follow_download(api: Api, file_id: str) -> Any:
    r = api.get(f"/api/v1/files/{file_id}/download", follow_redirects=False)
    assert r.status_code == 302, r.text
    assert r.headers["cache-control"] == "no-store"
    return api.get(r.headers["location"], follow_redirects=False)


# --------------------------------------------------------------------------- profile basics


def test_developer_profile_defaults_then_autosave_patch(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.get("/api/v1/me/developer-profile")
    assert r.status_code == 200
    assert r.json()["updated_at"] is None
    r = api.patch("/api/v1/me/developer-profile", json={"headline": "  React dev  "})
    assert r.status_code == 200, r.text
    assert r.json()["headline"] == "React dev"
    r = api.patch(
        "/api/v1/me/developer-profile",
        json={"hours_per_week": 30, "github_username": "nadia-dev", "timezone": "Asia/Dhaka"},
    )
    body = r.json()
    assert (body["headline"], body["hours_per_week"], body["github_username"]) == (
        "React dev",
        30,
        "nadia-dev",
    )
    assert api.patch(
        "/api/v1/me/developer-profile", json={"github_username": None}
    ).json()["github_username"] is None  # fmt: skip


@pytest.mark.parametrize(
    "body",
    [
        {"headline": "x" * 121},
        {"bio": "x" * 2001},
        {"hours_per_week": 0},
        {"hours_per_week": 81},
        {"github_username": "-bad-"},
        {"github_username": "a" * 40},
        {"timezone": "Mars/Olympus"},
        {"visibility": "SECRET"},
        {"headline": None},
        {"user_id": str(uuid.uuid4())},
        {"id": str(uuid.uuid4())},
    ],
)
def test_developer_profile_rejects_out_of_bounds_and_unknown_fields(
    api: Api, body: dict[str, Any]
) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.patch("/api/v1/me/developer-profile", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_profile_boundaries_are_accepted(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.patch(
        "/api/v1/me/developer-profile",
        json={"headline": "x" * 120, "bio": "y" * 2000, "hours_per_week": 80},
    )
    assert r.status_code == 200, r.text
    assert api.patch("/api/v1/me/developer-profile", json={"hours_per_week": 1}).status_code == 200


@pytest.mark.parametrize("value", INJECTION)
def test_injection_corpus_is_stored_as_inert_text(api: Api, value: str) -> None:
    user = api.sign_in_as("DEVELOPER")
    r = api.patch("/api/v1/me/developer-profile", json={"bio": value, "headline": value})
    assert r.status_code == 200, r.text
    stored = r.json()["bio"]
    assert stored == value  # stored as given; the UI escapes it like any text
    public = api.get(f"/api/v1/public/developers/{user.user_id}")
    assert public.status_code == 200
    assert public.headers["content-type"].startswith("application/json")


def test_control_characters_are_removed_from_text(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.patch(
        "/api/v1/me/developer-profile", json={"headline": "a\x00b\x07c", "bio": "line\n\tok\x1b"}
    )
    assert (r.json()["headline"], r.json()["bio"]) == ("abc", "line\n\tok")


def test_skills_replace_validate_and_bound(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    ids = skill_ids(api)
    assert len(ids) == 8
    r = api.request(
        "PUT", "/api/v1/me/skills", json={"skills": [{"skill_id": ids[0], "self_level": 5}]}
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["self_level"] == 5
    for bad in (
        {"skills": [{"skill_id": ids[0], "self_level": 6}]},
        {"skills": [{"skill_id": ids[0], "self_level": 0}]},
        {"skills": [{"skill_id": ids[0], "self_level": 3}, {"skill_id": ids[0], "self_level": 2}]},
        {"skills": [{"skill_id": str(uuid.uuid4()), "self_level": 3}]},
        {"skills": [{"skill_id": ids[0], "self_level": 3, "verified": True}]},
    ):
        r = api.request("PUT", "/api/v1/me/skills", json=bad)
        assert r.status_code == 422, (bad, r.text)
    assert api.request("PUT", "/api/v1/me/skills", json={"skills": []}).json() == []


def test_client_profile_patch_and_https_only_website(api: Api) -> None:
    api.sign_in_as("CLIENT")
    r = api.patch(
        "/api/v1/me/client-profile",
        json={"organization": "Rahim Traders", "website": "https://example.com/about"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["website"] == "https://example.com/about"
    for website in (
        "http://example.com",
        "javascript:alert(1)",
        "https://",
        "https://x" + "y" * 300,
    ):
        r = api.patch("/api/v1/me/client-profile", json={"website": website})
        assert r.status_code == 422, website
    assert api.patch("/api/v1/me/client-profile", json={"website": ""}).json()["website"] is None
    assert api.patch("/api/v1/me/client-profile", json={"user_id": "x"}).status_code == 422


# --------------------------------------------------------------------------- portfolio


def test_portfolio_crud_reorder_and_limits(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    ids = skill_ids(api)
    a = new_item(api, "First", skill_ids=ids[:2], url="https://example.com/a")
    b = new_item(api, "Second")
    c = new_item(api, "Third")
    assert [a["position"], b["position"], c["position"]] == [0, 1, 2]
    r = api.request("PUT", "/api/v1/me/portfolio-order", json={"ids": [c["id"], a["id"], b["id"]]})
    assert r.status_code == 200, r.text
    assert [i["title"] for i in api.get("/api/v1/me/portfolio").json()] == [
        "Third",
        "First",
        "Second",
    ]
    # The order must list every item exactly once.
    for ids_ in ([a["id"], b["id"]], [a["id"], b["id"], c["id"], str(uuid.uuid4())]):
        assert (
            api.request("PUT", "/api/v1/me/portfolio-order", json={"ids": ids_}).status_code == 422
        )
    assert api.patch(f"/api/v1/me/portfolio/{a['id']}", json={"position": 9}).status_code == 422
    r = api.patch(f"/api/v1/me/portfolio/{a['id']}", json={"title": "Renamed", "url": None})
    assert (r.json()["title"], r.json()["url"]) == ("Renamed", None)
    assert api.delete(f"/api/v1/me/portfolio/{c['id']}").status_code == 204
    assert [i["position"] for i in api.get("/api/v1/me/portfolio").json()] == [0, 1]
    for _ in range(18):
        new_item(api, "More")
    r = api.post("/api/v1/me/portfolio", json={"title": "Twenty-first"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_STATE"


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 121},
        {"title": "ok", "url": "http://example.com"},
        {"title": "ok", "skill_ids": [str(uuid.uuid4())]},
        {"title": "ok", "skill_ids": [str(uuid.uuid4()) for _ in range(9)]},
        {"title": "ok", "user_id": str(uuid.uuid4())},
        {"title": "ok", "position": 3},
    ],
)
def test_portfolio_item_validation(api: Api, body: dict[str, Any]) -> None:
    api.sign_in_as("DEVELOPER")
    assert api.post("/api/v1/me/portfolio", json=body).status_code == 422


def test_portfolio_image_upload_strips_metadata_and_downloads(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    item = new_item(api)
    r = add_image(api, item["id"], jpeg_with_gps(), name="../../IMG_0001.HEIC")
    assert r.status_code == 201, r.text
    image = r.json()["images"][0]
    assert image["file"]["name"] == "IMG_0001.jpg"
    assert (image["file"]["width"], image["file"]["height"]) == (120, 80)
    blob = follow_download(api, image["file"]["id"])
    assert blob.status_code == 200
    accel = blob.headers["x-accel-redirect"]
    assert accel.startswith("/_protected_files/")
    assert blob.headers["content-type"] == "image/jpeg"
    assert blob.headers["content-disposition"].startswith('attachment; filename="IMG_0001.jpg"')
    stored = (upload_dir() / accel.rsplit("/", 1)[1]).read_bytes()
    clean = Image.open(io.BytesIO(stored))
    assert dict(clean.getexif()) == {}
    assert "exif" not in clean.info


def test_at_most_five_images_per_item_and_delete_reorders(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    item = new_item(api)
    for _ in range(5):
        assert add_image(api, item["id"], jpeg_with_gps((20, 20))).status_code == 201
    r = add_image(api, item["id"], jpeg_with_gps((20, 20)))
    assert r.status_code == 409
    images = api.get("/api/v1/me/portfolio").json()[0]["images"]
    r = api.delete(f"/api/v1/me/portfolio/{item['id']}/images/{images[0]['id']}")
    assert r.status_code == 200
    assert [i["position"] for i in r.json()["images"]] == [0, 1, 2, 3]
    # The removed image's file can no longer be downloaded.
    r = api.get(f"/api/v1/files/{images[0]['file']['id']}/download", follow_redirects=False)
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (jpeg_with_gps() + b"PK\x03\x04" + b"\x00" * 300, "polyglot.jpg"),
        (b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "x.svg"),
        (b"<html><script>alert(1)</script></html>", "x.jpg"),
        (pdf(), "doc.jpg"),
        (b"PK\x03\x04" + b"\x00" * 100, "archive.png"),
        (b"MZ\x90\x00" + b"\x00" * 100, "tool.jpg"),
        (b"", "empty.jpg"),
    ],
)
def test_dangerous_uploads_are_rejected(api: Api, data: bytes, name: str) -> None:
    api.sign_in_as("DEVELOPER")
    item = new_item(api)
    r = add_image(api, item["id"], data, name)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["fields"]["file"]
    assert api.get("/api/v1/me/portfolio").json()[0]["images"] == []


def test_oversized_upload_is_refused(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    item = new_item(api)
    big = b"\xff\xd8\xff" + b"\x00" * (21 * 1024 * 1024)
    r = add_image(api, item["id"], big)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_needs_a_file_field(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    item = new_item(api)
    r = api.post(f"/api/v1/me/portfolio/{item['id']}/images", data={"note": "x"})
    assert r.status_code == 422


def test_json_endpoints_keep_the_small_body_limit(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.patch("/api/v1/me/developer-profile", json={"bio": "x" * 300_000})
    assert r.status_code == 413


# --------------------------------------------------------------------------- evidence


def test_certificate_upload_pending_and_no_self_verification(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.post(
        "/api/v1/me/certificates",
        data={"title": "AWS Cloud Practitioner", "issuer": "Amazon"},
        files={"file": ("cert.pdf", pdf(), "application/pdf")},
    )
    assert r.status_code == 201, r.text
    cert = r.json()
    assert cert["status"] == "PENDING"
    assert cert["file"]["mime_type"] == "application/pdf"
    r = api.patch(f"/api/v1/me/certificates/{cert['id']}", json={"status": "VERIFIED"})
    assert r.status_code == 422
    r = api.patch(f"/api/v1/me/certificates/{cert['id']}", json={"title": "AWS CCP"})
    assert r.json()["title"] == "AWS CCP"
    blob = follow_download(api, cert["file"]["id"])
    assert blob.headers["content-type"] == "application/pdf"
    assert api.delete(f"/api/v1/me/certificates/{cert['id']}").status_code == 204
    assert api.get("/api/v1/me/certificates").json() == []


def test_certificate_rejects_scripted_pdf_and_bad_fields(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    r = api.post(
        "/api/v1/me/certificates",
        data={"title": "Cert", "issuer": "Issuer"},
        files={"file": ("c.pdf", pdf(b"1 0 obj<</OpenAction<</S/JavaScript/JS(x)>>>>endobj\n"),
                        "application/pdf")},
    )  # fmt: skip
    assert r.status_code == 422
    r = api.post(
        "/api/v1/me/certificates",
        data={"title": "   ", "issuer": "Issuer"},
        files={"file": ("c.pdf", pdf(), "application/pdf")},
    )
    assert r.status_code == 422


def test_external_review_normalises_rating_and_validates(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    ok = {"source": "Upwork", "rating": "4.8", "scale": "5", "project_date": "2026-03-01"}
    r = api.post(
        "/api/v1/me/external-reviews",
        data=ok,
        files={"file": ("review.txt", b"Great developer, 4.8/5\n", "text/plain")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["rating_norm"] == "0.960"
    assert r.json()["status"] == "PENDING"
    for bad in (
        {**ok, "rating": "6", "scale": "5"},
        {**ok, "rating": "-1"},
        {**ok, "scale": "0"},
        {**ok, "project_date": "2999-01-01"},
        {**ok, "source": ""},
        {**ok, "source": "x" * 81},
    ):
        r = api.post(
            "/api/v1/me/external-reviews",
            data=bad,
            files={"file": ("r.txt", b"text", "text/plain")},
        )
        assert r.status_code == 422, (bad, r.text)
    review_id = api.get("/api/v1/me/external-reviews").json()[0]["id"]
    assert api.delete(f"/api/v1/me/external-reviews/{review_id}").status_code == 204


# --------------------------------------------------------------------------- IDOR


def test_other_users_objects_are_not_found(api: Api, api2: Api) -> None:
    api.sign_in_as("DEVELOPER")
    item = new_item(api)
    image = add_image(api, item["id"], jpeg_with_gps()).json()["images"][0]
    cert = api.post(
        "/api/v1/me/certificates",
        data={"title": "Cert", "issuer": "Issuer"},
        files={"file": ("c.pdf", pdf(), "application/pdf")},
    ).json()
    api2.sign_in_as("DEVELOPER")
    assert api2.patch(f"/api/v1/me/portfolio/{item['id']}", json={"title": "x"}).status_code == 404
    assert api2.delete(f"/api/v1/me/portfolio/{item['id']}").status_code == 404
    assert add_image(api2, item["id"], jpeg_with_gps()).status_code == 404
    assert api2.delete(f"/api/v1/me/portfolio/{item['id']}/images/{image['id']}").status_code == 404
    assert (
        api2.patch(f"/api/v1/me/certificates/{cert['id']}", json={"title": "x"}).status_code == 404
    )
    assert api2.delete(f"/api/v1/me/certificates/{cert['id']}").status_code == 404
    # Certificates are private: only the owner (and admins) may download them.
    r = api2.get(f"/api/v1/files/{cert['file']['id']}/download", follow_redirects=False)
    assert r.status_code == 404
    order = api2.request("PUT", "/api/v1/me/portfolio-order", json={"ids": [item["id"]]})
    assert order.status_code == 422
    # Nothing changed for the owner.
    assert api.get("/api/v1/me/portfolio").json()[0]["title"] == "Clinic booking app"


# --------------------------------------------------------------------------- signed URLs


def test_signed_url_expires_and_tampering_is_refused(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    api.sign_in_as("DEVELOPER")
    item = new_item(api)
    file_id = add_image(api, item["id"], jpeg_with_gps()).json()["images"][0]["file"]["id"]
    r = api.get(f"/api/v1/files/{file_id}/download", follow_redirects=False)
    url = r.headers["location"]
    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert api.get(url, follow_redirects=False).status_code == 200
    for field, value in (("t", "text/html"), ("n", "x.html"), ("e", str(int(query["e"]) + 600)),
                         ("s", query["s"][:-2] + "AA")):  # fmt: skip
        params = {**query, field: value}
        assert api.get(parts.path, params=params).status_code == 404, field
    other_key = f"/api/v1/files/blob/{uuid.uuid4()}"
    assert api.get(other_key, params=query).status_code == 404
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(minutes=5, seconds=5))
    monkeypatch.setattr(clock, "_clock", later)
    assert api.get(url, follow_redirects=False).status_code == 404
    assert api.get(f"/api/v1/files/blob/not-a-uuid?{parts.query}").status_code == 422


# --------------------------------------------------------------------------- public profile


def _profile_with_image(api: Api, visibility: str) -> tuple[str, str]:
    user = api.sign_in_as("DEVELOPER")
    r = api.patch(
        "/api/v1/me/developer-profile", json={"headline": "Visible?", "visibility": visibility}
    )
    assert r.status_code == 200, r.text
    assert r.json()["visibility"] == visibility
    # A second change of visibility alone (the autosave case) works too.
    again = api.patch("/api/v1/me/developer-profile", json={"visibility": visibility})
    assert again.status_code == 200, again.text
    item = new_item(api)
    file_id = add_image(api, item["id"], jpeg_with_gps()).json()["images"][0]["file"]["id"]
    return user.user_id, file_id


def test_public_profile_has_no_pii_and_images_are_downloadable(api: Api, api2: Api) -> None:
    user_id, file_id = _profile_with_image(api, "PUBLIC")
    r = api2.get(f"/api/v1/public/developers/{user_id}")
    assert r.status_code == 200, r.text
    text = r.text
    body = r.json()
    assert body["headline"] == "Visible?"
    assert body["portfolio"][0]["image_ids"] == [file_id]
    for secret in ("email", "phone", "@example.com", "+88017", "password"):
        assert secret not in text
    assert follow_download(api2, file_id).status_code == 200  # anonymous visitor


def test_clients_only_profile_is_hidden_from_anonymous_and_developers(api: Api, api2: Api) -> None:
    user_id, file_id = _profile_with_image(api, "CLIENTS_ONLY")
    assert api2.get(f"/api/v1/public/developers/{user_id}").status_code == 404
    assert api2.get(f"/api/v1/files/{file_id}/download", follow_redirects=False).status_code == 404
    api2.sign_in_as("DEVELOPER")
    assert api2.get(f"/api/v1/developers/{user_id}").status_code == 404
    api2.client.cookies.clear()
    api2.sign_in_as("CLIENT")
    assert api2.get(f"/api/v1/developers/{user_id}").status_code == 200
    assert api2.get(f"/api/v1/public/developers/{user_id}").status_code == 200
    assert api2.get(f"/api/v1/files/{file_id}/download", follow_redirects=False).status_code == 302
    # The developer always sees their own profile.
    assert api.get(f"/api/v1/developers/{user_id}").status_code == 200


def test_unknown_or_non_developer_profiles_are_not_found(api: Api) -> None:
    client = api.sign_in_as("CLIENT")
    assert api.get(f"/api/v1/public/developers/{uuid.uuid4()}").status_code == 404
    assert api.get(f"/api/v1/public/developers/{client.user_id}").status_code == 404
    assert api.get("/api/v1/public/developers/not-a-uuid").status_code == 422
