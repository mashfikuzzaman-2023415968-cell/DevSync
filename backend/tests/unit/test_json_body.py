"""JSON body rules: content type, nesting depth, NaN/Infinity (spec §10.1, §14.7)."""

from __future__ import annotations

import pytest

from app.core.json_body import (
    MAX_JSON_DEPTH,
    has_non_finite_number,
    is_json_content_type,
    media_type,
    nesting_depth_exceeds,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("application/json", True),
        ("Application/JSON", True),
        ("application/json; charset=utf-8", True),
        ('application/json; charset="UTF-8"', True),
        ("application/json;charset=utf8", True),
        ("application/json; charset=latin-1", False),
        ("application/json-patch+json", False),
        ("application/x-www-form-urlencoded", False),
        ("multipart/form-data; boundary=x", False),
        ("text/plain", False),
        ("text/json", False),
        ("", False),
        (None, False),
    ],
)
def test_json_content_type(value: str | None, ok: bool) -> None:
    assert is_json_content_type(value) is ok


def test_media_type_parsing() -> None:
    assert media_type("Multipart/Form-Data; Boundary=abc") == (
        "multipart/form-data",
        {"boundary": "abc"},
    )
    assert media_type("application/json;;") == ("application/json", {})


def _nested(depth: int) -> bytes:
    return b"[" * depth + b"]" * depth


def test_depth_boundary() -> None:
    assert not nesting_depth_exceeds(_nested(MAX_JSON_DEPTH))
    assert nesting_depth_exceeds(_nested(MAX_JSON_DEPTH + 1))
    mixed = b'{"a":' * (MAX_JSON_DEPTH - 1) + b"[1]" + b"}" * (MAX_JSON_DEPTH - 1)
    assert not nesting_depth_exceeds(mixed)
    assert nesting_depth_exceeds(b'{"a":' + mixed + b"}")


def test_brackets_inside_strings_do_not_count() -> None:
    body = b'{"text": "' + b"[{" * 100 + b'\\" [[[[ \\\\"}'
    assert not nesting_depth_exceeds(body)
    # An escaped quote does not end the string.
    assert not nesting_depth_exceeds(b'["\\"' + b"[" * 50 + b'"]')


def test_huge_nesting_is_rejected_without_recursion() -> None:
    assert nesting_depth_exceeds(b"[" * 250_000)


@pytest.mark.parametrize(
    "body",
    [b'{"x": NaN}', b'{"x": Infinity}', b'{"x": -Infinity}', b"[1, [NaN]]"],
)
def test_non_finite_numbers_are_found(body: bytes) -> None:
    assert has_non_finite_number(body)


@pytest.mark.parametrize(
    "body",
    [b'{"x": "NaN"}', b'{"Infinity": 1}', b'{"x": 1e308}', b"{not json NaN", b"\xff\xfe"],
)
def test_strings_and_malformed_json_are_not_flagged(body: bytes) -> None:
    assert not has_non_finite_number(body)


def test_rules_apply_when_the_router_is_unknown() -> None:
    from app.core.json_body import _route_serves  # noqa: PLC0415

    assert _route_serves({"type": "http", "method": "POST", "path": "/api/v1/x"})
