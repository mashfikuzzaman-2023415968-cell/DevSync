"""Authorization policies and session timing rules (spec §2.2, §14.4, §14.5)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.authz import Principal, authorize, policy, registered_actions
from app.core.errors import AuthError, ErrorCode, ForbiddenError, NotFoundError
from app.core.sessions import SessionData, SessionPolicy
from tests.conftest import make_settings

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 17, 6, 0, tzinfo=UTC)


def principal(role: str = "CLIENT", status: str = "ACTIVE", totp: bool = False) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        role=role,
        status=status,
        session_id=uuid.uuid4(),
        totp_verified=totp,
        step_up_until=None,
    )


def test_unknown_action_is_denied() -> None:
    with pytest.raises(ForbiddenError):
        authorize(principal(), "project.delete-everything")


def test_anonymous_gets_401_and_404_for_admin() -> None:
    with pytest.raises(AuthError):
        authorize(None, "account.read")
    with pytest.raises(NotFoundError):
        authorize(None, "admin.access")
    with pytest.raises(NotFoundError):
        authorize(None, "totp.manage")


@pytest.mark.parametrize(
    ("p", "outcome"),
    [
        (principal("ADMIN", totp=True), None),
        (principal("ADMIN", totp=False), NotFoundError),
        (principal("CLIENT"), NotFoundError),
        (principal("DEVELOPER"), NotFoundError),
        (principal("ADMIN", status="SUSPENDED", totp=True), NotFoundError),
    ],
)
def test_admin_area_is_hidden(p: Principal, outcome: type[Exception] | None) -> None:
    if outcome is None:
        authorize(p, "admin.access")
    else:
        with pytest.raises(outcome):
            authorize(p, "admin.access")


def test_pending_users_can_verify_but_not_update() -> None:
    p = principal(status="PENDING")
    authorize(p, "account.read")
    authorize(p, "account.verify")
    with pytest.raises(ForbiddenError) as exc:
        authorize(p, "account.update")
    assert exc.value.code is ErrorCode.VERIFICATION_REQUIRED


def test_suspended_users_are_unauthenticated() -> None:
    for action in ("account.read", "account.verify", "account.update", "session.manage"):
        with pytest.raises(AuthError):
            authorize(principal(status="SUSPENDED"), action)


def test_sessions_of_others_are_not_found() -> None:
    p = principal()
    authorize(p, "session.manage", SimpleNamespace(user_id=p.user_id))
    with pytest.raises(NotFoundError):
        authorize(p, "session.manage", SimpleNamespace(user_id=uuid.uuid4()))


def test_totp_management_only_for_admins() -> None:
    authorize(principal("ADMIN"), "totp.manage")
    with pytest.raises(NotFoundError):
        authorize(principal("DEVELOPER"), "totp.manage")


def test_policies_are_registered_once() -> None:
    assert {"account.read", "admin.access", "session.manage"} <= registered_actions()
    with pytest.raises(ValueError, match="duplicate"):
        policy("account.read")(lambda _p, _r: None)


def test_step_up_window() -> None:
    p = Principal(uuid.uuid4(), "ADMIN", "ACTIVE", uuid.uuid4(), True, NOW + timedelta(minutes=5))
    assert p.has_step_up(NOW)
    assert not p.has_step_up(NOW + timedelta(minutes=6))
    assert not principal("ADMIN").has_step_up(NOW)


def data(**kw: object) -> SessionData:
    base: dict[str, object] = {
        "session_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "role": "CLIENT",
        "status": "ACTIVE",
        "csrf_secret": b"s" * 32,
        "created_at": NOW,
        "last_seen_at": NOW,
        "rotated_at": NOW,
        "expires_at": NOW + timedelta(days=7),
        "step_up_until": None,
        "totp_verified": False,
        "last_db_write": NOW,
    }
    base.update(kw)
    return SessionData(**base)  # type: ignore[arg-type]


def test_session_json_round_trip() -> None:
    d = data(step_up_until=NOW + timedelta(minutes=10), totp_verified=True)
    assert SessionData.from_json(d.to_json()) == d


def test_rotation_idle_and_absolute_expiry() -> None:
    pol = SessionPolicy(make_settings())
    d = data()
    assert not pol.needs_rotation(d, NOW + timedelta(minutes=14))
    assert pol.needs_rotation(d, NOW + timedelta(minutes=15))
    assert not pol.is_expired(d, NOW + timedelta(minutes=29))
    assert pol.is_expired(d, NOW + timedelta(minutes=30))  # idle
    active = data(last_seen_at=NOW + timedelta(days=7))
    assert pol.is_expired(active, NOW + timedelta(days=7))  # absolute


def test_admin_idle_is_shorter() -> None:
    pol = SessionPolicy(make_settings())
    admin = data(role="ADMIN")
    assert not pol.is_expired(admin, NOW + timedelta(minutes=14))
    assert pol.is_expired(admin, NOW + timedelta(minutes=15))


def test_redis_ttl_never_exceeds_remaining_life() -> None:
    pol = SessionPolicy(make_settings())
    near_end = data(expires_at=NOW + timedelta(minutes=5))
    assert pol.redis_ttl(near_end, NOW) == 300
    assert pol.redis_ttl(data(), NOW) == 30 * 60
    assert pol.redis_ttl(data(expires_at=NOW), NOW) == 1
