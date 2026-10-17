"""Admin 2FA, recovery codes, step-up and admin-area hiding (spec §14.4, §14.17)."""

from __future__ import annotations

import pyotp
import pytest

from tests.helpers import Api, wait_for_next_totp_window

pytestmark = [pytest.mark.security, pytest.mark.api]


def password_step(
    api: Api, email: str, password: str, captcha: str | None = "test-bypass"
) -> object:
    body: dict[str, object] = {"email": email, "password": password}
    if captcha:
        body["captcha"] = captcha
    return api.post("/api/v1/auth/login", json=body)


def test_admin_login_always_needs_captcha(api: Api) -> None:
    admin = api.seed("ADMIN")
    r = password_step(api, admin.email, admin.password, captcha=None)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CAPTCHA_FAILED"


def test_admin_password_alone_gives_no_session(api: Api) -> None:
    admin = api.seed("ADMIN")
    r = password_step(api, admin.email, admin.password)
    assert r.status_code == 200
    assert r.json()["status"] == "TOTP_REQUIRED"
    assert "__Host-ds_session" not in api.client.cookies
    assert api.get("/api/v1/admin/session").status_code == 404


def test_admin_totp_success_and_wrong_code(api: Api) -> None:
    admin = api.seed("ADMIN")
    pre = password_step(api, admin.email, admin.password).json()["pre_auth"]
    bad = api.post("/api/v1/auth/login/totp", json={"pre_auth": pre, "code": "000000"})
    assert bad.status_code == 401
    code = pyotp.TOTP(admin.totp_secret or "").now()
    ok = api.post("/api/v1/auth/login/totp", json={"pre_auth": pre, "code": code})
    assert ok.status_code == 200
    assert ok.json()["redirect_to"] == "/admin"
    assert api.get("/api/v1/admin/session").json()["totp_verified"] is True


def test_totp_code_cannot_be_replayed(api: Api, api2: Api) -> None:
    admin = api.seed("ADMIN")
    code = pyotp.TOTP(admin.totp_secret or "").now()
    pre1 = password_step(api, admin.email, admin.password).json()["pre_auth"]
    assert (
        api.post("/api/v1/auth/login/totp", json={"pre_auth": pre1, "code": code}).status_code
        == 200
    )
    pre2 = password_step(api2, admin.email, admin.password).json()["pre_auth"]
    assert (
        api2.post("/api/v1/auth/login/totp", json={"pre_auth": pre2, "code": code}).status_code
        == 401
    )


def test_recovery_code_works_once(api: Api, api2: Api) -> None:
    admin = api.seed("ADMIN")
    code = admin.recovery_codes[0].upper()  # typed loosely
    pre = password_step(api, admin.email, admin.password).json()["pre_auth"]
    assert (
        api.post(
            "/api/v1/auth/login/totp", json={"pre_auth": pre, "recovery_code": code}
        ).status_code
        == 200
    )
    pre2 = password_step(api2, admin.email, admin.password).json()["pre_auth"]
    assert (
        api2.post(
            "/api/v1/auth/login/totp", json={"pre_auth": pre2, "recovery_code": code}
        ).status_code
        == 401
    )


def test_pre_auth_token_is_single_use(api: Api) -> None:
    admin = api.seed("ADMIN")
    pre = password_step(api, admin.email, admin.password).json()["pre_auth"]
    code = pyotp.TOTP(admin.totp_secret or "").now()
    assert (
        api.post("/api/v1/auth/login/totp", json={"pre_auth": pre, "code": code}).status_code == 200
    )
    assert (
        api.post("/api/v1/auth/login/totp", json={"pre_auth": pre, "code": code}).status_code == 401
    )


def test_admin_without_totp_must_set_it_up(api: Api) -> None:
    admin = api.seed("ADMIN", with_totp=False)
    r = password_step(api, admin.email, admin.password)
    assert r.json() == {
        "status": "TOTP_SETUP_REQUIRED",
        "redirect_to": "/admin/setup-2fa",
        "pre_auth": None,
    }
    assert api.get("/api/v1/admin/session").status_code == 404  # no admin powers yet
    setup = api.post("/api/v1/auth/totp/setup")
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["provisioning_uri"].startswith("otpauth://totp/")
    assert api.post("/api/v1/auth/totp/confirm", json={"code": "000000"}).status_code == 400
    confirm = api.post("/api/v1/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    assert confirm.status_code == 200
    assert len(confirm.json()["recovery_codes"]) == 10
    assert api.get("/api/v1/admin/session").status_code == 200


def test_step_up_required_for_sensitive_actions(api: Api) -> None:
    admin = api.sign_in_as("ADMIN")
    r = api.post("/api/v1/auth/recovery-codes/regenerate")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    assert api.post("/api/v1/auth/step-up", json={"code": "000000"}).status_code == 401
    code = wait_for_next_totp_window(admin.totp_secret or "")  # login used the current step
    assert api.post("/api/v1/auth/step-up", json={"code": code}).status_code == 204
    assert api.get("/api/v1/admin/session").json()["step_up_active"] is True
    assert api.post("/api/v1/auth/recovery-codes/regenerate").status_code == 200


@pytest.mark.parametrize("role", ["CLIENT", "DEVELOPER"])
def test_admin_area_is_404_for_other_roles(api: Api, role: str) -> None:
    api.sign_in_as(role)
    for method, path in (
        ("GET", "/api/v1/admin/session"),
        ("POST", "/api/v1/auth/totp/setup"),
        ("POST", "/api/v1/auth/recovery-codes/regenerate"),
        ("POST", "/api/v1/auth/step-up"),
    ):
        kw = {"json": {"code": "123456"}} if path.endswith("step-up") else {}
        assert api.request(method, path, **kw).status_code == 404, path


def test_admin_area_is_404_for_anonymous(api: Api) -> None:
    assert api.get("/api/v1/admin/session").status_code == 404
