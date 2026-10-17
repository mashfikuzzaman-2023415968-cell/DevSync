"""Injectable clock so time-dependent rules can be tested with frozen time (spec §16.2).

All times are UTC (`timestamptz`); conversion to Asia/Dhaka happens only for display.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Asia/Dhaka")


class Clock:
    """Real wall clock. Services receive a Clock instead of calling `datetime.now()`."""

    def now(self) -> datetime:
        """Current time, timezone-aware UTC."""
        return datetime.now(UTC)


class FrozenClock(Clock):
    """Clock that returns a fixed time until moved; used by tests and simulations."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FrozenClock needs a timezone-aware datetime")
        self._at = at.astimezone(UTC)

    def now(self) -> datetime:
        """The frozen instant."""
        return self._at

    def set(self, at: datetime) -> None:
        """Move the frozen instant to `at` (must be timezone-aware)."""
        if at.tzinfo is None:
            raise ValueError("FrozenClock needs a timezone-aware datetime")
        self._at = at.astimezone(UTC)


_clock: Clock = Clock()


def get_clock() -> Clock:
    """Process-wide clock (FastAPI dependency and service default)."""
    return _clock


def to_display(at: datetime) -> datetime:
    """Convert a UTC instant to Asia/Dhaka for display."""
    if at.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed")
    return at.astimezone(DISPLAY_TZ)
