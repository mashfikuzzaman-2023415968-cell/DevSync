"""Phone numbers as people in Bangladesh write them (audit fix, D56)."""

from __future__ import annotations

import pytest

from app.schemas.auth import normalise_phone

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("written", "stored"),
    [
        ("+8801712345678", "+8801712345678"),
        ("+88001712345678", "+8801712345678"),  # "+880" prefill + local number
        ("01712345678", "+8801712345678"),
        ("+880 1712-345678", "+8801712345678"),
        ("+447911123456", "+447911123456"),  # other countries: plain E.164
    ],
)
def test_accepted_numbers_are_stored_in_e164(written: str, stored: str) -> None:
    assert normalise_phone(written) == stored


@pytest.mark.parametrize(
    "written", ["+88012345", "+8801212345678", "+8802123456789", "0171234567", "12345", "+0123"]
)
def test_other_numbers_are_refused(written: str) -> None:
    with pytest.raises(ValueError, match="Use"):
        normalise_phone(written)
