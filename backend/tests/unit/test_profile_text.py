"""Profile text fields: cleaned, but held to their documented maxLength (spec §7.2)."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.profiles import Line120, SourceName, Text2000, Title

pytestmark = pytest.mark.unit

TEXT = TypeAdapter(Text2000)


def _error(adapter: TypeAdapter[str], value: object) -> str:
    with pytest.raises(ValidationError) as caught:
        adapter.validate_python(value)
    return str(caught.value.errors()[0]["type"])


def test_text_at_the_limit_is_kept() -> None:
    assert TEXT.validate_python("a" * 2000) == "a" * 2000


@pytest.mark.parametrize(
    "value",
    [
        "a" * 2001,
        "\x17" + "a" * 2000,  # one control character over: stripping must not sneak it under
        "\x00" * 10 + "a" * 1995,
        " " + "a" * 2000,  # trimming doesn't either
    ],
)
def test_input_over_the_documented_length_is_refused(value: str) -> None:
    assert _error(TEXT, value) == "string_too_long"


def test_text_is_still_cleaned() -> None:
    assert TEXT.validate_python("  \x17Line one\nline two\x7f  ") == "Line one\nline two"
    assert TypeAdapter(Line120).validate_python("Senior\x00 developer\n") == "Senior developer"


@pytest.mark.parametrize(
    ("adapter", "limit"),
    [(TypeAdapter(Line120), 120), (TypeAdapter(Title), 120), (TypeAdapter(SourceName), 80)],
)
def test_every_line_type_holds_its_limit(adapter: TypeAdapter[str], limit: int) -> None:
    assert adapter.validate_python("x" * limit) == "x" * limit
    assert _error(adapter, "\x01" + "x" * limit) == "string_too_long"


def test_a_title_of_only_control_characters_is_empty() -> None:
    assert _error(TypeAdapter(Title), "\x01\x02") == "too_short"


def test_non_strings_are_left_to_the_type_check() -> None:
    assert _error(TEXT, 123) == "string_type"
