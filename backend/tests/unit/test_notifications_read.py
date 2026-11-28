"""The notifications read API's shapes (D122): `app/api/v1/notifications.py` serves
`app/schemas/notifications.py`; the behaviour over HTTP (own rows only, unread count, read-all,
cursor) is `test_notifications_are_your_own` in `tests/security/test_team_api.py`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.notifications import router
from app.schemas.notifications import EX_NOTIFICATION, NotificationOut, ReadAll, UnreadCount

pytestmark = pytest.mark.unit


def test_example_matches_the_schema() -> None:
    n = NotificationOut.model_validate(EX_NOTIFICATION)
    assert n.link_path == "/dev"
    assert n.read_at is None


def test_counts_are_integers() -> None:
    assert UnreadCount(unread=3).unread == 3
    assert ReadAll(marked=0).marked == 0
    with pytest.raises(ValidationError):
        UnreadCount(unread="many")  # type: ignore[arg-type]


def test_routes() -> None:
    paths = {(next(iter(r.methods)), r.path) for r in router.routes}  # type: ignore[attr-defined]
    assert paths == {
        ("GET", "/notifications"),
        ("GET", "/notifications/unread-count"),
        ("POST", "/notifications/{notification_id}/read"),
        ("POST", "/notifications/read-all"),
        ("GET", "/notifications/stream"),
        ("GET", "/notification-preferences"),
        ("PUT", "/notification-preferences"),
    }
