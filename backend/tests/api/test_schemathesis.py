"""Contract fuzzing with schemathesis (spec §16.1, §16.4, §16.5 step 11).

Three runs, all deterministic (hypothesis `derandomize`, no example database):

1. **Anonymous:** every operation in the OpenAPI document gets 200 generated requests (§16.5
   step 11); the run fails on any 5xx, any status code the operation doesn't declare, and any
   response that doesn't match its declared schema.
2. **Authenticated:** the same checks for every operation as a signed-in developer, client and
   admin (TOTP-verified), plus an anonymous browser that has a CSRF token — so unsafe requests
   get past the CSRF check and reach validation, authorization and the services instead of
   stopping at 403. Fewer examples per operation (`FUZZ_AUTH_EXAMPLES`, default 20) keep the
   gate's time budget; the role/operation grid is what widens the search.
3. **Stateful** (from Phase 5): a hand-written state machine drives the core loop — a client
   creates a project, plans it and publishes it; developers bid on it with schemathesis-generated
   bodies, edit, withdraw and bid again; another developer tries to touch a sealed bid. Every
   response is validated against the operation's schema, and the model checks the outcomes by
   status class (2xx vs 4xx), so changing an error code does not break it, a 5xx always does.

The OpenAPI document comes from an app in development mode (the only mode that serves it); the
authenticated and stateful runs send their requests to an app in test mode (test-only seed router
and CAPTCHA bypass) over the same Postgres and Redis.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import redis
import schemathesis
from hypothesis import HealthCheck, event, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    Bundle,
    RuleBasedStateMachine,
    consumes,
    invariant,
    rule,
    run_state_machine_as_test,
)
from schemathesis.python.asgi import ASGIClient
from schemathesis.specs.openapi.checks import positive_data_acceptance

from app.core.config import Environment
from app.main import create_app
from tests.helpers import ORIGIN, Api, SeededUser, stack_available, stack_settings

pytestmark = pytest.mark.fuzz

if not stack_available():
    pytest.skip("contract fuzzing runs in the test stack", allow_module_level=True)


os.environ.setdefault("DEVSYNC_ENV", "test")
APP = create_app(
    stack_settings(DEVSYNC_ENV=Environment.DEVELOPMENT, ALLOWED_HOSTS="testserver,localhost")
)
# Requests of the authenticated and stateful runs go here (seed router, CAPTCHA bypass).
TEST_APP = create_app(stack_settings())
schema = schemathesis.openapi.from_asgi("/api/v1/openapi.json", APP)
_REDIS = redis.Redis.from_url(os.environ["REDIS_URL"])

BASE_URL = "https://testserver"  # https, so the __Host- cookies are sent back
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ANON_EXAMPLES = int(os.environ.get("FUZZ_EXAMPLES", "200"))
AUTH_EXAMPLES = int(os.environ.get("FUZZ_AUTH_EXAMPLES", "20"))
STATEFUL_EXAMPLES = int(os.environ.get("FUZZ_STATEFUL_EXAMPLES", "8"))
STATEFUL_STEPS = int(os.environ.get("FUZZ_STATEFUL_STEPS", "12"))
AUTH_ROLES = ("DEVELOPER", "CLIENT", "ADMIN", "ANONYMOUS")

FUZZ_SETTINGS = {
    "deadline": None,
    "derandomize": True,  # the same examples on every run (spec §16.2)
    "database": None,
    "suppress_health_check": [HealthCheck.too_slow, HealthCheck.filter_too_much],
}


def _clear_rate_limits() -> None:
    """Rate limiting is tested on its own (tests/security/test_rate_limits.py); here every
    example must reach the contract."""
    for key in _REDIS.scan_iter("rl:*"):
        _REDIS.delete(key)


def _validate(
    case: schemathesis.Case,
    response: Any,
    excluded: list[schemathesis.CheckFunction] | None = None,
    **transport: Any,
) -> None:
    """Full validation, except that a 422 naming a fuzzed page cursor is the right answer to
    it: a cursor is an opaque token only the server issues, so a generated one is (almost) never
    valid. Any other response to such a request — and every request without a cursor — is
    validated in full."""
    assert response.status_code < 500, response.text
    fuzzed_cursor = isinstance(case.query, dict) and case.query.get("cursor") is not None
    refused = response.status_code == 422 and response.json()["error"].get("fields", {})
    if fuzzed_cursor and refused and "cursor" in refused:
        return
    case.validate_response(response, excluded_checks=excluded, transport_kwargs=transport or None)


# --------------------------------------------------------------------------- 1. anonymous


@schema.parametrize()
@settings(max_examples=ANON_EXAMPLES, **FUZZ_SETTINGS)
def test_api_contract(case: schemathesis.Case) -> None:
    _clear_rate_limits()
    response = case.call()
    _validate(case, response)


# --------------------------------------------------------------------------- 2. authenticated


# Signed-in requests get past CSRF to the server's own rules, several of which JSON Schema can't
# express (password policy and breached passwords, Bangladeshi mobiles, known skill ids, a close
# time in the future, a portfolio order listing every item once, …): a 422 naming the field is
# the right answer to such a schema-valid body, so "valid data is accepted" is not demanded here.
# Every other check (no 5xx, documented status codes, response schemas, headers, content type)
# applies in full; the stateful run below asserts acceptance where the input is known to be valid.
SIGNED_IN_EXCLUDED: list[schemathesis.CheckFunction] = [positive_data_acceptance]


class Browser:
    """A signed-in (or anonymous) browser on TEST_APP that schemathesis can send cases through:
    a requests-compatible session with the cookie jar, plus the CSRF header for unsafe methods.
    If a fuzzed request ends the session (logout, password change, revoked session), the next
    case signs in again — seeding a new account if the old one can no longer sign in."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.client = ASGIClient(TEST_APP, base_url=BASE_URL)
        self.client.__enter__()
        self.api = Api(self.client)  # type: ignore[arg-type] - same request interface
        self.user: SeededUser | None = None
        self.dirty = True

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    def ready(self) -> None:
        """Make sure the session is alive (after any unsafe request that might have ended it)."""
        if not self.dirty:
            return
        self.dirty = False
        if self.role == "ANONYMOUS":
            self.api.csrf_token()
            return
        if self.user is not None and self.api.get("/api/v1/me").status_code == 200:
            return
        _clear_rate_limits()
        if self.user is not None and self.api.login(self.user).status_code == 200:
            return
        self.user = self.api.sign_in_as(self.role)

    def headers(self, method: str) -> dict[str, str]:
        if method.upper() in SAFE_METHODS:
            return {}
        self.dirty = True
        token = self.client.cookies.get("__Host-ds_csrf") or self.api.csrf_token()
        return {"X-CSRF-Token": token, "Origin": ORIGIN}

    def send(self, case: schemathesis.Case) -> Any:
        self.ready()
        _clear_rate_limits()
        transport = {"session": self.client, "base_url": BASE_URL}
        response = case.call(**transport, headers=self.headers(case.method))
        _validate(case, response, SIGNED_IN_EXCLUDED, **transport)
        return response


