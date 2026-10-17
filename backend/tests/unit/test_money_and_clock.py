"""Money helpers (never floats) and the injectable clock."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest
from app.core.clock import Clock, FrozenClock, get_clock, to_display
from app.core.money import (
    apply_basis_points,
    format_taka,
    to_decimal,
    to_paisa,
)
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.unit


def test_to_decimal_accepts_int_str_decimal() -> None:
    assert to_decimal(5) == Decimal(5)
    assert to_decimal("0.25") == Decimal("0.25")
    assert to_decimal(Decimal("1.5")) == Decimal("1.5")


@pytest.mark.parametrize("bad", [0.1, True, None, [1]])
def test_to_decimal_rejects_floats_and_other_types(bad: object) -> None:
    with pytest.raises(TypeError):
        to_decimal(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_to_decimal_rejects_non_finite(bad: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        to_decimal(bad)


def test_to_paisa_rounding_is_explicit() -> None:
    assert to_paisa(Decimal("75854.467"), ROUND_FLOOR) == 75854
    assert to_paisa(Decimal("2.5"), ROUND_HALF_EVEN) == 2
    assert to_paisa(Decimal("3.5"), ROUND_HALF_EVEN) == 4
    with pytest.raises(ValueError, match="Unsupported"):
        to_paisa(Decimal(1), ROUND_HALF_UP)
    with pytest.raises(ValueError, match="non-finite"):
        to_paisa(Decimal("NaN"), ROUND_FLOOR)


def test_spec_reward_example_reconciles() -> None:
    """§9.12.1 row 3: u = 120,000 × (1 − e^(−1)) → 75,854 paisa (ROUND_FLOOR)."""
    u = Decimal(120_000) * (Decimal(1) - Decimal(-1).exp())
    assert to_paisa(u, ROUND_FLOOR) == 75_854


def test_apply_basis_points() -> None:
    assert apply_basis_points(2_400_000, 500) == 120_000  # §9.12.1 fee
    assert apply_basis_points(2_280_000, 6000) == 1_368_000
    assert apply_basis_points(0, 10_000) == 0
    with pytest.raises(ValueError, match="basis points"):
        apply_basis_points(100, 10_001)
    with pytest.raises(ValueError, match="non-negative"):
        apply_basis_points(-1, 10)


@given(st.integers(min_value=0, max_value=10**12), st.integers(min_value=0, max_value=10_000))
def test_basis_point_split_never_creates_money(amount: int, bp: int) -> None:
    part = apply_basis_points(amount, bp)
    rest = apply_basis_points(amount, 10_000 - bp)
    assert 0 <= part <= amount
    assert part + rest <= amount


@pytest.mark.parametrize(
    ("paisa", "text"),
    [
        (0, "৳0"),
        (99, "৳0"),
        (1_250_000, "৳12,500"),
        (12_000_000, "৳1,20,000"),
        (1_234_567_800, "৳1,23,45,678"),
        (-50_000, "-৳500"),
    ],
)
def test_format_taka_uses_bangladeshi_grouping(paisa: int, text: str) -> None:
    assert format_taka(paisa) == text


def test_frozen_clock() -> None:
    at = datetime(2026, 10, 12, 4, 0, tzinfo=UTC)
    clock = FrozenClock(at)
    assert clock.now() == at
    later = datetime(2026, 10, 13, tzinfo=UTC)
    clock.set(later)
    assert clock.now() == later
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.set(datetime(2026, 1, 1))


def test_real_clock_is_utc_aware() -> None:
    assert isinstance(get_clock(), Clock)
    assert get_clock().now().tzinfo is not None


def test_display_conversion_is_dhaka() -> None:
    local = to_display(datetime(2026, 10, 12, 4, 0, tzinfo=UTC))
    assert local.hour == 10
    with pytest.raises(ValueError, match="Naive"):
        to_display(datetime(2026, 1, 1))
