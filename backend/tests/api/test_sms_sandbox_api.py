"""The developer SMS inbox over HTTP: a real sign-up lands its code there, and it works."""

from __future__ import annotations

import pytest

from tests.helpers import STRONG_PASSWORD, Api, unique_email, unique_phone
from tests.security.test_registration_verification import register

pytestmark = pytest.mark.api

INBOX = "/api/v1/dev-sandbox/sms"


def test_a_signup_code_appears_and_is_the_one_that_works(api: Api) -> None:
    email, phone = unique_email(), unique_phone()
    assert register(api, email, phone).status_code == 202  # type: ignore[attr-defined]
    login = api.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert login.status_code == 200
    body = api.get(INBOX, params={"phone": phone}).json()
    assert len(body["messages"]) == 1
    message = body["messages"][0]
    assert message["to"] == phone
    assert message["text"] == f"Your DevSync code is {message['code']}"
    assert body["newest_code"] == message["code"]
    # The code shown in the inbox is accepted by the real verification endpoint.
    assert api.post("/api/v1/auth/otp/verify", json={"code": message["code"]}).status_code == 204


def test_the_phone_filter_only_shows_that_number(api: Api) -> None:
    mine, other = unique_phone(), unique_phone()
    register(api, unique_email(), mine)
    register(api, unique_email(), other)
    for number in (mine, other):
        messages = api.get(INBOX, params={"phone": number}).json()["messages"]
        assert [m["to"] for m in messages] == [number]


def test_clear_empties_everything(api: Api) -> None:
    register(api, unique_email(), unique_phone())
    assert api.get(INBOX).json()["messages"]
    assert api.delete(INBOX).status_code == 204
    assert api.get(INBOX).json() == {"messages": [], "newest_code": None}


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": "ten"},
        {"phone": "not a phone"},
        {"phone": "+" + "1" * 30},
        {"phone": "+88017'; DROP TABLE users;--"},
    ],
)
def test_bad_query_values_are_refused(api: Api, params: dict[str, object]) -> None:
    assert api.get(INBOX, params=params).status_code == 422
