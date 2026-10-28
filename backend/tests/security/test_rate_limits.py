"""Every row of the §14.8 rate-limit table, through the real API (spec §16.4 "Rate limits").

For each scope that has an endpoint today, one test proves the three properties §16.4 asks for:

1. **Limit reached → 429** with the `RATE_LIMITED` error and a `Retry-After` within the window
   (every request before the limit is answered normally, never 429);
2. **Per-key isolation:** another key (another user, another email or another address, as the
   table's "Key" column says) is not blocked by the first key's exhaustion;
3. **Window reset:** once the window has passed, the first key is served again.

Time passing is simulated by ageing the limiter's own Redis entries (each hit is a member of a
sorted set scored by its time in ms; the Lua script drops members older than the window), so a
one-day window resets in milliseconds and nothing else (sessions, OTP expiry) moves. The real
clock version of the same check is `tests/integration/test_sessions_ratelimit.py`.

Rows whose feature doesn't exist yet are listed in `PENDING_SCOPES` with the phase that builds
them; `test_every_wired_scope_has_a_behaviour_test` fails as soon as one of them is wired into
the app without a test here, and the configured values of every row are checked against the
table in `tests/unit/test_rate_limit_table.py`.
"""

from __future__ import annotations

import io
import os
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
import redis
from fastapi.testclient import TestClient
from PIL import Image

from app.core import clock
from app.main import create_app
from tests.helpers import STRONG_PASSWORD, Api, stack_settings, unique_email, unique_phone

pytestmark = [pytest.mark.security, pytest.mark.api]

APP_DIR = Path(__file__).resolve().parents[2] / "app"
MINUTE, HOUR, DAY = 60, 3600, 86_400
# Sending or resending a code is a public form, so it carries the bot check (D68, §14.16).
BOT_OK = {"captcha": "test-bypass"}

# §14.8 rows that have no endpoint yet → the phase that builds (and must test) them.
PENDING_SCOPES = {
    "formation_run": "Phase 7 (formation runs; also 1 concurrent per project)",
    "coding_submit": "Phase 13 (coding challenges)",
    "coding_practice": "Phase 13 (coding challenges, practice mode)",
    "comment": "Phase 9 (workspace comments and discussion)",
    "review": "Phase 11 (reviews)",
    "dispute": "Phase 12 (disputes)",
    "github_sync": "Phase 13 (GitHub manual sync)",
    "data_export": "Phase 12 (data export)",
}
# Scopes with a behaviour test in this module (scope → test name).
TESTED_SCOPES = {
    "api_authenticated": "test_global_authenticated_limit_is_per_user",
    "api_anonymous": "test_global_anonymous_limit_is_per_address",
    "login": "test_login_limits_per_minute_and_hour_by_address_and_email",
    "registration": "test_registration_limit_is_per_address",
    "otp_send": "test_otp_send_limits_per_minute_and_hour",
    "otp_verify": "test_otp_verify_limit_and_attempts_per_code",
    "password_reset": "test_password_reset_limit",
    "email_resend": "test_email_resend_limit_is_per_user",
    "bid": "test_bid_create_and_edit_limit_is_per_user",
    "project_create": "test_project_create_limit_is_per_day_per_user",
    "test_start": "test_skill_test_start_limit_is_per_user",
    "upload": "test_upload_limit_is_per_user",
    # Role assessment (role assessment spec §9).
    "assessment_read": "test_assessment_read_limit_is_per_user",
    "assessment_start": "test_assessment_start_limit_is_per_user",
    "assessment_resume": "test_assessment_resume_limit_is_per_user",
    "assessment_answer": "test_assessment_answer_limit_is_per_user",
    "assessment_finish": "test_assessment_finish_limit_is_per_user",
    "assessment_focus": "test_assessment_focus_limit_is_per_user",
    "assessment_heartbeat": "test_assessment_heartbeat_limit_is_per_user",
    "assessment_history": "test_assessment_history_limit_is_per_user",
    "admin": "test_admin_limit_is_per_user",
    "admin_assessment_action": "test_admin_assessment_action_limit_is_per_user",
    # Not §14.8 rows, but wired limits all the same (covered elsewhere).
    "totp": "tests/security/test_admin_totp.py",
    "captcha_challenge": "tests/security/test_login_sessions.py",
    "public_stats": "tests/api/test_public.py",
    "client_errors": "tests/api/test_public.py::test_client_errors_are_rate_limited",
}


