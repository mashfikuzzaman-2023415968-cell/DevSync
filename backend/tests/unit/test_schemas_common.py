"""A NUL character left in request text is refused before it can reach the database (spec §14.7)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

import pytest
from pydantic import AfterValidator, AwareDatetime, Field, ValidationError

from app.schemas.common import StrictRequest, has_nul, wrong_json_type

pytestmark = pytest.mark.unit


def _clean(value: str) -> str:
    return value.replace("\x00", "")


class _Inner(StrictRequest):
    note: str


class _Body(StrictRequest):
    name: str
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)
    inner: _Inner | None = None
    cleaned: Annotated[str, AfterValidator(_clean)] = ""
    count: int = 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a\x00b", True),
        ("plain", False),
        (["x", "y\x00"], True),
        (("x\x00",), True),
        ({"k": "v\x00"}, True),
        ({"k\x00": "v"}, True),
        ({"a": [{"b": "\x00"}]}, True),  # found through lists and dicts, however deep
        (5, False),
        (None, False),
        ("", False),
    ],
)
def test_has_nul(value: object, expected: bool) -> None:
    assert has_nul(value) is expected


def _locations(exc: ValidationError) -> list[tuple[str | int, ...]]:
    return [tuple(e["loc"]) for e in exc.errors()]


@pytest.mark.parametrize(
    ("payload", "where"),
    [
        ({"name": "a\x00b"}, ("name",)),
        ({"name": "ok", "tags": ["fine", "x\x00"]}, ("tags",)),
        ({"name": "ok", "extra": {"k": "v\x00"}}, ("extra",)),
        ({"name": "ok", "inner": {"note": "\x00"}}, ("inner", "note")),
    ],
)
def test_a_nul_is_refused_at_the_field_that_holds_it(
    payload: dict[str, object], where: tuple[str, ...]
) -> None:
    with pytest.raises(ValidationError) as caught:
        _Body.model_validate(payload)
    assert where in _locations(caught.value)
    assert "NUL" in caught.value.errors()[0]["msg"]


def test_clean_text_is_accepted_unchanged() -> None:
    body = _Body.model_validate({"name": "Online ordering", "tags": ["a"], "count": 3})
    assert (body.name, body.tags, body.count) == ("Online ordering", ["a"], 3)


def test_a_field_that_cleans_its_own_text_keeps_doing_so() -> None:
    assert _Body.model_validate({"name": "x", "cleaned": "a\x00b"}).cleaned == "ab"


class _Typed(StrictRequest):
    amount: int = 0
    flag: bool = False
    maybe_flag: bool | None = None
    day: date | None = None
    when: AwareDatetime | None = None
    label: str = ""
    ratio: float = 0.0
    mode: str | int = 1


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"amount": False}, "amount"),
        ({"amount": True}, "amount"),
        ({"label": True}, "label"),
        ({"ratio": True}, "ratio"),
        ({"day": 0}, "day"),
        ({"day": 1700000000}, "day"),
        ({"day": 1.5}, "day"),
        ({"when": 0}, "when"),
        ({"day": True}, "day"),
    ],
)
def test_the_wrong_json_type_is_refused_not_coerced(payload: dict[str, object], field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        _Typed.model_validate(payload)
    assert (field,) in _locations(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": 5},
        {"flag": True},
        {"flag": False},
        {"maybe_flag": True},
        {"maybe_flag": None},
        {"day": "2026-11-20"},
        {"day": None},
        {"when": "2026-11-20T10:00:00+06:00"},
        {"ratio": 3},
        {"mode": 2},
        {"mode": "text"},
        {},
    ],
)
def test_right_values_still_pass(payload: dict[str, object]) -> None:
    _Typed.model_validate(payload)


@pytest.mark.parametrize(
    ("value", "annotation", "wrong"),
    [
        (True, int, True),
        (True, bool, False),
        (True, bool | None, False),
        (True, int | None, True),
        (True, object, False),
        (0, date, True),
        (0, datetime | None, True),
        (0, int | date, False),
        (None, int, False),
        ("x", int, False),
        (3, str, False),
    ],
)
def test_wrong_json_type(value: object, annotation: object, wrong: bool) -> None:
    assert wrong_json_type(value, annotation) is wrong
