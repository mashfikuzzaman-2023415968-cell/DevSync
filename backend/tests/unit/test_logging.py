"""Log redaction (spec §0.2 rule 12, §14.12)."""

from __future__ import annotations

import json

import pytest

from app.core.logging import (
    REDACTED,
    configure_logging,
    get_logger,
    redact,
    redaction_processor,
    request_id_var,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "new_password",
        "access_token",
        "csrf_token",
        "SECRET_KEY",
        "otp",
        "otp_code",
        "session_id",
        "Authorization",
        "cookie",
        "totp_secret",
        "phone_e164",
        "api_key",
    ],
)
def test_sensitive_keys_are_masked(key: str) -> None:
    assert redact({key: "value-123"}) == {key: REDACTED}


def test_nested_structures_are_masked() -> None:
    data = {"user": {"name": "Nadia", "password": "p"}, "items": [{"token": "t"}, "ok"]}
    assert redact(data) == {
        "user": {"name": "Nadia", "password": REDACTED},
        "items": [{"token": REDACTED}, "ok"],
    }


def test_secret_looking_values_are_masked_under_innocent_keys() -> None:
    out = redact({"note": "Bearer abc.def.ghi and key " + "A" * 40})
    assert "abc.def" not in out["note"]
    assert "A" * 40 not in out["note"]


def test_emails_are_partially_masked() -> None:
    assert redact({"to": "nadia@example.com"}) == {"to": "n***@example.com"}


def test_phone_numbers_in_text_are_masked() -> None:
    assert "1712345678" not in redact({"msg": "call +8801712345678 now"})["msg"]


def test_non_string_values_pass_through() -> None:
    assert redact({"count": 3, "ok": True, "none": None}) == {"count": 3, "ok": True, "none": None}


def test_processor_keeps_bookkeeping_keys() -> None:
    event = {"event": "login", "level": "info", "request_id": "req_abcdefgh", "password": "x"}
    out = redaction_processor(None, "info", event)
    assert out["event"] == "login"
    assert out["request_id"] == "req_abcdefgh"
    assert out["password"] == REDACTED


def test_rendered_log_line_contains_no_secret(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    token = request_id_var.set("req_test12345")
    try:
        get_logger("t").info("user_login", password="hunter2hunter2", otp="123456", user="nadia")
    finally:
        request_id_var.reset(token)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert "hunter2" not in line
    assert "123456" not in line
    assert record["request_id"] == "req_test12345"
    assert record["user"] == "nadia"
