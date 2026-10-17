"""Registration, phone OTP and email verification (spec §14.4, §16.4 Auth)."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from app.core import clock
from tests.helpers import STRONG_PASSWORD, Api, unique_email, unique_phone

pytestmark = [pytest.mark.security, pytest.mark.api]


def register(api: Api, email_value: str, phone_value: str, **overrides: object) -> object:
    body: dict[str, object] = {
        "display_name": "Nadia Rahman",
        "email": email_value,
        "phone": phone_value,
        "password": STRONG_PASSWORD,
        "role": "DEVELOPER",
        "accept_terms": True,
        "captcha": "test-bypass",
    }
    body.update(overrides)
    return api.post("/api/v1/auth/register", json=body)


def otp_for(api: Api, phone: str) -> str:
    message = api.get("/api/v1/__test__/sms", params={"phone": phone}).json()["message"]
    assert message, "no SMS recorded"
    return str(message).rsplit(" ", 1)[-1]


def email_token(api: Api, email: str, template: str = "verify_email") -> str:
    link = api.get(
        "/api/v1/__test__/email-link", params={"to": email, "template": template}
    ).json()["link"]
    assert link
    return parse_qs(urlparse(link).query)["token"][0]


def test_full_registration_and_verification(api: Api) -> None:
    email, phone = unique_email(), unique_phone()
    r = register(api, email, phone)
    assert r.status_code == 202
    assert r.json() == {"message": "Check your email and phone to verify your account."}

    login = api.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert login.status_code == 200
    assert login.json()["redirect_to"] == "/verify"  # PENDING users go to verification
    me = api.get("/api/v1/me").json()
    assert me["status"] == "PENDING"
    assert (me["email_verified"], me["phone_verified"]) == (False, False)

    # PENDING users can't use the rest of the account yet.
    assert api.patch("/api/v1/me", json={"display_name": "N"}).status_code == 403

    assert (
        api.post("/api/v1/auth/otp/verify", json={"code": otp_for(api, phone)}).status_code == 204
    )
    assert (
        api.post("/api/v1/auth/email/verify", json={"token": email_token(api, email)}).status_code
        == 204
    )
    me = api.get("/api/v1/me").json()
    assert me["status"] == "ACTIVE"
    # The same session can now use active-only actions without signing in again.
    assert api.patch("/api/v1/me", json={"display_name": "Nadia R."}).status_code == 200
    assert me["email_verified"]
    assert me["phone_verified"]
    assert "password_hash" not in me


def test_duplicate_registration_is_uniform_and_notifies_owner(api: Api) -> None:
    email, phone = unique_email(), unique_phone()
    first = register(api, email, phone)
    second = register(api, email, unique_phone())
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    link = api.get(
        "/api/v1/__test__/email-link", params={"to": email, "template": "account_exists"}
    ).json()["link"]
    assert link
    assert link.endswith("/login")


def test_duplicate_phone_is_uniform(api: Api) -> None:
    phone = unique_phone()
    assert register(api, unique_email(), phone).status_code == 202
    assert register(api, unique_email(), phone).status_code == 202


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"password": "short"}, "password"),
        ({"password": "password1234"}, "password"),
        ({"phone": "01712345678"}, "phone"),
        ({"email": "not-an-email"}, "email"),
        ({"role": "ADMIN"}, "role"),
        ({"accept_terms": False}, "accept_terms"),
        ({"display_name": ""}, "display_name"),
    ],
)
def test_registration_validation(api: Api, override: dict[str, object], field: str) -> None:
    r = register(api, unique_email(), unique_phone(), **override)
    assert r.status_code == 422
    assert field in r.json()["error"]["fields"]


@pytest.mark.parametrize("field", ["status", "email_verified_at", "role_admin", "id"])
def test_mass_assignment_is_rejected(api: Api, field: str) -> None:
    r = register(api, unique_email(), unique_phone(), **{field: "ACTIVE"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "bot",
    [{"captcha": None}, {"captcha": "forged"}, {"website": "http://spam"}, {"captcha": ""}],
)
def test_registration_requires_captcha_and_empty_honeypot(api: Api, bot: dict[str, object]) -> None:
    r = register(api, unique_email(), unique_phone(), **bot)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CAPTCHA_FAILED"


def _pending_user(api: Api) -> tuple[str, str]:
    email, phone = unique_email(), unique_phone()
    assert register(api, email, phone).status_code == 202
    assert (
        api.post(
            "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
        ).status_code
        == 200
    )
    return email, phone


def test_otp_attempt_limit(api: Api) -> None:
    _email, phone = _pending_user(api)
    code = otp_for(api, phone)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert api.post("/api/v1/auth/otp/verify", json={"code": wrong}).status_code == 400
    # After 5 wrong attempts even the right code is refused.
    assert api.post("/api/v1/auth/otp/verify", json={"code": code}).status_code in {400, 429}


def test_otp_expiry(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    _email, phone = _pending_user(api)
    code = otp_for(api, phone)
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(minutes=6))
    monkeypatch.setattr(clock, "_clock", later)
    r = api.post("/api/v1/auth/otp/verify", json={"code": code})
    assert r.status_code in {400, 401}  # expired code (or idle session) is refused


def test_otp_resend_cooldown(api: Api) -> None:
    _pending_user(api)
    assert api.post("/api/v1/auth/otp/send").status_code == 429  # just sent at registration
    r = api.post("/api/v1/auth/otp/send")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_already_verified_is_409(api: Api) -> None:
    user = api.sign_in_as("DEVELOPER")
    assert user.user_id
    assert api.post("/api/v1/auth/otp/verify", json={"code": "123456"}).status_code == 409
    assert api.post("/api/v1/auth/email/resend").status_code == 409


def test_email_token_single_use_and_invalid(api: Api) -> None:
    email, _phone = _pending_user(api)
    token = email_token(api, email)
    assert api.post("/api/v1/auth/email/verify", json={"token": token}).status_code == 204
    assert api.post("/api/v1/auth/email/verify", json={"token": token}).status_code == 400
    assert api.post("/api/v1/auth/email/verify", json={"token": "x" * 43}).status_code == 400


def test_resend_invalidates_previous_link(api: Api) -> None:
    email, _phone = _pending_user(api)
    old = email_token(api, email)
    assert api.post("/api/v1/auth/email/resend").status_code == 204
    new = email_token(api, email)
    assert old != new
    assert api.post("/api/v1/auth/email/verify", json={"token": old}).status_code == 400
    assert api.post("/api/v1/auth/email/verify", json={"token": new}).status_code == 204


def test_registration_rate_limit(api: Api) -> None:
    statuses = [register(api, unique_email(), unique_phone()).status_code for _ in range(6)]
    assert statuses[:5] == [202] * 5
    assert statuses[5] == 429
