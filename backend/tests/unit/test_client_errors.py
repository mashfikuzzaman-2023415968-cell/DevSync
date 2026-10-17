"""Client error reports are sanitized before logging (spec §15.7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from app.schemas.public import ClientErrorReport
from app.services import client_errors
from app.services.client_errors import clean_path, clean_text, record_client_error, sanitize

pytestmark = pytest.mark.unit

TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-tok"


def report(**over: object) -> ClientErrorReport:
    data: dict[str, object] = {"message": "TypeError: boom", "path": "/settings", "kind": "render"}
    data.update(over)
    return ClientErrorReport.model_validate(data)


def test_paths_lose_query_strings_and_fragments() -> None:
    assert clean_path(f"/reset-password?token={TOKEN}#x") == "/reset-password"
    assert clean_path(f"/verify-email/{TOKEN}") == "/verify-email/[redacted]"
    assert clean_path("relative/path") == "/"


def test_control_characters_and_secret_like_strings_are_removed() -> None:
    assert clean_text("line\x00one\x1b[31m\u2028two", 100) == "lineone[31mtwo"
    assert clean_text(f"failed with {TOKEN}", 100) == "failed with [redacted]"
    assert len(clean_text("x" * 10, 4)) == 4


def test_stack_is_capped_in_lines() -> None:
    stack = "\n".join(f"at frame{i}" for i in range(100))
    out = sanitize(report(stack=stack))["stack"]
    assert out is not None
    assert out.count("\n") == client_errors.MAX_STACK_LINES - 1


def test_record_logs_a_warning_with_clean_fields() -> None:
    with capture_logs() as logs:
        record_client_error(report(message=f"leak {TOKEN}", path=f"/x?t={TOKEN}"), None)
    entry = logs[-1]
    assert entry["event"] == "client_error"
    assert entry["log_level"] == "warning"
    assert TOKEN not in str(entry)
    assert entry["path"] == "/x"


@pytest.mark.parametrize(
    "over",
    [
        {"extra": "field"},
        {"path": "https://evil.example/"},
        {"kind": "other"},
        {"message": ""},
        {"message": "m" * 501},
        {"stack": "s" * 4001},
        {"request_id": "bad id with spaces"},
    ],
)
def test_invalid_reports_are_rejected(over: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        report(**over)
