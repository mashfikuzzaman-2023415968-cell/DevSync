"""Availability reservation maths — prevents double booking (spec §9.17). PURE.

A bid declares `hours_per_week_committed`. A developer is UNAVAILABLE for a project if the sum of
their **confirmed** reservations overlapping the project period, plus this commitment, exceeds
their profile `hours_per_week`. Periods are `[from_date, to_date]` inclusive of both endpoints
(a project runs on its start and finish days); two periods overlap when each starts on or before
the other ends. Adjacent periods where one ends the day before the next begins do **not** overlap.
No database or clock access; `services/availability.py` loads the confirmed reservations and calls
`is_feasible`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Period:
    """An inclusive day range; `to` must be on or after `from_`."""

    from_: date
    to: date


@dataclass(frozen=True)
class Reservation:
    period: Period
    hours_per_week: int


def overlaps(a: Period, b: Period) -> bool:
    """True when the two inclusive day ranges share at least one day."""
    return a.from_ <= b.to and b.from_ <= a.to


def committed_hours(reservations: list[Reservation], period: Period) -> int:
    """Total weekly hours already committed over reservations overlapping `period`."""
    return sum(r.hours_per_week for r in reservations if overlaps(r.period, period))


def is_feasible(
    reservations: list[Reservation], period: Period, new_commitment: int, profile_hours: int
) -> bool:
    """Whether `new_commitment` fits within `profile_hours` given overlapping reservations."""
    return committed_hours(reservations, period) + new_commitment <= profile_hours