@pytest.fixture(scope="module")
def browsers(migrated: str) -> Iterator[dict[str, Browser]]:
    """One browser per role for the whole module (sign-in hashes a password: do it once)."""
    made: dict[str, Browser] = {}
    try:
        yield {role: made.setdefault(role, Browser(role)) for role in AUTH_ROLES}
    finally:
        for browser in made.values():
            browser.close()


@pytest.mark.parametrize("role", AUTH_ROLES)
@schema.parametrize()
@settings(max_examples=AUTH_EXAMPLES, **FUZZ_SETTINGS)
def test_api_contract_signed_in(
    case: schemathesis.Case, role: str, browsers: dict[str, Browser]
) -> None:
    browsers[role].send(case)


# --------------------------------------------------------------------------- 3. stateful

PROJECTS = "/api/v1/projects"
PROJECT = "/api/v1/projects/{project_id}"
SLOTS = "/api/v1/projects/{project_id}/slots"
MILESTONES = "/api/v1/projects/{project_id}/milestones"
PUBLISH = "/api/v1/projects/{project_id}/publish"
VERIFY_PAYMENT = "/api/v1/me/payment-method/verify"
PLACE_BID = "/api/v1/projects/{project_id}/bids"
BID = "/api/v1/bids/{bid_id}"
MY_BIDS = "/api/v1/me/bids"
SKILLS = "/api/v1/skills"


def _ok(response: Any) -> bool:
    return 200 <= response.status_code < 300


def _items(body: Any) -> list[dict[str, Any]]:
    """A list response, bare or wrapped in a page object (`items`)."""
    if isinstance(body, dict):
        return list(body.get("items", []))
    return list(body)


