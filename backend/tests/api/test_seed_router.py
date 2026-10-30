"""The test-only seed router (`/__test__/seed/user`) stays dependable as test users pile up."""

from __future__ import annotations

import pytest

from tests.helpers import STRONG_PASSWORD, Api, unique_email, unique_phone

pytestmark = pytest.mark.api


def _seed(api: Api, phone: str | None) -> dict[str, object]:
    r = api.post(
        "/api/v1/__test__/seed/user",
        json={
            "role": "DEVELOPER",
            "email": unique_email("dev"),
            "phone": phone,
            "password": STRONG_PASSWORD,
            "verified": True,
            "with_totp": False,
        },
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_a_taken_phone_is_swapped_for_a_free_one(api: Api) -> None:
    phone = unique_phone()
    first = _seed(api, phone)
    second = _seed(api, phone)  # was a 500 (unique violation) when random numbers collided
    assert first["phone"] == phone
    assert second["phone"] != phone
    assert str(second["phone"]).startswith("+88017")
    assert len(str(second["phone"])) == len(phone)


def test_no_phone_stays_no_phone(api: Api) -> None:
    assert _seed(api, None)["phone"] is None
