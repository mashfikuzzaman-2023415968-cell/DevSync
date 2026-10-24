"""PATCH /me/external-reviews/{id}: owner only, PENDING only, no mass assignment (§10.2, §14.5)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import update

from app.db.context import DbContext
from app.db.session import open_session
from app.models.profiles import ExternalReview, VerificationStatus
from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]

OK = {"source": "Upwork", "rating": "4.8", "scale": "5", "project_date": "2026-03-01"}


def _add(api: Api, **over: Any) -> dict[str, Any]:
    r = api.post(
        "/api/v1/me/external-reviews",
        data={**OK, **over},
        files={"file": ("review.txt", b"Great developer, 4.8/5\n", "text/plain")},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def _path(review_id: str) -> str:
    return f"/api/v1/me/external-reviews/{review_id}"


def test_owner_can_correct_a_pending_review(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    review = _add(api)
    r = api.patch(_path(review["id"]), json={"source": "Fiverr"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "Fiverr"
    assert r.json()["rating_norm"] == review["rating_norm"]  # untouched
    assert r.json()["file"]["id"] == review["file"]["id"]  # evidence stays
    assert r.json()["status"] == "PENDING"
    # The rating is re-normalised from the platform's own scale.
    r = api.patch(_path(review["id"]), json={"rating": "9", "scale": 10})
    assert r.json()["rating_norm"] == "0.900"
    r = api.patch(_path(review["id"]), json={"project_date": "2026-01-15"})
    assert r.json()["project_date"] == "2026-01-15"
    assert api.get("/api/v1/me/external-reviews").json()[0]["source"] == "Fiverr"


@pytest.mark.parametrize(
    "body",
    [
        {"status": "VERIFIED"},  # mass assignment: admins decide this
        {"reason": "please accept"},
        {"developer_id": "00000000-0000-4000-8000-000000000001"},
        {"rating_norm": "1.000"},
        {"evidence_file_id": "00000000-0000-4000-8000-000000000002"},
        {"reviewed_by": "00000000-0000-4000-8000-000000000003"},
        {"id": "00000000-0000-4000-8000-000000000004"},
        {},  # nothing to change
        {"rating": "4"},  # a rating without its scale
        {"scale": 5},
        {"rating": "6", "scale": 5},  # above the scale
        {"rating": "-1", "scale": 5},
        {"scale": 0, "rating": "0"},
        {"source": ""},
        {"source": "x" * 81},
        {"project_date": "2999-01-01"},  # in the future
        {"project_date": "not a date"},
        {"source": None},  # null is not "leave it alone" here
    ],
)
def test_refused_bodies_change_nothing(api: Api, body: dict[str, Any]) -> None:
    api.sign_in_as("DEVELOPER")
    review = _add(api)
    r = api.patch(_path(review["id"]), json=body)
    assert r.status_code == 422, (body, r.text)
    assert api.get("/api/v1/me/external-reviews").json()[0] == review


async def test_a_verified_review_is_frozen(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    review = _add(api)
    # Only an admin or SYSTEM may set a verification status (migration 0004's trigger), and
    # Phase 3 has no admin console yet, so the test marks it the way that job will.
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(ExternalReview)
            .where(ExternalReview.id == uuid.UUID(str(review["id"])))
            .values(status=VerificationStatus.VERIFIED)
        )
        await db.commit()
    r = api.patch(_path(review["id"]), json={"source": "Fiverr"})
    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "INVALID_STATE"
    assert body["current_state"] == "VERIFIED"
    assert body["allowed_actions"] == ["delete"]
    assert api.get("/api/v1/me/external-reviews").json()[0]["source"] == "Upwork"


def test_another_developer_and_a_client_get_404_or_403(api: Api, api2: Api) -> None:
    api.sign_in_as("DEVELOPER")
    review = _add(api)
    api2.sign_in_as("DEVELOPER")
    assert api2.patch(_path(review["id"]), json={"source": "Fiverr"}).status_code == 404
    api2.client.cookies.clear()
    api2.sign_in_as("CLIENT")
    assert api2.patch(_path(review["id"]), json={"source": "Fiverr"}).status_code == 403
    assert api.get("/api/v1/me/external-reviews").json()[0]["source"] == "Upwork"


def test_unknown_id_and_anonymous(api: Api) -> None:
    missing = _path(str(uuid.uuid4()))
    assert api.patch(missing, json={"source": "Fiverr"}).status_code == 401
    api.sign_in_as("DEVELOPER")
    assert api.patch(missing, json={"source": "Fiverr"}).status_code == 404
    assert api.patch(_path("not-a-uuid"), json={"source": "Fiverr"}).status_code == 422