class BidLifecycle(RuleBasedStateMachine):
    """Create → plan → publish → bid → edit → withdraw (→ bid again), with sealed bids."""

    projects = Bundle("projects")
    bids = Bundle("bids")

    def __init__(self) -> None:
        super().__init__()
        self.client = Browser("CLIENT")
        self.developers = [Browser("DEVELOPER"), Browser("DEVELOPER")]
        for browser in (self.client, *self.developers):
            browser.ready()
        skill = self._send(self.client, SKILLS, "GET").json()[0]
        self.skill_id = skill.get("skill_id") or skill["id"]
        self.skill_name = str(skill["name"])
        # Model: bid id → (developer index, project id, status) and each developer's active bid
        # per project (one ACTIVE bid per developer and project, DECISIONS D49).
        self.bid_state: dict[str, tuple[int, str, str]] = {}
        self.active: dict[tuple[int, str], str] = {}

    def teardown(self) -> None:
        for browser in (self.client, *self.developers):
            browser.close()

    def _send(
        self,
        browser: Browser,
        path: str,
        method: str,
        *,
        case: schemathesis.Case | None = None,
        **parts: Any,
    ) -> Any:
        """Send a case for `path`/`method` (built from `parts` unless given) and validate it."""
        if case is None:
            case = schema[path][method].Case(**parts)
        return browser.send(case)

    def _version(self, pid: str) -> int:
        return int(
            self._send(self.client, PROJECT, "GET", path_parameters={"project_id": pid}).json()[
                "version"
            ]
        )

    def _plan_write(self, path: str, pid: str, body: dict[str, Any]) -> Any:
        """Plan edits carry the current version in If-Match (optimistic concurrency)."""
        return self._send(
            self.client,
            path,
            "PUT",
            path_parameters={"project_id": pid},
            body=body,
            headers={"If-Match": str(self._version(pid))},
        )

    @rule(
        target=projects,
        budget=st.integers(5_000_000, 50_000_000),
        deadline=st.integers(20, 120),
    )
    def publish_project(self, budget: int, deadline: int) -> Any:
        created = self._send(
            self.client,
            PROJECTS,
            "POST",
            body={
                "title": "Online ordering system",
                "summary": "Order and track restaurant orders.",
                "budget_paisa": budget,
                "deadline_days": deadline,
                "team_size": 2,
            },
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        slots = self._plan_write(SLOTS, pid, {"slots": [{"skill_id": self.skill_id, "count": 2}]})
        assert _ok(slots), slots.text
        milestones = self._plan_write(
            MILESTONES,
            pid,
            {
                "milestones": [
                    {
                        "name": "Design",
                        "duration_days": 5,
                        "share_bp": 6000,
                        "skill_ids": [self.skill_id],
                    },
                    {
                        "name": "Build",
                        "duration_days": 10,
                        "share_bp": 4000,
                        "skill_ids": [self.skill_id],
                    },
                ]
            },
        )
        assert _ok(milestones), milestones.text
        assert _ok(self._send(self.client, VERIFY_PAYMENT, "POST"))
        published = self._send(
            self.client,
            PUBLISH,
            "POST",
            path_parameters={"project_id": pid},
            body={},
            headers={"If-Match": str(self._version(pid))},
        )
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "BIDDING"
        slot_id = slots.json()[0]["id"]
        # Both developers are newcomers, who bid on a passed role assessment for the role (role
        # assessment spec §8.3); a pass counts for every project with the same blueprint.
        for dev in self.developers:
            dev.ready()
            assert dev.user is not None
            _clear_rate_limits()
            dev.api.qualify_for_slot(dev.user, pid, slot_id, self.skill_name)
        return (pid, slot_id, deadline)

    @rule(target=bids, project=projects, dev=st.integers(0, 1), data=st.data())
    def place_bid(self, project: tuple[str, str, int], dev: int, data: st.DataObject) -> Any:
        pid, slot_id, deadline = project
        # A schemathesis-generated body, pointed at the real project and slot.
        case = data.draw(schema[PLACE_BID]["POST"].as_strategy())
        case.path_parameters = {"project_id": pid}
        body = case.body if isinstance(case.body, dict) else {}
        body["slot_id"] = slot_id
        body.pop("portfolio_item_ids", None)  # the bidder's own items only (tested elsewhere)
        case.body = body
        response = self._send(self.developers[dev], PLACE_BID, "POST", case=case)
        event(f"place bid → {response.status_code}")
        if (dev, pid) in self.active:
            assert not _ok(response), "a second active bid on the same project was accepted"
        if response.status_code == 201:
            bid_id = response.json()["id"]
            self.bid_state[bid_id] = (dev, pid, "ACTIVE")
            self.active[(dev, pid)] = bid_id
            return bid_id
        # A valid bid on an open project by a developer without one there must be accepted.
        days, price = body.get("days_needed"), body.get("price_paisa")
        valid = _is_int(days) and 1 <= days <= deadline and _is_int(price) and 0 < price <= 10**10
        if (dev, pid) not in self.active and valid and _plain_text(body):
            pytest.fail(f"valid bid refused: {response.status_code} {response.text}")
        return str(uuid.uuid4())  # an id that never existed: later rules must get 4xx for it

    @rule(bid=bids, price=st.integers(1, 10_000_000_000), days=st.integers(1, 365))
    def edit_bid(self, bid: str, price: int, days: int) -> None:
        state = self.bid_state.get(bid)
        dev = state[0] if state else 0
        response = self._send(
            self.developers[dev],
            BID,
            "PATCH",
            path_parameters={"bid_id": bid},
            body={"price_paisa": price, "days_needed": days},
        )
        event(f"edit {state[2] if state else 'unknown'} bid → {response.status_code}")
        if state is None or state[2] != "ACTIVE":
            assert not _ok(response), "an unknown or withdrawn bid was edited"
        else:
            assert response.status_code == 200, response.text
            assert response.json()["price_paisa"] == price

    @rule(bid=bids)
    def foreign_developer_cannot_touch_a_bid(self, bid: str) -> None:
        state = self.bid_state.get(bid)
        other = 1 - (state[0] if state else 0)
        path = {"bid_id": bid}
        edit = self._send(
            self.developers[other], BID, "PATCH", path_parameters=path, body={"days_needed": 9}
        )
        withdraw = self._send(self.developers[other], BID, "DELETE", path_parameters=path)
        assert not _ok(edit), "a developer edited someone else's bid"
        assert not _ok(withdraw), "a developer withdrew someone else's bid"

    @rule(bid=consumes(bids))
    def withdraw_bid(self, bid: str) -> None:
        state = self.bid_state.get(bid)
        dev = state[0] if state else 0
        response = self._send(self.developers[dev], BID, "DELETE", path_parameters={"bid_id": bid})
        event(f"withdraw {state[2] if state else 'unknown'} bid → {response.status_code}")
        if state is None or state[2] != "ACTIVE":
            assert not _ok(response), "an unknown or withdrawn bid was withdrawn"
            return
        assert _ok(response), response.text
        self.bid_state[bid] = (state[0], state[1], "WITHDRAWN")
        self.active.pop((state[0], state[1]), None)
        again = self._send(self.developers[dev], BID, "DELETE", path_parameters={"bid_id": bid})
        assert not _ok(again), "a withdrawn bid was withdrawn twice"

    @invariant()
    def my_bids_match_the_model(self) -> None:
        """Each developer sees exactly their own active bids — never another developer's."""
        if not self.bid_state:
            return
        for dev, browser in enumerate(self.developers):
            listed = _items(self._send(browser, MY_BIDS, "GET").json())
            mine = {b["id"]: b["status"] for b in listed if b["id"] in self.bid_state}
            for bid_id, status in mine.items():
                owner, _pid, model_status = self.bid_state[bid_id]
                assert owner == dev, "a developer's list shows another developer's bid"
                assert (status == "ACTIVE") == (model_status == "ACTIVE"), (bid_id, status)
            expected = {b for b, (o, _p, s) in self.bid_state.items() if o == dev and s == "ACTIVE"}
            assert expected <= {b for b, s in mine.items() if s == "ACTIVE"}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _plain_text(body: dict[str, Any]) -> bool:
    """Free text the server keeps as is: control characters are stripped and limits count code
    points after NFC, so only plain printable text is predictable enough to demand a 201."""
    for field in ("proposal", "expected_contribution"):
        value = body.get(field, "")
        if not isinstance(value, str) or not value.isascii() or not value.isprintable():
            return False
    hours = body.get("hours_per_week_committed")
    # The server checks hours against the developer's free time (§9.17); new developers have 20.
    return hours is None or (_is_int(hours) and 1 <= hours <= 20)


def test_bid_lifecycle_state_machine(migrated: str) -> None:
    run_state_machine_as_test(
        BidLifecycle,
        settings=settings(
            max_examples=STATEFUL_EXAMPLES,
            stateful_step_count=STATEFUL_STEPS,
            **FUZZ_SETTINGS,
        ),
    )