# --------------------------------------------------------------------------- helpers


def _redis() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"])


def _clear(scope: str | None = None) -> None:
    """Forget the counters of one scope (or all of them)."""
    r = _redis()
    try:
        for key in r.scan_iter(f"rl:{scope or '*'}:*"):
            r.delete(key)
    finally:
        r.close()


def _age(scope: str, seconds: int) -> None:
    """Make every recorded hit of `scope` `seconds` older, as if that much time had passed."""
    r = _redis()
    try:
        for key in r.scan_iter(f"rl:{scope}:*"):
            hits = cast("list[tuple[bytes, float]]", r.zrange(key, 0, -1, withscores=True))
            if hits:
                r.zadd(key, {member: score - seconds * 1000 for member, score in hits})
    finally:
        r.close()


def _assert_limited(response: Any, window: int) -> None:
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    retry_after = int(response.headers["Retry-After"])
    assert 1 <= retry_after <= window


def _fill(send: Callable[[], Any], limit: int) -> list[int]:
    """Send `limit` requests; none of them may be refused by the limiter."""
    statuses = [send().status_code for _ in range(limit)]
    assert 429 not in statuses, statuses
    return statuses


@pytest.fixture
def api_at(migrated: str) -> Iterator[Callable[[str], Api]]:
    """Factory: an independent HTTPS client whose requests come from the given address."""
    with ExitStack() as stack:

        def make(address: str) -> Api:
            client = TestClient(
                create_app(stack_settings()),
                base_url="https://testserver",
                client=(address, 50000),
            )
            return Api(stack.enter_context(client))

        yield make


def _register(api: Api, email: str | None = None, phone: str | None = None) -> Any:
    return api.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Nadia Rahman",
            "email": email or unique_email(),
            "phone": phone or unique_phone(),
            "password": STRONG_PASSWORD,
            "role": "DEVELOPER",
            "accept_terms": True,
            "captcha": "test-bypass",
        },
    )


def _pending(api: Api) -> tuple[str, str]:
    """Register and sign in (PENDING); returns (email, phone)."""
    email, phone = unique_email(), unique_phone()
    assert _register(api, email, phone).status_code == 202
    r = api.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert r.status_code == 200, r.text
    _clear()  # the set-up requests must not use up the limits under test
    return email, phone


def _otp(api: Api, phone: str) -> str:
    message = api.get("/api/v1/__test__/sms", params={"phone": phone}).json()["message"]
    assert message
    return str(message).rsplit(" ", 1)[-1]


def _skill_id(api: Api) -> str:
    skills = api.get("/api/v1/skills").json()
    return str(skills[0].get("skill_id") or skills[0]["id"])


PROJECT = {
    "title": "Online ordering system",
    "summary": "Order and track restaurant orders.",
    "budget_paisa": 12_000_000,
    "deadline_days": 30,
    "team_size": 2,
}


