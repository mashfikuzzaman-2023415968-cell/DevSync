"""The project-file byte budget's pure parts and its Redis failure mode (D175).

Covered: the per-user, per-Dhaka-day key (hashed, rolls over at Dhaka midnight, not UTC);
`Retry-After` until Dhaka midnight at its boundaries; what is reserved for a missing, zero, small
or oversized Content-Length; Redis down fails closed (503) and an over-budget reservation is 429.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.ratelimit import RateLimited, RateLimitUnavailable
from app.services import project_files as pf

pytestmark = pytest.mark.unit
USER = uuid.UUID("0f3c2b1a-9e8d-4c7b-a6f5-e4d3c2b1a098")
MB = 1024 * 1024


def test_the_key_is_per_user_and_dhaka_day_and_hides_the_user() -> None:
    before = pf.budget_key(USER, datetime(2026, 12, 14, 17, 59, 59, tzinfo=UTC))  # 23:59:59 BDT
    after = pf.budget_key(USER, datetime(2026, 12, 14, 18, 0, 0, tzinfo=UTC))  # 00:00 BDT
    assert before.endswith(":2026-12-14")
    assert after.endswith(":2026-12-15")
    assert before.startswith("rl:upload_bytes:")
    assert str(USER) not in before
    other = pf.budget_key(uuid.uuid4(), datetime(2026, 12, 14, 12, tzinfo=UTC))
    assert other.rsplit(":", 1)[0] != before.rsplit(":", 1)[0]


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 12, 14, 18, 0, 0, tzinfo=UTC), 24 * 3600),  # exactly Dhaka midnight
        (datetime(2026, 12, 14, 17, 59, 59, tzinfo=UTC), 1),  # one second before
        (datetime(2026, 12, 14, 17, 59, 59, 900_000, tzinfo=UTC), 1),  # never 0
        (datetime(2026, 12, 14, 6, 0, 0, tzinfo=UTC), 12 * 3600),  # noon in Dhaka
    ],
)
def test_retry_after_runs_to_dhaka_midnight(now: datetime, expected: int) -> None:
    assert pf.seconds_to_dhaka_midnight(now) == expected


@pytest.mark.parametrize(
    ("content_length", "expected"),
    [(None, 20 * MB), (0, 20 * MB), (-5, 20 * MB), (1, 1), (5 * MB, 5 * MB), (99 * MB, 20 * MB)],
)
def test_what_is_reserved(content_length: int | None, expected: int) -> None:
    assert pf.reservation(content_length, 20 * MB) == expected


class _Script:
    def __init__(self, result: Any) -> None:
        self.result = result

    async def __call__(self, **_: Any) -> Any:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Redis:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.increments: list[tuple[str, int]] = []

    def register_script(self, _source: str) -> _Script:
        return _Script(self.result)

    async def incrby(self, key: str, amount: int) -> int:
        if isinstance(self.result, Exception):
            raise self.result
        self.increments.append((key, amount))
        return amount


NOW = datetime(2026, 12, 14, 6, tzinfo=UTC)


async def test_redis_down_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "get_redis", lambda: _Redis(RedisConnectionError("down")))
    with pytest.raises(RateLimitUnavailable):
        await pf._reserve("k", 10, 100, NOW)


async def test_over_budget_is_rate_limited_until_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "get_redis", lambda: _Redis(0))
    with pytest.raises(RateLimited) as caught:
        await pf._reserve("k", 10, 100, NOW)
    assert caught.value.retry_after == 12 * 3600


async def test_within_budget_passes_and_settles(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Redis(1)
    monkeypatch.setattr(pf, "get_redis", lambda: fake)
    await pf._reserve("k", 10, 100, NOW)
    await pf._settle("k", -4)
    await pf._settle("k", 0)  # nothing to send
    assert fake.increments == [("k", -4)]


async def test_settling_without_redis_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "get_redis", lambda: _Redis(RedisConnectionError("down")))
    await pf._settle("k", -4)  # over-counted for the day, which is the safe side
