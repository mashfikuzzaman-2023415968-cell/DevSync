"""CAPTCHA verification, email templates/header safety, TOTP window/replay, job backoff."""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
from altcha import v1 as altcha_v1

from app.core import captcha
from app.core.ratelimit import RateLimited, hash_key
from app.integrations.email import build_message, render, validate_address
from app.jobs.email_jobs import backoff
from app.services.auth.login import verify_totp_code
from tests.conftest import make_settings

pytestmark = pytest.mark.unit
KEY = "captcha-test-key-" * 2


class FakeRedis:
    """Just enough of redis for single-use CAPTCHA checks."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def set(self, key: str, value: Any, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True


def solved(challenge: dict[str, Any]) -> str:
    solution = altcha_v1.solve_challenge(
        challenge["challenge"], challenge["salt"], "SHA-256", challenge["max_number"]
    )
    assert solution is not None
    payload = {
        "algorithm": "SHA-256",
        "challenge": challenge["challenge"],
        "number": solution.number,
        "salt": challenge["salt"],
        "signature": challenge["signature"],
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def long_ago() -> int:
    return int(time.time() * 1000) - 10_000


async def test_valid_solution_is_accepted_once() -> None:
    redis = FakeRedis()
    payload = solved(captcha.create_challenge(KEY, test_mode=True))
    await captcha.verify(redis, KEY, payload=payload, honeypot=None, started_at_ms=long_ago())  # type: ignore[arg-type]
    with pytest.raises(captcha.CaptchaError):  # replay
        await captcha.verify(redis, KEY, payload=payload, honeypot=None, started_at_ms=long_ago())  # type: ignore[arg-type]


@pytest.mark.parametrize("case", ["missing", "tampered", "wrong_key", "garbage", "too_long"])
async def test_bad_solutions_are_rejected(case: str) -> None:
    payload: str | None = solved(captcha.create_challenge(KEY, test_mode=True))
    key = KEY
    if case == "missing":
        payload = None
    elif case == "tampered":
        data = json.loads(base64.b64decode(payload or ""))
        data["number"] += 1
        payload = base64.b64encode(json.dumps(data).encode()).decode()
    elif case == "wrong_key":
        key = "another-key-entirely-1234567890"
    elif case == "garbage":
        payload = "not-base64-json"
    elif case == "too_long":
        payload = "A" * 5000
    with pytest.raises(captcha.CaptchaError):
        await captcha.verify(
            FakeRedis(), key, payload=payload, honeypot=None, started_at_ms=long_ago()
        )  # type: ignore[arg-type]


async def test_expired_challenge_is_rejected() -> None:
    challenge = altcha_v1.create_challenge(
        altcha_v1.ChallengeOptions(
            hmac_key=KEY, max_number=10, expires=datetime.now(UTC) - timedelta(seconds=1)
        )
    )
    payload = solved(
        {
            "challenge": challenge.challenge,
            "salt": challenge.salt,
            "signature": challenge.signature,
            "max_number": challenge.max_number,
        }
    )
    with pytest.raises(captcha.CaptchaError):
        await captcha.verify(
            FakeRedis(), KEY, payload=payload, honeypot=None, started_at_ms=long_ago()
        )  # type: ignore[arg-type]


async def test_honeypot_and_fill_time() -> None:
    with pytest.raises(captcha.CaptchaError):
        await captcha.verify(
            FakeRedis(), KEY, payload=None, honeypot="http://spam", started_at_ms=None, bypass=True
        )  # type: ignore[arg-type]
    too_fast = int(time.time() * 1000) - 500
    with pytest.raises(captcha.CaptchaError):
        await captcha.verify(
            FakeRedis(), KEY, payload=None, honeypot=None, started_at_ms=too_fast, bypass=True
        )  # type: ignore[arg-type]
    await captcha.verify(
        FakeRedis(), KEY, payload=None, honeypot=None, started_at_ms=long_ago(), bypass=True
    )  # type: ignore[arg-type]


def test_frontend_protocol_matches_library() -> None:
    """The in-house widget computes SHA-256(salt + n); this must agree with the library."""
    import hashlib  # noqa: PLC0415

    c = captcha.create_challenge(KEY, test_mode=True)
    for n in range(c["max_number"] + 1):
        if hashlib.sha256(f"{c['salt']}{n}".encode()).hexdigest() == c["challenge"]:
            break
    else:
        pytest.fail("challenge not solvable with the widget's algorithm")


def test_templates_escape_html_and_strip_control_chars() -> None:
    subject, text, html = render(
        "verify_email", {"name": "<script>alert(1)</script>\x00", "link": "https://x/y?a=1&b=2"}
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;b=2" in html
    assert "\x00" not in text
    assert subject == "Verify your DevSync email"


def test_unknown_template_raises() -> None:
    with pytest.raises(KeyError):
        render("nope", {})


@pytest.mark.parametrize(
    "address", ["a@b.com\r\nBcc: victim@x.com", "no-at-sign", "x" * 250 + "@b.com"]
)
def test_header_injection_and_bad_addresses_rejected(address: str) -> None:
    with pytest.raises(ValueError, match="invalid"):
        validate_address(address)


def test_message_has_text_and_html_parts() -> None:
    msg = build_message(
        make_settings(),
        "nadia@example.com",
        "reset_password",
        {"name": "Nadia", "link": "https://devsync/reset?token=t"},
    )
    assert msg["To"] == "nadia@example.com"
    assert msg.get_content_type() == "multipart/alternative"
    assert "\n" not in msg["Subject"]


def test_totp_window_and_replay() -> None:
    secret = pyotp.random_base32()
    now = datetime(2026, 10, 17, 6, 0, 15, tzinfo=UTC)
    totp = pyotp.TOTP(secret)
    current = totp.at(now)
    step = verify_totp_code(secret, current, now, None)
    assert step == int(now.timestamp()) // 30
    assert verify_totp_code(secret, current, now, step) is None  # replay blocked
    previous = totp.at(now - timedelta(seconds=30))
    assert verify_totp_code(secret, previous, now, None) is not None  # ±1 window
    too_old = totp.at(now - timedelta(seconds=90))
    assert verify_totp_code(secret, too_old, now, None) is None
    assert (
        verify_totp_code(secret, "000000" if current != "000000" else "111111", now, None) is None
    )


def test_backoff_grows() -> None:
    assert [backoff(n).total_seconds() for n in (1, 2, 3, 4)] == [30, 60, 120, 240]


def test_rate_limit_helpers() -> None:
    assert hash_key("1.2.3.4", "A@B.com") == hash_key("1.2.3.4", "a@b.com")
    assert len(hash_key("x")) == 32
    exc = RateLimited(0)
    assert exc.retry_after == 1
    assert exc.status_code == 429