def _published_project(api: Api) -> tuple[str, str]:
    """As a signed-in client: a BIDDING project; returns (project_id, slot_id)."""
    sid = _skill_id(api)
    pid = api.post("/api/v1/projects", json=PROJECT).json()["id"]
    slots = api.put(
        f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": 2}]}
    ).json()
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    )
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204
    published = api.post(f"/api/v1/projects/{pid}/publish", json={})
    assert published.status_code == 200, published.text
    return pid, slots[0]["id"]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (15, 118, 110)).save(buf, "PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- meta


def _scopes_used_by_the_app() -> set[str]:
    """Scope names passed to `rate_limit("…")` or `RateLimiter(...).hit("…", …)` in app/."""
    used: set[str] = set()
    pattern = re.compile(r"""(?:rate_limit\(|\.hit\(\s*)["']([a-z_]+)["']""")
    for path in APP_DIR.rglob("*.py"):
        used.update(pattern.findall(path.read_text(encoding="utf-8")))
    return used


def test_every_wired_scope_has_a_behaviour_test() -> None:
    used = _scopes_used_by_the_app() | {"api_authenticated", "api_anonymous"}  # middleware
    untested = sorted(used - set(TESTED_SCOPES))
    assert not untested, f"rate-limited scopes without a §16.4 test: {untested}"
    wired_but_pending = sorted(used & set(PENDING_SCOPES))
    assert not wired_but_pending, f"move to TESTED_SCOPES with a test: {wired_but_pending}"
    for scope, test in TESTED_SCOPES.items():
        if test.startswith("test_"):
            assert test in globals(), f"{scope}: {test} is missing"


def test_scope_detection_finds_known_scopes() -> None:
    """Guards the guard: the scan must see scopes wired in both styles."""
    used = _scopes_used_by_the_app()
    assert {"login", "registration", "bid", "project_create", "upload", "totp"} <= used


# --------------------------------------------------------------------------- global limits


def test_global_authenticated_limit_is_per_user(api: Api, api2: Api) -> None:
    """Authenticated API (global): 120/min, keyed by user."""
    api.sign_in_as("CLIENT")
    api2.sign_in_as("CLIENT")
    _clear()
    _fill(lambda: api.get("/api/v1/me"), 120)
    _assert_limited(api.get("/api/v1/me"), MINUTE)
    assert api2.get("/api/v1/me").status_code == 200  # another user, same address
    _age("api_authenticated", MINUTE)
    assert api.get("/api/v1/me").status_code == 200


def test_global_anonymous_limit_is_per_address(api_at: Callable[[str], Api]) -> None:
    """Unauthenticated API (global): 60/min, keyed by IP."""
    first, second = api_at("198.51.100.10"), api_at("198.51.100.11")
    _clear()
    _fill(lambda: first.get("/api/v1/auth/csrf"), 60)
    _assert_limited(first.get("/api/v1/auth/csrf"), MINUTE)
    assert second.get("/api/v1/auth/csrf").status_code == 204
    _age("api_anonymous", MINUTE)
    assert first.get("/api/v1/auth/csrf").status_code == 204


# --------------------------------------------------------------------------- accounts


def _drop_login_delays() -> None:
    """The progressive delay and CAPTCHA counters are separate controls (tested in
    test_login_sessions.py); clear them so only the rate limit decides here."""
    r = _redis()
    try:
        for key in [*r.scan_iter("auth:delay:*"), *r.scan_iter("auth:fail:*")]:
            r.delete(key)
    finally:
        r.close()


def test_login_limits_per_minute_and_hour_by_address_and_email(api: Api) -> None:
    """Login: 5/min and 20/hour, keyed by IP + email."""
    email = unique_email()

    def attempt(address: str = email) -> Any:
        return api.post(
            "/api/v1/auth/login",
            json={"email": address, "password": "wrong password 99", "captcha": "test-bypass"},
        )

    _fill(attempt, 5)
    _assert_limited(attempt(), MINUTE)
    _drop_login_delays()
    assert attempt(unique_email()).status_code == 401  # another email from the same address
    # The minute window passes three more times: 20 attempts in the hour.
    for _ in range(3):
        _age("login", MINUTE + 1)
        _drop_login_delays()
        _fill(attempt, 5)
    _age("login", MINUTE + 1)
    _drop_login_delays()
    limited = attempt()
    _assert_limited(limited, HOUR)
    assert int(limited.headers["Retry-After"]) > MINUTE  # the hourly rule, not the minute one
    _age("login", HOUR)
    _drop_login_delays()
    assert attempt().status_code == 401


def test_registration_limit_is_per_address(api_at: Callable[[str], Api]) -> None:
    """Registration: 5/hour, keyed by IP."""
    first, second = api_at("198.51.100.20"), api_at("198.51.100.21")
    _clear()
    assert [_register(first).status_code for _ in range(5)] == [202] * 5
    _assert_limited(_register(first), HOUR)
    assert _register(second).status_code == 202
    _age("registration", HOUR)
    assert _register(first).status_code == 202


def test_otp_send_limits_per_minute_and_hour(
    api: Api, api2: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OTP send: 1/60 s and 5/hour, keyed by phone (the signed-in user's) + IP. The service's
    own 60-second resend cooldown reads the app clock, so the clock moves with the counters."""
    _, phone = _pending(api)
    _pending(api2)
    start = clock.get_clock().now()
    elapsed = 0

    def later(seconds: int) -> None:
        """Age the counters by `seconds`; the app clock moves at most past the cooldown (a
        full hour on the app clock would also end the session through its idle timeout)."""
        nonlocal elapsed
        elapsed += min(seconds, MINUTE + 1)
        monkeypatch.setattr(clock, "_clock", clock.FrozenClock(start + timedelta(seconds=elapsed)))
        _age("otp_send", seconds)

    later(MINUTE + 1)  # past the code sent at registration
    assert api.post("/api/v1/auth/otp/send", json=BOT_OK).status_code == 204
    _assert_limited(api.post("/api/v1/auth/otp/send", json=BOT_OK), MINUTE)  # 1 per 60 s
    later(MINUTE + 1)
    # another user's phone
    assert api2.post("/api/v1/auth/otp/send", json=BOT_OK).status_code == 204
    for _ in range(4):
        assert api.post("/api/v1/auth/otp/send", json=BOT_OK).status_code == 204
        later(MINUTE + 1)
    limited = api.post("/api/v1/auth/otp/send", json=BOT_OK)  # a 6th code within the hour
    _assert_limited(limited, HOUR)
    assert int(limited.headers["Retry-After"]) > MINUTE
    later(HOUR)
    assert api.post("/api/v1/auth/otp/send", json=BOT_OK).status_code == 204
    assert _otp(api, phone)


def test_otp_verify_limit_and_attempts_per_code(
    api: Api, api2: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OTP verify: 5 attempts per code (the code then stops working; a new code works), and
    the endpoint's own limit (10/hour per user + IP) answers 429 beyond that."""
    _, phone = _pending(api)
    _pending(api2)
    code = _otp(api, phone)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert api.post("/api/v1/auth/otp/verify", json={"code": wrong}).status_code == 400
    burnt = api.post("/api/v1/auth/otp/verify", json={"code": code})
    assert burnt.status_code == 400  # five wrong attempts used the code up
    # Four more requests reach the endpoint's own limit of 10 per hour.
    _fill(lambda: api.post("/api/v1/auth/otp/verify", json={"code": wrong}), 4)
    _assert_limited(api.post("/api/v1/auth/otp/verify", json={"code": wrong}), HOUR)
    assert api2.post("/api/v1/auth/otp/verify", json={"code": wrong}).status_code == 400
    _age("otp_verify", HOUR)
    _age("otp_send", HOUR)
    # Past the service's 60-second resend cooldown (app clock).
    later = clock.FrozenClock(clock.get_clock().now() + timedelta(seconds=MINUTE + 1))
    monkeypatch.setattr(clock, "_clock", later)
    assert api.post("/api/v1/auth/otp/send", json=BOT_OK).status_code == 204  # a fresh code
    fresh = _otp(api, phone)
    assert api.post("/api/v1/auth/otp/verify", json={"code": fresh}).status_code == 204


def test_password_reset_limit(api_at: Callable[[str], Api]) -> None:
    """Password reset request: 3/hour. The app keys it by IP (+ user when signed in), which is
    stricter per address than the table's "email + IP": another address is not blocked."""
    first, second = api_at("198.51.100.30"), api_at("198.51.100.31")
    _clear()

    def forgot(api: Api) -> Any:
        return api.post(
            "/api/v1/auth/password/forgot", json={"email": unique_email(), "captcha": "test-bypass"}
        )

    assert [forgot(first).status_code for _ in range(3)] == [202] * 3
    _assert_limited(forgot(first), HOUR)
    assert forgot(second).status_code == 202
    _age("password_reset", HOUR)
    assert forgot(first).status_code == 202


def test_email_resend_limit_is_per_user(api: Api, api2: Api) -> None:
    """Email verification resend: 3/hour, keyed by user."""
    _pending(api)
    _pending(api2)
    # A CAPTCHA field is accepted (and ignored while the endpoint doesn't ask for one).
    body = {"captcha": "test-bypass"}
    _fill(lambda: api.post("/api/v1/auth/email/resend", json=body), 3)
    _assert_limited(api.post("/api/v1/auth/email/resend", json=body), HOUR)
    assert api2.post("/api/v1/auth/email/resend", json=body).status_code == 204
    _age("email_resend", HOUR)
    assert api.post("/api/v1/auth/email/resend", json=body).status_code == 204


# --------------------------------------------------------------------------- marketplace


def test_bid_create_and_edit_limit_is_per_user(api: Api, api2: Api) -> None:
    """Bid create/edit: 20/hour, keyed by user (placing and editing share the budget)."""
    api.sign_in_as("CLIENT")
    pid, slot_id = _published_project(api)
    skill = api.get("/api/v1/skills").json()[0]["name"]
    for client in (api, api2):  # newcomers allowed to bid (role assessment spec §8.3)
        client.qualify_for_slot(client.sign_in_as("DEVELOPER"), pid, slot_id, skill)
    _clear()
    created = api.post(
        f"/api/v1/projects/{pid}/bids",
        json={"slot_id": slot_id, "price_paisa": 1_800_000, "days_needed": 20},
    )
    assert created.status_code == 201, created.text
    bid_id = created.json()["id"]

    def edit(price: list[int] = [1_700_000]) -> Any:  # noqa: B006 - a deliberate counter
        price[0] -= 1_000
        return api.patch(f"/api/v1/bids/{bid_id}", json={"price_paisa": price[0]})

    assert set(_fill(edit, 19)) == {200}
    _assert_limited(edit(), HOUR)
    other = api2.post(
        f"/api/v1/projects/{pid}/bids",
        json={"slot_id": slot_id, "price_paisa": 1_900_000, "days_needed": 20},
    )
    assert other.status_code == 201, other.text
    _age("bid", HOUR)
    assert edit().status_code == 200


def test_project_create_limit_is_per_day_per_user(api: Api, api2: Api) -> None:
    """Project create: 10/day, keyed by user."""
    api.sign_in_as("CLIENT")
    api2.sign_in_as("CLIENT")
    _clear()
    assert set(_fill(lambda: api.post("/api/v1/projects", json=PROJECT), 10)) == {201}
    limited = api.post("/api/v1/projects", json=PROJECT)
    _assert_limited(limited, DAY)
    assert int(limited.headers["Retry-After"]) > HOUR
    assert api2.post("/api/v1/projects", json=PROJECT).status_code == 201
    _age("project_create", DAY)
    assert api.post("/api/v1/projects", json=PROJECT).status_code == 201


def test_skill_test_start_limit_is_per_user(api: Api, api2: Api) -> None:
    """Skill test attempts start: 10/hour, keyed by user. Starts after the first answer 409
    (one open attempt at a time) but still count, so retrying can't be used to probe."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    tests = api.get("/api/v1/skill-tests").json()
    assert tests, "seeded skill tests expected"
    test_id = tests[0]["id"]
    _clear()

    def start(client: Api = api) -> Any:
        return client.post(f"/api/v1/skill-tests/{test_id}/attempts")

    statuses = _fill(start, 10)
    assert statuses[0] == 201
    _assert_limited(start(), HOUR)
    assert start(api2).status_code == 201
    _age("test_start", HOUR)
    assert start().status_code != 429


def test_upload_limit_is_per_user(api: Api, api2: Api) -> None:
    """File uploads: 20/hour, keyed by user (refused uploads count too)."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    items = [
        api.post("/api/v1/me/portfolio", json={"title": f"App {n}"}).json()["id"] for n in range(5)
    ]
    other_item = api2.post("/api/v1/me/portfolio", json={"title": "Other"}).json()["id"]
    _clear()
    image = _png()

    def upload(n: int, client: Api = api, item: str | None = None) -> Any:
        target = item or items[n % len(items)]  # at most 5 images per item
        return client.post(
            f"/api/v1/me/portfolio/{target}/images",
            files={"file": ("shot.png", image, "image/png")},
        )

    statuses = [upload(n).status_code for n in range(20)]
    assert 429 not in statuses
    assert statuses.count(201) == 20
    _assert_limited(upload(20), HOUR)
    assert upload(0, api2, other_item).status_code == 201
    _age("upload", HOUR)
    assert upload(21).status_code != 429


# --------------------------------------------------------------------------- role assessment


def _per_user(
    scope: str, send: Callable[[], Any], other: Callable[[], Any], limit: int, window: int
) -> None:
    """`limit` requests pass, the next is 429 with Retry-After, another user is unaffected, and
    the window passing lets the first user in again. The global per-user limit (120/min, tested
    above) is reset as it goes — every 50 sends, as a POST costs two requests (the CSRF token,
    then the call) — so every 429 here comes from `scope` itself."""
    _clear()
    for done in range(0, limit, 50):
        _fill(send, min(50, limit - done))
        _clear("api_authenticated")
    _assert_limited(send(), window)
    assert other().status_code != 429
    _age(scope, window)
    _clear("api_authenticated")
    assert send().status_code != 429


def _ids() -> tuple[str, str]:
    return str(uuid.uuid4()), str(uuid.uuid4())


def test_assessment_read_limit_is_per_user(api: Api, api2: Api) -> None:
    """Assessment status, attempt and result reads: 120/min per user (spec §9)."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    pid, sid = _ids()
    path = f"/api/v1/projects/{pid}/slots/{sid}/assessment"
    _per_user("assessment_read", lambda: api.get(path), lambda: api2.get(path), 120, MINUTE)


def test_assessment_start_limit_is_per_user(api: Api, api2: Api) -> None:
    """Starting a role assessment: 10/hour per user."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    pid, sid = _ids()
    path = f"/api/v1/projects/{pid}/slots/{sid}/assessment/attempts"
    body = {"consent": True, "rules_version": 1}
    _per_user(
        "assessment_start",
        lambda: api.post(path, json=body),
        lambda: api2.post(path, json=body),
        10,
        HOUR,
    )


def test_assessment_resume_limit_is_per_user(api: Api, api2: Api) -> None:
    """Resuming (a new window token): 20/hour per user."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    path = f"/api/v1/assessment-attempts/{uuid.uuid4()}/resume"
    _per_user("assessment_resume", lambda: api.post(path), lambda: api2.post(path), 20, HOUR)


def test_assessment_answer_limit_is_per_user(api: Api, api2: Api) -> None:
    """Answers: 120/min per user."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    path = f"/api/v1/assessment-attempts/{uuid.uuid4()}/answer"
    body = {"question_id": str(uuid.uuid4()), "choice": 0}
    _per_user(
        "assessment_answer",
        lambda: api.post(path, json=body),
        lambda: api2.post(path, json=body),
        120,
        MINUTE,
    )


def test_assessment_finish_limit_is_per_user(api: Api, api2: Api) -> None:
    """Finishing early: 10/hour per user."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    path = f"/api/v1/assessment-attempts/{uuid.uuid4()}/finish"
    _per_user("assessment_finish", lambda: api.post(path), lambda: api2.post(path), 10, HOUR)


def test_assessment_focus_limit_is_per_user(api: Api, api2: Api) -> None:
    """Focus events: 60/min per user."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    path = f"/api/v1/assessment-attempts/{uuid.uuid4()}/focus-events"
    body = {"seq": 1, "type": "WINDOW_BLUR"}
    _per_user(
        "assessment_focus",
        lambda: api.post(path, json=body),
        lambda: api2.post(path, json=body),
        60,
        MINUTE,
    )


def test_assessment_heartbeat_limit_is_per_user(api: Api, api2: Api) -> None:
    """Heartbeats: 10/min per user (the client sends one every 15 s)."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    path = f"/api/v1/assessment-attempts/{uuid.uuid4()}/heartbeat"
    body = {"visible": True, "fullscreen": True}
    _per_user(
        "assessment_heartbeat",
        lambda: api.post(path, json=body),
        lambda: api2.post(path, json=body),
        10,
        MINUTE,
    )


def test_assessment_history_limit_is_per_user(api: Api, api2: Api) -> None:
    """My role assessments: 60/min per user."""
    api.sign_in_as("DEVELOPER")
    api2.sign_in_as("DEVELOPER")
    path = "/api/v1/me/role-assessments"
    _per_user("assessment_history", lambda: api.get(path), lambda: api2.get(path), 60, MINUTE)


def test_admin_limit_is_per_user(api: Api, api2: Api) -> None:
    """Admin reads: 300/min per admin."""
    api.sign_in_as("ADMIN")
    api2.sign_in_as("ADMIN")
    path = "/api/v1/admin/question-bank?limit=1"
    _per_user("admin", lambda: api.get(path), lambda: api2.get(path), 300, MINUTE)


def test_admin_assessment_action_limit_is_per_user(api: Api, api2: Api) -> None:
    """Admin void and accommodations: 30/hour per admin (each also needs a step-up)."""
    api.sign_in_as("ADMIN")
    api2.sign_in_as("ADMIN")
    path = f"/api/v1/admin/users/{uuid.uuid4()}/accommodation"
    body = {"extra_time_pct": 25}
    _per_user(
        "admin_assessment_action",
        lambda: api.post(path, json=body),
        lambda: api2.post(path, json=body),
        30,
        HOUR,
    )
