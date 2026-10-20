"""Availability overlap and feasibility maths (spec §9.17). Pure."""

from __future__ import annotations

from datetime import date

from app.algorithms.availability import (
    Period,
    Reservation,
    committed_hours,
    is_feasible,
    overlaps,
)


def p(a: str, b: str) -> Period:
    return Period(date.fromisoformat(a), date.fromisoformat(b))


def test_overlapping_periods() -> None:
    assert overlaps(p("2026-01-01", "2026-01-31"), p("2026-01-15", "2026-02-15"))


def test_adjacent_periods_do_not_overlap() -> None:
    # One ends the day before the next begins → no shared day.
    assert not overlaps(p("2026-01-01", "2026-01-10"), p("2026-01-11", "2026-01-20"))


def test_same_day_boundary_overlaps() -> None:
    # One ends on the exact day the next starts → they share that day (inclusive ranges).
    assert overlaps(p("2026-01-01", "2026-01-10"), p("2026-01-10", "2026-01-20"))


def test_single_day_periods() -> None:
    assert overlaps(p("2026-01-05", "2026-01-05"), p("2026-01-05", "2026-01-05"))
    assert not overlaps(p("2026-01-05", "2026-01-05"), p("2026-01-06", "2026-01-06"))


def test_committed_hours_counts_only_overlapping() -> None:
    period = p("2026-02-01", "2026-02-28")
    reservations = [
        Reservation(p("2026-02-10", "2026-02-20"), 15),  # overlaps
        Reservation(p("2026-03-01", "2026-03-10"), 20),  # after → excluded
        Reservation(p("2026-01-01", "2026-01-31"), 10),  # before → excluded
    ]
    assert committed_hours(reservations, period) == 15


def test_feasible_at_and_over_the_limit() -> None:
    period = p("2026-02-01", "2026-02-28")
    existing = [Reservation(p("2026-02-05", "2026-02-25"), 30)]
    # 30 committed + 10 new = 40 == profile 40 → feasible (boundary).
    assert is_feasible(existing, period, new_commitment=10, profile_hours=40)
    # 30 + 11 = 41 > 40 → not feasible.
    assert not is_feasible(existing, period, new_commitment=11, profile_hours=40)


def test_feasible_with_no_existing_reservations() -> None:
    assert is_feasible([], p("2026-02-01", "2026-02-28"), new_commitment=20, profile_hours=40)
