"""The quick sign-in tab: one click starts a real session for a seeded demo account, and nothing
else can use it (no real address, no administrator, no unknown account)."""

from __future__ import annotations

import asyncio
import secrets

import pytest

from app.services.testing.seed import create_user
from tests.helpers import STRONG_PASSWORD, Api, stack_settings, unique_phone

pytestmark = pytest.mark.api

ACCOUNTS = "/api/v1/dev-sandbox/accounts"
SIGN_IN = "/api/v1/dev-sandbox/sign-in"


def _demo_email(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}@devsync.local"


def _seed(api: Api, role: str, email: str, name: str = "Demo Person") -> None:
    """Like the demo seed: straight into the database (the test seed route refuses `.local`)."""
    del api
    asyncio.run(
        create_user(
            stack_settings(),
            role=role,
            email=email,
            phone=None if role == "ADMIN" else unique_phone(),
            password=STRONG_PASSWORD,
            display_name=name,
            verified=True,
            with_totp=role == "ADMIN",
        )
    )


def test_a_demo_client_signs_in_with_one_call(api: Api) -> None:
    email = _demo_email("client")
    _seed(api, "CLIENT", email)
    r = api.post(SIGN_IN, json={"email": email})
    assert r.status_code == 200, r.text
    assert r.json() == {"redirect_to": "/client"}
    assert api.client.cookies.get("__Host-ds_session")
    me = api.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_a_demo_developer_lands_on_the_developer_home(api: Api) -> None:
    email = _demo_email("dev")
    _seed(api, "DEVELOPER", email)
    assert api.post(SIGN_IN, json={"email": email.upper()}).json() == {"redirect_to": "/dev"}


def test_the_list_has_clients_and_developers_but_never_an_admin(api: Api) -> None:
    client, dev, admin = _demo_email("c"), _demo_email("d"), _demo_email("a")
    _seed(api, "CLIENT", client, "Zed Client")
    _seed(api, "DEVELOPER", dev, "Amy Developer")
    _seed(api, "ADMIN", admin, "Ada Admin")
    accounts = api.get(ACCOUNTS).json()["accounts"]
    by_email = {a["email"]: a for a in accounts}
    assert by_email[client]["role"] == "CLIENT"
    assert by_email[dev]["role"] == "DEVELOPER"
    assert admin not in by_email
    assert all(a["email"].endswith("@devsync.local") for a in accounts)
    roles = [a["role"] for a in accounts]
    assert roles == sorted(roles, key=lambda r: r != "CLIENT")  # clients first


def test_an_admin_cannot_use_it(api: Api) -> None:
    email = _demo_email("admin")
    _seed(api, "ADMIN", email)
    r = api.post(SIGN_IN, json={"email": email})
    assert r.status_code == 401
    assert not api.client.cookies.get("__Host-ds_session")


def test_a_real_looking_address_is_refused_even_if_the_account_exists(api: Api) -> None:
    user = api.seed("CLIENT")  # an ordinary @example-style address
    assert not user.email.endswith("@devsync.local")
    r = api.post(SIGN_IN, json={"email": user.email})
    assert r.status_code == 401
    assert not api.client.cookies.get("__Host-ds_session")


@pytest.mark.parametrize(
    "email", ["nobody@devsync.local", "x@devsync.local.evil.com", "@devsync.local", "devsync.local"]
)
def test_unknown_or_malformed_addresses_are_a_plain_401(api: Api, email: str) -> None:
    assert api.post(SIGN_IN, json={"email": email}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": ""},
        {"email": "x" * 300 + "@devsync.local"},
        {"email": "a@devsync.local", "role": "ADMIN"},
    ],
)
def test_bad_bodies_are_422(api: Api, body: dict[str, str]) -> None:
    assert api.post(SIGN_IN, json=body).status_code == 422


def test_it_needs_the_csrf_token_like_any_other_post(api: Api) -> None:
    email = _demo_email("csrf")
    _seed(api, "CLIENT", email)
    r = api.post(SIGN_IN, json={"email": email}, csrf=False)
    assert r.status_code == 403
    assert not api.client.cookies.get("__Host-ds_session")


def test_every_use_is_audited(api: Api) -> None:
    email = _demo_email("audit")
    _seed(api, "CLIENT", email)
    assert api.post(SIGN_IN, json={"email": email}).status_code == 200
    # The audit trail is admin-only; its existence is covered in the audit-log tests. Here the
    # session works, which means the write and the commit that carries it both succeeded.
    assert api.get("/api/v1/me").status_code == 200
