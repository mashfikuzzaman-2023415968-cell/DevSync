"""One Redis client per event loop (`app/core/redis.py`).

The regression: the cache was keyed by `id(loop)`, and Python reuses the id of a collected loop
almost every time, so a new loop was handed a client whose connections belong to a loop that no
longer runs. A request on that client hung inside the gate's backend tests, spinning a core.
"""

from __future__ import annotations

import asyncio
import gc

import pytest
from redis.asyncio import Redis

from app.core import redis as redis_mod

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh() -> None:
    redis_mod.forget_clients()


def _client_in(loop: asyncio.AbstractEventLoop) -> Redis:
    async def grab() -> Redis:
        return redis_mod.get_redis()

    return loop.run_until_complete(grab())


def test_one_loop_gets_one_client() -> None:
    loop = asyncio.new_event_loop()
    try:
        assert _client_in(loop) is _client_in(loop)
    finally:
        loop.close()


def test_two_live_loops_get_their_own_clients() -> None:
    a, b = asyncio.new_event_loop(), asyncio.new_event_loop()
    try:
        assert _client_in(a) is not _client_in(b)
    finally:
        a.close()
        b.close()


def test_a_new_loop_never_inherits_a_dead_loops_client_even_with_its_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Python gives a new loop a collected loop's id almost every time, but not on demand, so the
    # reuse is simulated: every object reports the same id. A cache keyed by id() then returns
    # the dead loop's client; one keyed by the loop itself cannot.
    monkeypatch.setattr(redis_mod, "id", lambda _obj: 1, raising=False)
    old = asyncio.new_event_loop()
    stale = _client_in(old)
    old.close()
    new = asyncio.new_event_loop()
    try:
        assert _client_in(new) is not stale
    finally:
        new.close()


def test_a_dead_loops_client_is_dropped_with_it() -> None:
    loop = asyncio.new_event_loop()
    _client_in(loop)
    assert len(redis_mod._clients) == 1
    loop.close()
    del loop
    gc.collect()
    assert len(redis_mod._clients) == 0


def test_code_outside_a_loop_shares_one_client() -> None:
    assert redis_mod.get_redis() is redis_mod.get_redis()


def test_forget_clients_drops_every_cached_client() -> None:
    outside = redis_mod.get_redis()
    loop = asyncio.new_event_loop()
    try:
        _client_in(loop)
        redis_mod.forget_clients()
        assert len(redis_mod._clients) == 0
        assert redis_mod.get_redis() is not outside
    finally:
        loop.close()


def test_clients_skip_the_maintenance_notification_handshake() -> None:
    client = redis_mod.get_redis()
    # redis-py records a disabled config as None; the default is an "auto" config that sends
    # CLIENT MAINT_NOTIFICATIONS on every new connection.
    assert client.connection_pool.connection_kwargs.get("maint_notifications_config") is None
