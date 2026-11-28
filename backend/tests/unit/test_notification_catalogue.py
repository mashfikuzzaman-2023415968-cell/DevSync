"""The notification catalogue and the writers' guards (spec §12; D162, D163).

Covered: every type has exactly one §12 category and every category a label and defaults
(mentions email off, D153; rows without an email can't default it on); every email template is
either one of the six account templates or mapped to a type, and every mapped template exists;
every notification kind the code passes (string literals and module constants) is in the
catalogue; `notify` refuses a kind outside it before touching the database; the outbox refuses
an unknown template and a non-account template that doesn't name its recipient.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import pytest

from app.core.notification_types import (
    ACCOUNT_TEMPLATES,
    CATEGORIES,
    CATEGORY_OF,
    TEMPLATE_TYPE,
    Category,
    NotificationType,
    category,
)
from app.integrations.email import TEMPLATES
from app.services import notifications, outbox

pytestmark = pytest.mark.unit
APP = Path(__file__).resolve().parents[2] / "app"
_ARGS = r"notify(?:_once|_users)?\(\s*(?:[\w.\[\]]+,\s*){1,2}"
CALL = re.compile(_ARGS + r"\"([A-Z][A-Z_]+)\"", re.S)  # notify(db, user, "KIND", ...)
KIND_ARG = re.compile(_ARGS + r"(_?[A-Z][A-Z_]+)\s*,", re.S)  # notify(db, user, _KIND, ...)
CONSTANT_DEF = re.compile(r"^(_?[A-Z][A-Z_]+) = \"([A-Z][A-Z_]+)\"$", re.M)


def test_every_type_has_one_category_with_defaults() -> None:
    assert set(CATEGORY_OF) == set(NotificationType)
    assert set(CATEGORIES) == set(Category)
    for kind in NotificationType:
        assert category(kind) in CATEGORIES
    for cat, info in CATEGORIES.items():
        assert info.label, cat
        assert info.email_available or not info.email, cat  # no email → can't default on
    assert CATEGORIES[Category.MENTIONS].email is False  # opt-in (D153)
    assert CATEGORIES[Category.MENTIONS].email_available is True


def test_every_template_is_an_account_email_or_has_a_type() -> None:
    assert set(TEMPLATES) >= ACCOUNT_TEMPLATES
    assert set(TEMPLATE_TYPE) <= set(TEMPLATES)
    assert not ACCOUNT_TEMPLATES & set(TEMPLATE_TYPE)
    unmapped = set(TEMPLATES) - ACCOUNT_TEMPLATES - set(TEMPLATE_TYPE)
    assert not unmapped, f"templates with neither an account role nor a type: {unmapped}"
    for template, kind in TEMPLATE_TYPE.items():
        assert CATEGORIES[category(kind)].email_available, template


def test_every_kind_the_code_sends_is_in_the_catalogue() -> None:
    """Kinds passed as string literals, and module constants passed by name, are all in the
    catalogue (at runtime `notify` refuses anything else as well)."""
    known = {t.value for t in NotificationType}
    sent: set[str] = set()
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        sent |= set(CALL.findall(text))
        constants = dict(CONSTANT_DEF.findall(text))
        for name in KIND_ARG.findall(text):
            if name in constants:
                sent.add(constants[name])
    assert {"MENTIONED", "CHECKIN_REMINDER", "RISK_CRITICAL", "BID_NOT_SELECTED"} <= sent
    assert {"TOO_FEW_BIDS", "PROJECT_CANCELLED", "NEW_BIDS"} <= sent  # passed as constants
    assert sent <= known, f"kinds outside the catalogue: {sorted(sent - known)}"


def test_notify_refuses_a_kind_outside_the_catalogue() -> None:
    with pytest.raises(ValueError, match="NOT_A_KIND"):
        asyncio.run(
            notifications.notify(
                None,  # type: ignore[arg-type]  # refused before the session is used
                uuid.uuid4(),
                "NOT_A_KIND",
                title="t",
                body="b",
                link="/",
            )
        )


def test_the_outbox_refuses_unknown_and_anonymous_non_account_emails() -> None:
    with pytest.raises(KeyError):
        asyncio.run(outbox.enqueue(None, to="a@example.com", template="nope", payload={}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="recipient"):
        asyncio.run(
            outbox.enqueue(None, to="a@example.com", template="mentioned", payload={})  # type: ignore[arg-type]
        )
