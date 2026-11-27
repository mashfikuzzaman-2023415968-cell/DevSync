"""Check-in weeks (D145, `app/algorithms/weeks.py`): the Dhaka week, on time at the Tuesday
23:59 boundary (±1 minute), expected weeks from the first Monday on or after joining, and the
weeks that are over. Times are fixed instants (FrozenClock-style), never the real clock."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.algorithms.weeks import (
    DHAKA,
    due_at,
    expected_weeks,
    finished_weeks,
    first_expected_week,
    is_on_time,
    week_of,
)

pytestmark = pytest.mark.unit
MON = date(2026, 11, 23)


def dhaka(day: tuple[int, int, int], hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    """A Dhaka wall-clock instant: dhaka((2026, 11, 24), 23, 59)."""
    return datetime(*day, hh, mm, ss, tzinfo=DHAKA)


def test_the_week_is_monday_to_sunday_in_dhaka() -> None:
    assert week_of(dhaka((2026, 11, 23), 0, 0)) == MON  # Monday 00:00 Dhaka
    assert week_of(dhaka((2026, 11, 29), 23, 59)) == MON  # Sunday night
    assert week_of(dhaka((2026, 11, 30), 0, 0)) == MON + timedelta(days=7)
    # 2026-11-22 18:30 UTC is Monday 00:30 in Dhaka (UTC+6).
    assert week_of(datetime(2026, 11, 22, 18, 30, tzinfo=UTC)) == MON
    assert week_of(datetime(2026, 11, 22, 17, 59, tzinfo=UTC)) == MON - timedelta(days=7)


def test_naive_times_are_refused() -> None:
    with pytest.raises(ValueError, match="timezone"):
        week_of(datetime(2026, 11, 23, 10, 0))


@pytest.mark.parametrize(
    ("posted", "on_time"),
    [
        (dhaka((2026, 11, 24), 23, 58), True),
        (dhaka((2026, 11, 24), 23, 59, 59), True),
        (dhaka((2026, 11, 25), 0, 0), False),
        (dhaka((2026, 11, 25), 0, 1), False),
        (dhaka((2026, 11, 23), 10, 0), True),
    ],
)
def test_on_time_until_tuesday_2359_dhaka(posted: datetime, on_time: bool) -> None:
    assert is_on_time(posted, MON) is on_time


def test_the_due_time_is_tuesday_night_in_dhaka() -> None:
    assert due_at(MON).astimezone(UTC) == datetime(2026, 11, 24, 17, 59, 59, 999999, tzinfo=UTC)


@pytest.mark.parametrize(
    ("joined", "first"),
    [
        (dhaka((2026, 11, 23), 9, 0), MON),  # a Monday: that week
        (dhaka((2026, 11, 24), 9, 0), MON + timedelta(days=7)),  # Tuesday: the next Monday
        (dhaka((2026, 11, 29), 23, 0), MON + timedelta(days=7)),  # Sunday night
    ],
)
def test_the_first_expected_week_starts_on_or_after_joining(joined: datetime, first: date) -> None:
    assert first_expected_week(joined) == first


def test_expected_and_finished_weeks() -> None:
    joined = dhaka((2026, 11, 4), 12)  # a Wednesday: first expected week is Mon 9 Nov
    now = dhaka((2026, 11, 25), 12)  # in the week of Mon 23 Nov
    weeks = expected_weeks(joined, now)
    assert weeks == [date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23)]
    assert finished_weeks(joined, now, now) == [date(2026, 11, 9), date(2026, 11, 16)]
    left = dhaka((2026, 11, 17), 9)  # left in the week of 16 Nov
    assert finished_weeks(joined, left, now) == [date(2026, 11, 9), date(2026, 11, 16)]
    assert expected_weeks(joined, dhaka((2026, 11, 6))) == []  # before the first week
