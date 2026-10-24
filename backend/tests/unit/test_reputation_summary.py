"""The profile reputation summary (D48, D55): exact 3-place C/P, null while there's no record,
and the "seeded" demo marker never in production."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.profiles import reputation_summary
from app.services.reputation_read import StoredReputation

pytestmark = pytest.mark.unit


def _stored(**over: object) -> StoredReputation:
    values: dict[str, object] = {
        "c": Decimal("0.712"),
        "p": Decimal("0.768"),
        "is_newcomer": False,
        "seeded": True,
    }
    values.update(over)
    return StoredReputation(**values)  # type: ignore[arg-type]


def test_no_snapshot_means_newcomer_without_values() -> None:
    out = reputation_summary(None, production=False)
    assert out.competency is None
    assert out.performance is None
    assert out.is_newcomer is True
    assert out.seeded is False


def test_values_are_three_places_and_serialise_as_strings() -> None:
    out = reputation_summary(_stored(c=Decimal("0.5"), p=Decimal("1")), production=False)
    assert out.model_dump(mode="json") == {
        "competency": "0.500",
        "performance": "1.000",
        "is_newcomer": False,
        "seeded": True,
    }


def test_boundaries_zero_and_one() -> None:
    out = reputation_summary(_stored(c=Decimal("0"), p=Decimal("0.000")), production=False)
    assert out.model_dump(mode="json")["competency"] == "0.000"
    assert out.model_dump(mode="json")["performance"] == "0.000"


def test_seeded_marker_is_hidden_in_production() -> None:
    assert reputation_summary(_stored(), production=True).seeded is False
    assert reputation_summary(_stored(), production=False).seeded is True
    assert reputation_summary(_stored(seeded=False), production=False).seeded is False


def test_newcomer_flag_passes_through() -> None:
    assert reputation_summary(_stored(is_newcomer=True), production=True).is_newcomer is True
