"""Check-in weeks (DECISIONS D145). Pure: callers pass the times; nothing reads a clock.

A check-in belongs to the Monday–Sunday week, in Asia/Dhaka, in which it is posted. It is on time
when posted by Tuesday 23:59:59.999999 Dhaka of that week (the reminder goes out Monday 10:00, so
that is a day and a half). A member is expected to check in every week from the first Monday on or
after the day they became ACTIVE, until they leave or the project stops being IN_PROGRESS.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DHAKA = ZoneInfo("Asia/Dhaka")
ON_TIME_DAYS = 1  # Monday + 1 = Tuesday


def dhaka_date(at: datetime) -> date:
    if at.tzinfo is None:
        raise ValueError("times must be timezone-aware")
    return at.astimezone(DHAKA).date()


def week_start(day: date) -> date:
    """The Monday of `day`'s week."""
    return day - timedelta(days=day.weekday())


def week_of(at: datetime) -> date:
    """The Monday (Dhaka) of the week an instant falls in."""
    return week_start(dhaka_date(at))


def due_at(monday: date) -> datetime:
    """The last on-time instant of a week: Tuesday 23:59:59.999999 in Dhaka."""
    return datetime.combine(monday + timedelta(days=ON_TIME_DAYS), time.max, tzinfo=DHAKA)


def is_on_time(posted_at: datetime, monday: date) -> bool:
    return posted_at <= due_at(monday)


def first_expected_week(active_since: datetime) -> date:
    """The first Monday on or after the (Dhaka) day the member became ACTIVE."""
    day = dhaka_date(active_since)
    monday = week_start(day)
    return monday if monday == day else monday + timedelta(days=7)


def expected_weeks(active_since: datetime, until: datetime) -> list[date]:
    """Every week (by its Monday) the member owed a check-in, from their first expected week up
    to and including the week `until` falls in (empty if that is before the first)."""
    first = first_expected_week(active_since)
    last = week_of(until)
    weeks: list[date] = []
    current = first
    while current <= last:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks


def finished_weeks(active_since: datetime, until: datetime, now: datetime) -> list[date]:
    """Expected weeks that are over by `now` (their Sunday has passed in Dhaka): the ones a
    missing check-in can be recorded for."""
    this_week = week_of(now)
    return [w for w in expected_weeks(active_since, min(until, now)) if w < this_week]
