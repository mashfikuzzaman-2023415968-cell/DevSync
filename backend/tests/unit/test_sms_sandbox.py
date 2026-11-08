"""The developer SMS inbox (OTP sandbox): recording, reading, the on/off switch and its guard."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI

from app.core.config import Environment, InsecureConfigurationError
from app.integrations import sms
from app.integrations.sms import SANDBOX_KEY, SANDBOX_MAX, deliver_sms, extract_code
from app.main import assert_no_sandbox_routes
from app.services import sms_sandbox
from tests.unit.test_sms import demo_production

pytestmark = pytest.mark.unit


class FakeRedis:
    """Just the list commands the inbox uses (newest first, like Redis LPUSH)."""

    def __init__(self) -> None:
        self.items: list[str] = []
        self.ttl: int | None = None

    async def lpush(self, _key: str, value: str) -> None:
        self.items.insert(0, value)

    async def ltrim(self, _key: str, start: int, stop: int) -> None:
        self.items = self.items[start : stop + 1]

    async def expire(self, _key: str, seconds: int) -> None:
        self.ttl = seconds

    async def lrange(self, _key: str, start: int, stop: int) -> list[str]:
        return self.items[start : stop + 1]

    async def delete(self, _key: str) -> None:
        self.items = []


def dev(**overrides: object) -> Any:
    return demo_production(
        DEVSYNC_ENV=Environment.DEVELOPMENT, SMS_PROVIDER="console", DEMO_STACK=False, **overrides
    )


# -- the one-time code -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Your DevSync code is 123456", "123456"),
        ("Your DevSync code is 0042", "0042"),
        ("code 12345678 now", "12345678"),
        ("no digits here", None),
        ("only 123 digits", None),  # too short
        ("number 123456789 is too long", None),  # not a 4-8 digit run
        ("", None),
        ("Code ٣٤٥٦٧٨ arabic-indic digits", None),  # only ASCII digits count
    ],
)
def test_extract_code(text: str, code: str | None) -> None:
    assert extract_code(text) == code


# -- the on/off switch (fail closed) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "enabled"),
    [
        ({"DEVSYNC_ENV": Environment.DEVELOPMENT, "DEMO_STACK": False}, True),
        ({"DEVSYNC_ENV": Environment.TEST, "DEMO_STACK": False}, True),
        ({"DEVSYNC_ENV": Environment.PRODUCTION, "DEMO_STACK": True}, True),  # offline demo
        ({"DEVSYNC_ENV": Environment.PRODUCTION, "DEMO_STACK": False}, False),  # real deployment
    ],
)
def test_sandbox_switch(overrides: dict[str, object], enabled: bool) -> None:
    assert demo_production(**overrides).sms_sandbox_enabled is enabled


def test_default_settings_are_not_production_demo() -> None:
    # A production deployment never sets DEMO_STACK, so it can never turn the inbox on.
    assert demo_production(DEMO_STACK=False).sms_sandbox_enabled is False


def test_guard_refuses_a_mounted_inbox_where_it_is_off() -> None:
    from app.api.v1 import sms_sandbox as router_module  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/v1")
    off = demo_production(DEMO_STACK=False)
    with pytest.raises(InsecureConfigurationError):
        assert_no_sandbox_routes(app, off)
    assert_no_sandbox_routes(app, demo_production())  # on: fine
    assert_no_sandbox_routes(FastAPI(), off)  # nothing mounted: fine


def test_the_routes_stay_out_of_the_public_api_document() -> None:
    from app.api.v1 import sms_sandbox as router_module  # noqa: PLC0415

    assert router_module.router.include_in_schema is False
    assert all(not getattr(r, "include_in_schema", True) for r in router_module.router.routes)


# -- recording and delivering ----------------------------------------------------------------


async def test_record_keeps_code_and_caps_the_list() -> None:
    redis = FakeRedis()
    for i in range(SANDBOX_MAX + 5):
        await sms.record_sandbox_sms(redis, "+8801712345678", f"Your DevSync code is {100000 + i}")  # type: ignore[arg-type]
    assert len(redis.items) == SANDBOX_MAX
    newest = json.loads(redis.items[0])
    assert newest["code"] == str(100000 + SANDBOX_MAX + 4)
    assert newest["to"] == "+8801712345678"
    assert redis.ttl == sms.SANDBOX_TTL


async def test_deliver_records_and_sends_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []

    class Sender:
        async def send(self, phone: str, text: str) -> None:
            sent.append((phone, text))

    monkeypatch.setattr(sms, "sms_sender", lambda _s, _r: Sender())
    redis = FakeRedis()
    await deliver_sms(dev(), redis, "+8801712345678", "Your DevSync code is 424242")  # type: ignore[arg-type]
    assert sent == [("+8801712345678", "Your DevSync code is 424242")]
    assert json.loads(redis.items[0])["code"] == "424242"


async def test_deliver_keeps_nothing_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    class Sender:
        async def send(self, phone: str, text: str) -> None:
            sent.append(text)

    monkeypatch.setattr(sms, "sms_sender", lambda _s, _r: Sender())
    redis = FakeRedis()
    await deliver_sms(demo_production(DEMO_STACK=False), redis, "+8801712345678", "code 424242")  # type: ignore[arg-type]
    assert sent == ["code 424242"]
    assert redis.items == []  # codes are never copied anywhere in a real deployment


async def test_a_broken_inbox_never_blocks_the_real_send(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    class Sender:
        async def send(self, phone: str, text: str) -> None:
            sent.append(text)

    class Broken(FakeRedis):
        async def lpush(self, _key: str, value: str) -> None:
            raise ConnectionError("redis down")

    monkeypatch.setattr(sms, "sms_sender", lambda _s, _r: Sender())
    await deliver_sms(dev(), Broken(), "+8801712345678", "code 424242")  # type: ignore[arg-type]
    assert sent == ["code 424242"]


# -- reading ---------------------------------------------------------------------------------


async def _filled() -> FakeRedis:
    redis = FakeRedis()
    await sms.record_sandbox_sms(redis, "+8801711111111", "Your DevSync code is 111111")  # type: ignore[arg-type]
    await sms.record_sandbox_sms(redis, "+8801722222222", "Your DevSync code is 222222")  # type: ignore[arg-type]
    await sms.record_sandbox_sms(redis, "+8801711111111", "Your DevSync code is 333333")  # type: ignore[arg-type]
    return redis


async def test_list_is_newest_first_with_the_newest_code() -> None:
    result = await sms_sandbox.list_messages(await _filled(), None, 50)  # type: ignore[arg-type]
    assert [m.code for m in result.messages] == ["333333", "222222", "111111"]
    assert result.newest_code == "333333"


@pytest.mark.parametrize("phone", ["+8801711111111", "8801711111111", "+880 1711111111"])
async def test_phone_filter_ignores_plus_and_spaces(phone: str) -> None:
    result = await sms_sandbox.list_messages(await _filled(), phone, 50)  # type: ignore[arg-type]
    assert [m.code for m in result.messages] == ["333333", "111111"]


async def test_phone_filter_with_no_match_is_empty() -> None:
    result = await sms_sandbox.list_messages(await _filled(), "+8801799999999", 50)  # type: ignore[arg-type]
    assert result.messages == []
    assert result.newest_code is None


async def test_limit_keeps_only_the_newest() -> None:
    result = await sms_sandbox.list_messages(await _filled(), None, 1)  # type: ignore[arg-type]
    assert [m.code for m in result.messages] == ["333333"]


async def test_an_unreadable_entry_is_skipped_not_fatal() -> None:
    redis = await _filled()
    redis.items.insert(0, "not json")
    redis.items.insert(1, json.dumps({"id": "x"}))  # missing fields
    result = await sms_sandbox.list_messages(redis, None, 50)  # type: ignore[arg-type]
    assert len(result.messages) == 3


async def test_clear_empties_the_inbox() -> None:
    redis = await _filled()
    await sms_sandbox.clear_messages(redis)  # type: ignore[arg-type]
    assert (await sms_sandbox.list_messages(redis, None, 50)).messages == []  # type: ignore[arg-type]
    assert SANDBOX_KEY == "sandbox:sms"
