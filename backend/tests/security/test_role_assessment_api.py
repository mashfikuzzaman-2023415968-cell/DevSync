"""Role assessment API and security behaviour (role assessment spec §6-§9, §12, §15-§17).

Real projects are published through the API; developers are newcomers unless a test says
otherwise. The test-only routes (`/__test__/...`) seed reputation, skills, passed or failed
attempts and read the answer key; they are not part of the product API and their responses are
never scanned for answer data. Everything a candidate or a client can reach IS scanned: every
JSON response made through `call()` is checked for answer or correctness fields.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Environment
from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import ORIGIN, Api, SeededUser, stack_available, stack_settings
from tests.helpers import wait_for_next_totp_window as next_totp

pytestmark = [pytest.mark.security, pytest.mark.api]

BASE = "/api/v1"
FORBIDDEN_KEYS = {
    "correct_index",
    "correct",
    "answer",
    "answers",
    "explanation",
    "verification",
    "is_correct",
}
QUESTION_KEYS = {"id", "index", "total", "text", "code_snippet", "options", "competency"}
UNKNOWN = "00000000-0000-4000-8000-000000000000"
SEEN: list[tuple[str, Any]] = []  # every candidate/client-facing JSON response of this process


@pytest.fixture
def api3(migrated: str) -> Iterator[Api]:
    """A third independent browser (the admin, while `api` is the client and `api2` a developer)."""
    if not stack_available():
        pytest.skip("needs the test compose stack")
    with TestClient(create_app(stack_settings()), base_url=ORIGIN) as c:
        yield Api(c)


# ------------------------------------------------------------------------------ scanning


def walk_keys(payload: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    """(path, key) of every key anywhere in a JSON payload."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield path, str(key)
            yield from walk_keys(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, value in enumerate(payload):
            yield from walk_keys(value, f"{path}[{i}]")


def assert_no_answer_data(payload: Any, where: str = "") -> None:
    # A 422 names the input fields it rejected (`error.fields`); that is the caller's own input.
    bad = [
        (p, k)
        for p, k in walk_keys(payload)
        if k in FORBIDDEN_KEYS and not p.endswith(".error.fields")
    ]
    assert not bad, f"answer data leaked {where}: {bad}"


def strings(payload: Any) -> Iterator[str]:
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, dict):
        for value in payload.values():
            yield from strings(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from strings(value)


def call(api: Api, method: str, path: str, *, token: str | None = None, **kw: Any) -> Any:
    """A request whose JSON response is scanned for answer data before the test sees it."""
    headers = dict(kw.pop("headers", {}) or {})
    if token is not None:
        headers["X-Attempt-Token"] = token
    r = api.request(method, path, headers=headers, **kw)
    if "application/json" in r.headers.get("content-type", ""):
        body = r.json()
        assert_no_answer_data(body, f"in {method} {path} -> {r.status_code}")
        SEEN.append((f"{method} {path}", body))
    return r


def code(r: Any) -> str:
    return str(r.json()["error"]["code"])


def when(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ------------------------------------------------------------------------------- set-up


def skill_ids(api: Api) -> dict[str, str]:
    return {s["name"]: s["id"] for s in api.get(f"{BASE}/skills").json()}


def publish(
    api: Api, skills: tuple[str, ...] = ("React",), *, team: int = 2
) -> tuple[str, dict[str, str]]:
    """Create, plan, pay and publish a project as the signed-in client; (project_id, slot by
    skill name). The text mentions what the role is about so the blueprint is the same each time."""
    ids = skill_ids(api)
    chosen = [ids[n] for n in skills]
    pid = api.post(
        f"{BASE}/projects",
        json={
            "title": "Customer dashboard",
            "summary": "A dashboard with sign in, roles, forms and charts for a restaurant chain.",
            "budget_paisa": 12_000_000,
            "deadline_days": 30,
            "team_size": team,
        },
    ).json()["id"]
    r = api.put(
        f"{BASE}/projects/{pid}/slots",
        json={"slots": [{"skill_id": s, "count": 1 if len(chosen) > 1 else team} for s in chosen]},
    )
    assert r.status_code == 200, r.text
    by_skill = {s["skill_id"]: s["id"] for s in r.json()}
    r = api.put(
        f"{BASE}/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": chosen},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": chosen},
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert api.post(f"{BASE}/me/payment-method/verify").status_code == 204
    assert api.post(f"{BASE}/projects/{pid}/publish", json={}).status_code == 200
    return pid, {n: by_skill[ids[n]] for n in skills}


_SHARED: dict[str, tuple[str, str]] = {}


def shared_project(api: Api, skill: str = "React") -> tuple[str, str]:
    """One published project per skill for the whole run (each test brings its own developers).
    Signs `api` in as the project's client the first time; callers sign in as who they need."""
    if skill not in _SHARED:
        api.sign_in_as("CLIENT")
        pid, slots = publish(api, (skill,))
        _SHARED[skill] = (pid, slots[skill])
    return _SHARED[skill]


def add_skill(api: Api, dev: SeededUser, name: str, score: str = "0.900") -> None:
    r = api.post(
        f"{BASE}/__test__/developers/{dev.user_id}/skill-evidence",
        json={"skill": name, "score": score},
    )
    assert r.status_code == 204, r.text


def newcomer(api: Api, skill: str = "React") -> SeededUser:
    """A signed-in newcomer with the skill on the profile."""
    dev = api.sign_in_as("DEVELOPER")
    add_skill(api, dev, skill)
    return dev


def slot_path(pid: str, slot: str, tail: str = "") -> str:
    return f"{BASE}/projects/{pid}/slots/{slot}/assessment{tail}"


def status_of(api: Api, pid: str, slot: str) -> dict[str, Any]:
    r = call(api, "GET", slot_path(pid, slot))
    assert r.status_code == 200, r.text
    return dict(r.json())


def start(
    api: Api, pid: str, slot: str, *, consent: bool = True, version: int | None = None, **kw: Any
) -> Any:
    if version is None:
        version = int(status_of(api, pid, slot)["rules_version"])
    return call(
        api,
        "POST",
        slot_path(pid, slot, "/attempts"),
        json={"consent": consent, "rules_version": version},
        **kw,
    )


def begin(api: Api, pid: str, slot: str) -> tuple[dict[str, Any], str]:
    """Start a fresh attempt (201); (attempt, window token)."""
    r = start(api, pid, slot)
    assert r.status_code == 201, r.text
    body = r.json()
    return body, body["attempt_token"]


def attempt_path(attempt_id: str, tail: str = "") -> str:
    return f"{BASE}/assessment-attempts/{attempt_id}{tail}"


def answer_key(api: Api, attempt_id: str) -> list[dict[str, Any]]:
    """Correct option per question (test-only route; not scanned)."""
    r = api.get(f"{BASE}/__test__/assessment-attempts/{attempt_id}/answer-key")
    assert r.status_code == 200, r.text
    return list(r.json()["answers"])


def answer(api: Api, aid: str, token: str | None, qid: str, choice: int | None) -> Any:
    return call(
        api,
        "POST",
        attempt_path(aid, "/answer"),
        token=token,
        json={"question_id": qid, "choice": choice},
    )


def play(
    api: Api, attempt: dict[str, Any], token: str, plan: Any = lambda _i: True
) -> dict[str, Any]:
    """Answer every question (`plan(index)` → correct / wrong / None to skip); the last response."""
    key = answer_key(api, attempt["id"])
    question = attempt["question"]
    last: dict[str, Any] = {}
    for i, k in enumerate(key):
        verdict = plan(i)
        choice = None if verdict is None else k["answer"] if verdict else (k["answer"] + 1) % 4
        r = answer(api, attempt["id"], token, question["id"], choice)
        assert r.status_code == 200, r.text
        last = r.json()
        question = last.get("question")
    assert last["status"] == "SCORED", last
    return last


def pass_via_test_route(
    api: Api, dev: SeededUser, pid: str, slot: str, outcome: str
) -> dict[str, Any]:
    r = api.post(
        f"{BASE}/__test__/developers/{dev.user_id}/role-evidence",
        json={"project_id": pid, "slot_id": slot, "outcome": outcome},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def age_attempt(migration_url: str, attempt_id: str, hours: int = 3) -> None:
    """Move an attempt's start and deadline into the past (the migrator may update the table)."""
    engine = create_engine(migration_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE test_attempts SET started_at = started_at - make_interval(hours => :h), "
                "deadline_at = deadline_at - make_interval(hours => :h) WHERE id = :id"
            ),
            {"h": hours, "id": uuid.UUID(attempt_id)},
        )
    engine.dispose()


def reset_limits(api: Api) -> None:
    assert api.get(f"{BASE}/__test__/ratelimits/reset").status_code == 204


def bid_body(slot_id: str, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"slot_id": slot_id, "price_paisa": 1_800_000, "days_needed": 20}
    body.update(over)
    return body


# ---------------------------------------------------------------------------- status


def test_status_required_has_blueprint_summary(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    body = status_of(api, pid, slot)
    assert body["status"] == "REQUIRED"
    assert body["reason"] is None
    assert body["rules_version"] >= 1
    assert body["attempt_id"] is None
    assert body["open_elsewhere"] is None
    assert body["result"] is None
    bp = body["blueprint"]
    assert bp["label"].startswith("React")
    assert bp["question_count"] >= 10
    assert bp["time_limit_seconds"] >= 60
    assert bp["extra_time_seconds"] == 0
    assert (bp["pass_overall"], bp["floor"]) == (60, 40)
    comps = bp["competencies"]
    assert len(comps) >= 3
    assert sum(c["weight_bp"] for c in comps) == 10_000
    assert sum(c["question_count"] for c in comps) == bp["question_count"]
    assert all(c["reasons"] for c in comps)
    assert body["bidding_deadline"] is not None
    assert isinstance(body["bidding_closes_soon"], bool)


def test_status_blocked_when_the_skill_is_not_on_the_profile(api: Api) -> None:
    pid, slot = shared_project(api)
    api.sign_in_as("DEVELOPER")
    body = status_of(api, pid, slot)
    assert (body["status"], body["reason"]) == ("BLOCKED", "SKILL_NOT_ON_PROFILE")
    assert body["blueprint"] is None
    r = start(api, pid, slot)
    assert r.status_code == 409
    assert code(r) == "SKILL_NOT_ON_PROFILE"
    assert r.json()["error"]["assessment"]["status"] == "BLOCKED"


def test_status_blocked_for_an_unverified_account(api: Api) -> None:
    pid, slot = shared_project(api)
    dev = api.seed("DEVELOPER", verified=False)
    login = api.login(dev)
    if login.status_code != 200:
        pytest.skip("an unverified account can't sign in on this build")
    body = status_of(api, pid, slot)
    assert (body["status"], body["reason"]) == ("BLOCKED", "ACCOUNT_NOT_VERIFIED")
    r = start(api, pid, slot)
    assert r.status_code == 403
    assert code(r) == "ACCOUNT_NOT_VERIFIED"


def test_status_not_required_for_an_experienced_developer(api: Api) -> None:
    pid, slot = shared_project(api)
    dev = newcomer(api)
    r = api.post(
        f"{BASE}/__test__/developers/{dev.user_id}/reputation", json={"p": "0.700", "c": "0.800"}
    )
    assert r.status_code == 204
    body = status_of(api, pid, slot)
    assert body["status"] == "NOT_REQUIRED"
    assert body["blueprint"] is None
    r = start(api, pid, slot)
    assert r.status_code == 409
    assert code(r) == "NOT_REQUIRED"
    # Experienced developers bid as before: no assessment, nothing linked.
    bid = call(api, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    assert bid.status_code == 201, bid.text


def test_status_closed_after_bidding_closes(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slots = publish(api)
    slot = slots["React"]
    newcomer(api)
    assert status_of(api, pid, slot)["status"] == "REQUIRED"
    assert api.post(f"{BASE}/__test__/projects/{pid}/close-bidding").status_code == 204
    body = status_of(api, pid, slot)
    assert body["status"] == "CLOSED"
    r = start(api, pid, slot)
    assert r.status_code == 409
    assert code(r) == "BIDDING_CLOSED"
    assert r.json()["error"]["assessment"]["status"] == "CLOSED"


def test_status_fallback_to_practice_where_no_assessment_exists(api: Api) -> None:
    """A skill whose blueprint can't be built or served keeps the practice-test rule."""
    api.sign_in_as("CLIENT")
    fallback = None
    for name in ("Flutter", "DevOps", "UI/UX", "Testing", "Node.js", "PostgreSQL"):
        pid, slots = publish(api, (name,))
        dev = api.sign_in_as("DEVELOPER")
        add_skill(api, dev, name)
        body = status_of(api, pid, slots[name])
        if body["status"] == "FALLBACK_PRACTICE":
            fallback = (pid, slots[name], name, body)
            break
        api.sign_in_as("CLIENT")
    if fallback is None:
        pytest.skip("every other skill has a servable blueprint on this database")
    pid, slot, name, body = fallback
    assert body["blueprint"] is None
    assert body["fallback"]["skill_name"] == name
    assert body["fallback"]["practice_score"] == 90
    assert body["fallback"]["passes"] is True
    r = start(api, pid, slot)
    assert r.status_code == 409
    assert code(r) == "BLUEPRINT_UNAVAILABLE"
    # The practice result is what bidding uses there.
    bid = call(api, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    assert bid.status_code == 201, bid.text


def test_status_in_progress_and_open_elsewhere(api: Api, api2: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, _token = begin(api, pid, slot)
    body = status_of(api, pid, slot)
    assert body["status"] == "IN_PROGRESS"
    assert body["attempt_id"] == attempt["id"]
    assert body["blueprint"] is not None
    # A practice test can't start next to an open role attempt (either direction, §16 case 2).
    tests = api.get(f"{BASE}/skill-tests").json()
    r = api.post(f"{BASE}/skill-tests/{tests[0]['id']}/attempts")
    assert r.status_code == 409
    assert code(r) == "ATTEMPT_OPEN"
    assert r.json()["error"]["kind"] == "ROLE"
    # Another developer with an open practice test sees OPEN_ELSEWHERE and can't start.
    newcomer(api2)
    practice = api2.post(f"{BASE}/skill-tests/{tests[0]['id']}/attempts")
    assert practice.status_code == 201, practice.text
    body = status_of(api2, pid, slot)
    assert body["status"] == "OPEN_ELSEWHERE"
    assert body["open_elsewhere"] == practice.json()["id"]
    r = start(api2, pid, slot)
    assert r.status_code == 409
    assert code(r) == "ATTEMPT_OPEN"
    assert r.json()["error"]["assessment"]["open_elsewhere"] == practice.json()["id"]


def test_status_passed_and_reused_by_another_slot_with_the_same_role(api: Api) -> None:
    pid, slot = shared_project(api)
    dev = newcomer(api)
    done = pass_via_test_route(api, dev, pid, slot, "pass")
    assert done["passed"] is True
    body = status_of(api, pid, slot)
    assert body["status"] == "PASSED"
    assert body["result"]["outcome"] == "PASSED"
    assert body["result"]["passed"] is True
    assert body["result"]["valid_until"] is not None
    assert body["result"]["next_allowed_at"] is None
    r = start(api, pid, slot)
    assert r.status_code == 409
    assert code(r) == "ALREADY_PASSED"
    assert r.json()["error"]["assessment"]["status"] == "PASSED"
    # A second project for the same role needs no new attempt (§16 case 9): a freshly published
    # project has the same requirements, so the fingerprint matches.
    api.sign_in_as("CLIENT")
    pid2, slots2 = publish(api)
    api.login(dev)
    assert status_of(api, pid2, slots2["React"])["status"] == "PASSED"


def test_status_retake_locked_after_a_failed_attempt(api: Api) -> None:
    pid, slot = shared_project(api)
    dev = newcomer(api)
    done = pass_via_test_route(api, dev, pid, slot, "fail")
    assert done["passed"] is False
    body = status_of(api, pid, slot)
    assert body["status"] == "RETAKE_LOCKED"
    assert body["result"]["outcome"] == "NOT_PASSED"
    assert body["result"]["valid_until"] is None
    allowed = when(body["next_allowed_at"])
    assert timedelta(days=29) < allowed - datetime.now(UTC) <= timedelta(days=31)
    assert body["result"]["next_allowed_at"] == body["next_allowed_at"]
    r = start(api, pid, slot)
    assert r.status_code == 409
    assert code(r) == "RETAKE_LOCKED"
    assert r.json()["error"]["assessment"]["next_allowed_at"] == body["next_allowed_at"]


@pytest.mark.parametrize("role", ["CLIENT", "ADMIN"])
def test_status_refuses_clients_and_admins(api: Api, role: str) -> None:
    pid, slot = shared_project(api)
    api.sign_in_as(role)
    r = call(api, "GET", slot_path(pid, slot))
    assert r.status_code == 403
    assert code(r) == "ROLE_NOT_ALLOWED"
    r = start(api, pid, slot, version=1)
    assert r.status_code == 403
    assert code(r) == "ROLE_NOT_ALLOWED"
    r = call(api, "GET", f"{BASE}/me/role-assessments")
    assert r.status_code == 403
    assert code(r) == "ROLE_NOT_ALLOWED"


def test_status_anonymous_and_unknown_ids(api: Api) -> None:
    pid, slot = shared_project(api)
    api.client.cookies.clear()
    assert call(api, "GET", slot_path(pid, slot)).status_code == 401
    assert start(api, pid, slot, version=1).status_code == 401
    newcomer(api)
    assert call(api, "GET", slot_path(UNKNOWN, slot)).status_code == 404
    assert call(api, "GET", slot_path(pid, UNKNOWN)).status_code == 404
    assert start(api, UNKNOWN, slot, version=1).status_code == 404
    assert call(api, "GET", slot_path("not-a-uuid", slot)).status_code == 422
    # A slot of another project is not this project's slot.
    api.sign_in_as("CLIENT")
    other_pid, other_slots = publish(api)
    api.sign_in_as("DEVELOPER")
    assert call(api, "GET", slot_path(pid, other_slots["React"])).status_code == 404
    assert other_pid != pid


def test_status_of_a_draft_project_is_not_found(api: Api) -> None:
    api.sign_in_as("CLIENT")
    ids = skill_ids(api)
    created = api.post(
        f"{BASE}/projects",
        json={
            "title": "Online ordering system",
            "summary": "Order and track restaurant orders.",
            "budget_paisa": 12_000_000,
            "deadline_days": 30,
            "team_size": 2,
        },
    )
    assert created.status_code in (200, 201), created.text
    draft = created.json()["id"]
    slots = api.put(
        f"{BASE}/projects/{draft}/slots", json={"slots": [{"skill_id": ids["React"], "count": 2}]}
    ).json()
    newcomer(api)
    assert call(api, "GET", slot_path(draft, slots[0]["id"])).status_code == 404


# ----------------------------------------------------------------------------- start


@pytest.mark.parametrize(
    "body",
    [
        {"consent": False, "rules_version": 1},
        {"consent": True, "rules_version": 2},
        {"consent": True, "rules_version": 99},
        {"consent": False, "rules_version": 99},
    ],
)
def test_start_needs_consent_to_the_current_rules(api: Api, body: dict[str, Any]) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    current = status_of(api, pid, slot)["rules_version"]
    assert current == 1  # the bodies above assume it; bump them together with the rules text
    r = call(api, "POST", slot_path(pid, slot, "/attempts"), json=body)
    assert r.status_code == 422
    assert code(r) == "CONSENT_REQUIRED"
    assert r.json()["error"]["rules_version"] == current
    assert status_of(api, pid, slot)["status"] == "REQUIRED"  # nothing was started


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"consent": True},
        {"rules_version": 1},
        {"consent": True, "rules_version": 0},
        {"consent": True, "rules_version": 101},
        {"consent": True, "rules_version": 1, "user_id": UNKNOWN},
        {"consent": True, "rules_version": 1, "blueprint_id": UNKNOWN},
        {"consent": True, "rules_version": 1, "score": 100},
        {"consent": True, "rules_version": 1, "deadline_at": "2099-01-01T00:00:00Z"},
        {"consent": True, "rules_version": 1, "current_index": 11},
    ],
)
def test_start_rejects_malformed_bodies_and_values_the_server_decides(
    api: Api, body: dict[str, Any]
) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    r = call(api, "POST", slot_path(pid, slot, "/attempts"), json=body)
    assert r.status_code == 422, r.text
    assert status_of(api, pid, slot)["status"] == "REQUIRED"


def test_start_returns_the_first_question_only_and_a_token(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    before = datetime.now(UTC)
    r = start(api, pid, slot)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["attempt_token"]) >= 40
    assert body["state"] == "OPEN"
    assert body["current_index"] == 0
    assert body["total"] >= 10
    assert body["focus_leaves"] == 0
    assert body["leave_limit"] == 2
    assert body["result"] is None
    bp = status_of(api, pid, slot)["blueprint"]
    assert bp["question_count"] == body["total"]
    q = body["question"]
    assert set(q) == QUESTION_KEYS
    assert (q["index"], q["total"]) == (0, body["total"])
    assert len(q["options"]) == 4
    assert q["text"]
    # The server's clock and deadline (started + time limit), not the client's.
    assert abs(when(body["server_now"]) - before) < timedelta(minutes=2)
    assert when(body["deadline_at"]) - when(body["started_at"]) == timedelta(
        seconds=bp["time_limit_seconds"]
    )
    assert body["label"] == bp["label"]
    assert set(body) == {
        "id",
        "label",
        "state",
        "current_index",
        "total",
        "started_at",
        "deadline_at",
        "server_now",
        "focus_leaves",
        "leave_limit",
        "question",
        "result",
        "attempt_token",
    }
    assert status_of(api, pid, slot)["status"] == "IN_PROGRESS"


def test_starting_again_resumes_with_a_new_token(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    first, token1 = begin(api, pid, slot)
    r = start(api, pid, slot)
    assert r.status_code == 200, r.text
    again = r.json()
    assert again["id"] == first["id"]
    token2 = again["attempt_token"]
    assert token2 != token1
    assert again["question"]["id"] == first["question"]["id"]
    assert again["deadline_at"] == first["deadline_at"]
    # The first window has been replaced.
    r = answer(api, first["id"], token1, first["question"]["id"], 0)
    assert r.status_code == 409
    assert code(r) == "ATTEMPT_MOVED"
    r = answer(api, first["id"], token2, first["question"]["id"], 0)
    assert r.status_code == 200, r.text


def test_start_is_idempotent_with_an_idempotency_key(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    key = str(uuid.uuid4())
    first = start(api, pid, slot, headers={"Idempotency-Key": key})
    assert first.status_code == 201, first.text
    replay = start(api, pid, slot, headers={"Idempotency-Key": key})
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["attempt_token"] != first.json()["attempt_token"]  # never replayed
    # A malformed key is refused; the same key for a different request is a conflict.
    assert start(api, pid, slot, headers={"Idempotency-Key": "x"}).status_code in (400, 422)
    other = call(
        api,
        "POST",
        slot_path(pid, slot, "/attempts"),
        json={"consent": False, "rules_version": 1},
        headers={"Idempotency-Key": key},
    )
    assert other.status_code in (409, 422)
    # Two attempts never exist for one developer.
    r = call(api, "GET", f"{BASE}/me/role-assessments")
    assert r.status_code == 200
    assert r.json() == []  # nothing scored yet


def test_open_practice_test_blocks_starting_a_role_attempt(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    tests = api.get(f"{BASE}/skill-tests").json()
    assert api.post(f"{BASE}/skill-tests/{tests[0]['id']}/attempts").status_code == 201
    r = start(api, pid, slot)
    assert r.status_code == 409
    assert code(r) == "ATTEMPT_OPEN"
    assert r.json()["error"]["assessment"]["status"] == "OPEN_ELSEWHERE"


def test_unsafe_methods_need_csrf_and_a_session(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid, qid = attempt["id"], attempt["question"]["id"]
    for path, body in (
        (slot_path(pid, slot, "/attempts"), {"consent": True, "rules_version": 1}),
        (attempt_path(aid, "/resume"), None),
        (attempt_path(aid, "/answer"), {"question_id": qid, "choice": 0}),
        (attempt_path(aid, "/finish"), None),
        (attempt_path(aid, "/focus-events"), {"seq": 1, "type": "VISIBILITY_HIDDEN"}),
        (attempt_path(aid, "/heartbeat"), {"visible": True, "fullscreen": False}),
    ):
        kw: dict[str, Any] = {"headers": {"X-Attempt-Token": token}}
        if body is not None:
            kw["json"] = body
        assert api.post(path, csrf=False, **kw).status_code == 403, path
        assert api.post(path, origin="https://evil.example", **kw).status_code == 403, path
    # Nothing happened: still on the first question.
    state = call(api, "GET", attempt_path(aid), token=token).json()
    assert state["current_index"] == 0
    assert state["focus_leaves"] == 0


# ---------------------------------------------------------------------- the one-way flow


def test_one_way_flow_with_retry_skip_and_scoring(api: Api, migration_url: str) -> None:  # noqa: PLR0915 - one flow, step by step
    pid, slot = shared_project(api)
    dev = newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid = attempt["id"]
    total = attempt["total"]
    key = answer_key(api, aid)
    assert len(key) == total
    q0 = attempt["question"]

    # A question that isn't the current one, and a made-up one.
    for qid in (UNKNOWN, str(uuid.uuid4())):
        r = answer(api, aid, token, qid, 0)
        assert r.status_code == 409
        assert code(r) == "NOT_CURRENT_QUESTION"

    r = answer(api, aid, token, q0["id"], key[0]["answer"])
    assert r.status_code == 200, r.text
    nxt = r.json()
    assert (nxt["status"], nxt["current_index"], nxt["total"]) == ("NEXT", 1, total)
    assert nxt["result"] is None
    q1 = nxt["question"]
    assert set(q1) == QUESTION_KEYS
    assert q1["index"] == 1
    assert q1["id"] != q0["id"]

    # An identical retry (lost response) is ignored and gets the same next question.
    r = answer(api, aid, token, q0["id"], key[0]["answer"])
    assert r.status_code == 200, r.text
    assert r.json()["question"]["id"] == q1["id"]
    assert r.json()["current_index"] == 1
    # ...but a different choice for the already answered question is not accepted.
    r = answer(api, aid, token, q0["id"], (key[0]["answer"] + 1) % 4)
    assert r.status_code == 409
    assert code(r) == "NOT_CURRENT_QUESTION"

    # Skip counts as wrong and locks the question.
    r = answer(api, aid, token, q1["id"], None)
    assert r.status_code == 200, r.text
    q2 = r.json()["question"]
    assert r.json()["current_index"] == 2
    # Now the first question is two steps back: not even an identical retry works.
    r = answer(api, aid, token, q0["id"], key[0]["answer"])
    assert r.status_code == 409
    assert code(r) == "NOT_CURRENT_QUESTION"

    # The state shows position only; the question needs the window token.
    state = call(api, "GET", attempt_path(aid)).json()
    assert state["question"] is None
    assert (state["state"], state["current_index"], state["result"]) == ("OPEN", 2, None)
    state = call(api, "GET", attempt_path(aid), token=token).json()
    assert state["question"]["id"] == q2["id"]
    assert state["question"]["index"] == 2

    # Result before scoring: INVALID_STATE with what is possible.
    r = call(api, "GET", attempt_path(aid, "/result"))
    assert r.status_code == 409
    assert code(r) == "INVALID_STATE"
    assert r.json()["error"]["allowed_actions"] == ["answer", "finish"]
    assert r.json()["error"]["current_state"] == "OPEN"

    # Answer the rest correctly; the last answer scores.
    question = q2
    last: dict[str, Any] = {}
    for i in range(2, total):
        r = answer(api, aid, token, question["id"], key[i]["answer"])
        assert r.status_code == 200, r.text
        last = r.json()
        question = last["question"]
        if i < total - 1:
            assert (last["status"], last["current_index"]) == ("NEXT", i + 1)
    assert last["status"] == "SCORED"
    assert last["question"] is None
    result = last["result"]
    assert result["attempt_id"] == aid
    assert result["outcome"] in ("PASSED", "NOT_PASSED")
    assert 0 < result["score"] < 100  # one skipped question: never a perfect score
    assert sum(c["weight_bp"] for c in result["competencies"]) == 10_000
    assert set(result) == {
        "attempt_id",
        "label",
        "outcome",
        "passed",
        "score",
        "pass_overall",
        "competencies",
        "strongest",
        "weakest",
        "submitted_at",
        "valid_until",
        "next_allowed_at",
    }
    for c in result["competencies"]:
        assert set(c) == {"code", "name", "weight_bp", "score"}
        assert 0 <= c["score"] <= 100
    names = {c["name"] for c in result["competencies"]}
    assert result["strongest"] in names
    assert result["weakest"] in names
    assert result["passed"] == (result["outcome"] == "PASSED")
    if result["passed"]:
        assert result["valid_until"] is not None
        assert result["next_allowed_at"] is None
    else:
        assert result["valid_until"] is None
        assert result["next_allowed_at"] is not None

    # The skipped question is stored as a skip (no choice) and a scored attempt is closed.
    engine = create_engine(migration_url)
    with engine.connect() as conn:
        locked: list[dict[str, Any]] = conn.execute(
            text("SELECT answers_locked FROM test_attempts WHERE id = :id"),
            {"id": uuid.UUID(aid)},
        ).scalar_one()
    engine.dispose()
    assert len(locked) == total
    assert locked[1]["choice"] is None
    assert locked[0]["choice"] == key[0]["answer"]

    r = answer(api, aid, token, q0["id"], 0)
    assert r.status_code == 409
    assert code(r) == "ATTEMPT_CLOSED"
    assert r.json()["error"]["result"]["attempt_id"] == aid
    after = call(api, "GET", attempt_path(aid, "/result"))
    assert after.status_code == 200
    assert after.json() == result
    state = call(api, "GET", attempt_path(aid), token=token).json()
    assert (state["state"], state["question"]) == ("SCORED", None)
    assert state["result"] == result
    assert call(api, "POST", attempt_path(aid, "/resume")).status_code == 409
    # History lists it, newest first, with no flag or focus data.
    history = call(api, "GET", f"{BASE}/me/role-assessments").json()
    assert [h["attempt_id"] for h in history] == [aid]
    assert set(history[0]) == {
        "attempt_id",
        "label",
        "outcome",
        "score",
        "passed",
        "started_at",
        "submitted_at",
        "valid_until",
    }
    # Retake lock (or already passed) follows from the result.
    expected = "ALREADY_PASSED" if result["passed"] else "RETAKE_LOCKED"
    r = start(api, pid, slot)
    assert code(r) == expected
    assert dev.user_id


def test_identical_retry_of_a_skip_returns_the_same_next_question(api: Api) -> None:
    """§16 case 12 for a skip: a retried `choice: null` is ignored like any identical retry."""
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid = attempt["id"]
    first = attempt["question"]
    r = answer(api, aid, token, first["id"], None)
    assert r.status_code == 200, r.text
    nxt = r.json()["question"]
    r = answer(api, aid, token, first["id"], None)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["current_index"]) == ("NEXT", 1)
    assert r.json()["question"]["id"] == nxt["id"]


def test_skipping_every_question_scores_zero(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    last = play(api, attempt, token, plan=lambda _i: None)
    result = last["result"]
    assert result["score"] == 0
    assert result["passed"] is False
    assert result["outcome"] == "NOT_PASSED"
    assert all(c["score"] == 0 for c in result["competencies"])
    assert result["next_allowed_at"] is not None
    assert status_of(api, pid, slot)["status"] == "RETAKE_LOCKED"


def test_all_correct_passes_and_the_pass_is_reusable(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    result = play(api, attempt, token)["result"]
    assert (result["score"], result["passed"], result["outcome"]) == (100, True, "PASSED")
    assert all(c["score"] == 100 for c in result["competencies"])
    valid_until = when(result["valid_until"])
    assert timedelta(days=150) < valid_until - datetime.now(UTC) < timedelta(days=200)
    body = status_of(api, pid, slot)
    assert body["status"] == "PASSED"
    assert body["result"] == result
    assert call(api, "GET", f"{BASE}/me/role-assessments").json()[0]["passed"] is True


def test_finishing_early_counts_the_rest_as_wrong(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid = attempt["id"]
    key = answer_key(api, aid)
    question = attempt["question"]
    for i in range(2):
        r = answer(api, aid, token, question["id"], key[i]["answer"])
        question = r.json()["question"]
    assert call(api, "POST", attempt_path(aid, "/finish")).status_code == 400  # token required
    r = call(api, "POST", attempt_path(aid, "/finish"), token=token)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["attempt_id"] == aid
    assert result["passed"] is False  # two of a dozen cannot pass
    assert result["outcome"] == "NOT_PASSED"
    assert 0 < result["score"] < 60
    assert result["next_allowed_at"] is not None
    again = call(api, "POST", attempt_path(aid, "/finish"), token=token)
    assert again.status_code == 409
    assert code(again) == "ATTEMPT_CLOSED"
    assert again.json()["error"]["result"]["score"] == result["score"]
    r = answer(api, aid, token, question["id"], 0)
    assert code(r) == "ATTEMPT_CLOSED"


def test_bodies_over_two_kilobytes_are_refused(api: Api) -> None:
    """Every assessment body is a few fields (role assessment spec §15): over 2 KB → 413 before
    any work, at the boundary still validated normally; a GET is never read for a body."""
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid, qid = attempt["id"], attempt["question"]["id"]
    headers = {"Content-Type": "application/json"}
    over = b'{"question_id": "%s", "choice": 0, "pad": "%s"}' % (qid.encode(), b"x" * 2100)
    r = call(api, "POST", attempt_path(aid, "/answer"), token=token, content=over, headers=headers)
    assert (r.status_code, code(r)) == (413, "PAYLOAD_TOO_LARGE")
    r = call(api, "POST", slot_path(pid, slot, "/attempts"), content=over, headers=headers)
    assert (r.status_code, code(r)) == (413, "PAYLOAD_TOO_LARGE")
    # Exactly 2048 bytes: not refused for size (the extra field is refused by validation).
    pad = 2048 - len(b'{"question_id": "%s", "choice": 0, "pad": ""}' % qid.encode())
    edge = b'{"question_id": "%s", "choice": 0, "pad": "%s"}' % (qid.encode(), b"x" * pad)
    assert len(edge) == 2048
    r = call(api, "POST", attempt_path(aid, "/answer"), token=token, content=edge, headers=headers)
    assert r.status_code == 422, r.text
    # Nothing was recorded, and a GET with no body is unaffected.
    state = call(api, "GET", attempt_path(aid), token=token)
    assert state.status_code == 200
    assert state.json()["current_index"] == 0


def test_window_token_is_required_checked_and_rotated_on_resume(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid, qid = attempt["id"], attempt["question"]["id"]
    body = {"question_id": qid, "choice": 0}
    # Missing → 400 on every token route.
    for path, payload in (
        (attempt_path(aid, "/answer"), body),
        (attempt_path(aid, "/finish"), None),
        (attempt_path(aid, "/focus-events"), {"seq": 1, "type": "WINDOW_BLUR"}),
        (attempt_path(aid, "/heartbeat"), {"visible": True, "fullscreen": True}),
    ):
        kw: dict[str, Any] = {} if payload is None else {"json": payload}
        r = call(api, "POST", path, **kw)
        assert (r.status_code, code(r)) == (400, "ATTEMPT_TOKEN_REQUIRED"), path
        r = call(api, "POST", path, token="", **kw)
        assert (r.status_code, code(r)) == (400, "ATTEMPT_TOKEN_REQUIRED"), path
        r = call(api, "POST", path, token="x" * 43, **kw)
        assert (r.status_code, code(r)) == (403, "ATTEMPT_TOKEN_INVALID"), path
        # A token that is a prefix of the real one is not the real one.
        r = call(api, "POST", path, token=token[:-1], **kw)
        assert (r.status_code, code(r)) == (403, "ATTEMPT_TOKEN_INVALID"), path
    r = call(api, "POST", attempt_path(aid, "/answer"), token="x" * 500, json=body)
    assert r.status_code in (403, 422)
    # GET: no token, no question; a wrong token is refused rather than ignored.
    assert call(api, "GET", attempt_path(aid)).json()["question"] is None
    r = call(api, "GET", attempt_path(aid), token="x" * 43)
    assert (r.status_code, code(r)) == (403, "ATTEMPT_TOKEN_INVALID")
    assert call(api, "GET", attempt_path(aid), token=token).json()["question"]["id"] == qid
    # Nothing above changed the attempt.
    assert call(api, "GET", attempt_path(aid)).json()["current_index"] == 0

    # Resume rotates the token and keeps the deadline and position.
    r = call(api, "POST", attempt_path(aid, "/resume"))
    assert r.status_code == 200, r.text
    resumed = r.json()
    new = resumed["attempt_token"]
    assert new != token
    assert resumed["deadline_at"] == attempt["deadline_at"]
    assert resumed["question"]["id"] == qid
    assert resumed["current_index"] == 0
    for path, payload in (
        (attempt_path(aid, "/answer"), body),
        (attempt_path(aid, "/focus-events"), {"seq": 1, "type": "WINDOW_BLUR"}),
        (attempt_path(aid, "/heartbeat"), {"visible": True, "fullscreen": True}),
        (attempt_path(aid, "/finish"), None),
    ):
        kw = {} if payload is None else {"json": payload}
        r = call(api, "POST", path, token=token, **kw)
        assert (r.status_code, code(r)) == (409, "ATTEMPT_MOVED"), path
    r = call(api, "GET", attempt_path(aid), token=token)
    assert (r.status_code, code(r)) == (409, "ATTEMPT_MOVED")
    hb = call(
        api,
        "POST",
        attempt_path(aid, "/heartbeat"),
        token=new,
        json={"visible": True, "fullscreen": False},
    )
    assert hb.status_code == 200, hb.text
    assert set(hb.json()) == {"server_now", "deadline_at"}
    assert hb.json()["deadline_at"] == attempt["deadline_at"]


@pytest.mark.parametrize(
    "payload",
    [
        {"choice": 0},
        {"question_id": "nope", "choice": 0},
        {"question_id": UNKNOWN},
        {"question_id": UNKNOWN, "choice": 4},
        {"question_id": UNKNOWN, "choice": -1},
        {"question_id": UNKNOWN, "choice": 1.5},
        {"question_id": UNKNOWN, "choice": 0, "correct": True},
        {"question_id": UNKNOWN, "choice": 0, "score": 100},
        {"question_id": UNKNOWN, "choice": 0, "current_index": 5},
    ],
)
def test_answer_input_bounds(api: Api, payload: dict[str, Any]) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    r = call(api, "POST", attempt_path(attempt["id"], "/answer"), token=token, json=payload)
    assert r.status_code == 422, r.text
    assert call(api, "GET", attempt_path(attempt["id"])).json()["current_index"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"seq": 0, "type": "VISIBILITY_HIDDEN"},
        {"seq": 101, "type": "VISIBILITY_HIDDEN"},
        {"seq": -1, "type": "VISIBILITY_HIDDEN"},
        {"seq": 1, "type": "TAB_SWITCH"},
        {"seq": 1},
        {"seq": 1, "type": "VISIBILITY_HIDDEN", "client_at": "yesterday"},
        {"seq": 1, "type": "VISIBILITY_HIDDEN", "focus_leaves": 0},
        {"seq": 1, "type": "VISIBILITY_HIDDEN", "status": "OPEN"},
    ],
)
def test_focus_event_input_bounds(api: Api, payload: dict[str, Any]) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    r = call(api, "POST", attempt_path(attempt["id"], "/focus-events"), token=token, json=payload)
    assert r.status_code == 422, r.text
    assert call(api, "GET", attempt_path(attempt["id"])).json()["focus_leaves"] == 0


def test_heartbeat_input_bounds(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    path = attempt_path(attempt["id"], "/heartbeat")
    for payload in (
        {},
        {"visible": True},
        {"visible": "maybe", "fullscreen": False},
        {"visible": True, "fullscreen": False, "deadline_at": "2099-01-01T00:00:00Z"},
    ):
        assert call(api, "POST", path, token=token, json=payload).status_code == 422, payload
    ok = call(api, "POST", path, token=token, json={"visible": False, "fullscreen": False})
    assert ok.status_code == 200


# ------------------------------------------------------------------------------ deadline


@pytest.mark.parametrize(
    "via", ["get", "result", "resume", "answer", "finish", "heartbeat", "focus"]
)
def test_a_request_after_the_deadline_scores_the_attempt_at_once(  # noqa: PLR0915 - one flow, step by step
    api: Api, migration_url: str, via: str
) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid, qid = attempt["id"], attempt["question"]["id"]
    key = answer_key(api, aid)
    r = answer(api, aid, token, qid, key[0]["answer"])
    assert r.status_code == 200
    qid = r.json()["question"]["id"]
    age_attempt(migration_url, aid)

    if via == "get":
        r = call(api, "GET", attempt_path(aid), token=token)
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "SCORED"
        assert r.json()["question"] is None
        result = r.json()["result"]
    elif via == "result":
        r = call(api, "GET", attempt_path(aid, "/result"))
        assert r.status_code == 200, r.text
        result = r.json()
    elif via == "resume":
        r = call(api, "POST", attempt_path(aid, "/resume"))
        assert (r.status_code, code(r)) == (409, "ATTEMPT_CLOSED"), r.text
        result = r.json()["error"]["result"]
    elif via == "answer":
        r = answer(api, aid, token, qid, key[1]["answer"])
        assert (r.status_code, code(r)) == (409, "DEADLINE_PASSED"), r.text
        result = r.json()["error"]["result"]
    elif via == "finish":
        r = call(api, "POST", attempt_path(aid, "/finish"), token=token)
        assert r.status_code in (200, 409), r.text
        result = r.json() if r.status_code == 200 else r.json()["error"]["result"]
    elif via == "heartbeat":
        r = call(
            api,
            "POST",
            attempt_path(aid, "/heartbeat"),
            token=token,
            json={"visible": True, "fullscreen": True},
        )
        assert (r.status_code, code(r)) == (409, "ATTEMPT_CLOSED"), r.text
        result = r.json()["error"]["result"]
    else:
        r = call(
            api,
            "POST",
            attempt_path(aid, "/focus-events"),
            token=token,
            json={"seq": 1, "type": "VISIBILITY_HIDDEN"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "CLOSED"
        result = r.json()["result"]

    assert result["attempt_id"] == aid
    assert result["passed"] is False
    assert result["outcome"] == "NOT_PASSED"  # time ran out: scored, not ended by the leave rule
    assert 0 <= result["score"] < 60
    # Scored for good: further answers are refused and the history shows the expiry.
    state = call(api, "GET", attempt_path(aid)).json()
    assert state["state"] == "SCORED"
    assert state["result"]["score"] == result["score"]
    r = answer(api, aid, token, qid, 0)
    assert (r.status_code, code(r)) == (409, "ATTEMPT_CLOSED")
    history = call(api, "GET", f"{BASE}/me/role-assessments").json()
    assert [(h["attempt_id"], h["outcome"], h["passed"]) for h in history] == [
        (aid, "NOT_PASSED", False)
    ]
    assert status_of(api, pid, slot)["status"] == "RETAKE_LOCKED"


def test_the_status_scores_an_expired_attempt_too(api: Api, migration_url: str) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, _token = begin(api, pid, slot)
    age_attempt(migration_url, attempt["id"])
    body = status_of(api, pid, slot)
    assert body["status"] == "RETAKE_LOCKED"  # not IN_PROGRESS: it was scored on the way
    assert body["result"]["attempt_id"] == attempt["id"]


def test_answers_inside_the_grace_period_still_count(api: Api, migration_url: str) -> None:
    """Deadline + 4 s is accepted, + 6 s is not (§16 case 13)."""
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid, qid = attempt["id"], attempt["question"]["id"]
    key = answer_key(api, aid)
    engine = create_engine(migration_url)

    def deadline_in(seconds: float) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE test_attempts SET started_at = now() - interval '1 hour', "
                    "deadline_at = now() + make_interval(secs => :s) WHERE id = :id"
                ),
                {"s": seconds, "id": uuid.UUID(aid)},
            )

    deadline_in(-3)  # 3 s late: inside the 5 s grace
    r = answer(api, aid, token, qid, key[0]["answer"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "NEXT"
    deadline_in(-30)  # far too late
    r = answer(api, aid, token, r.json()["question"]["id"], key[1]["answer"])
    assert (r.status_code, code(r)) == (409, "DEADLINE_PASSED")
    engine.dispose()


# ----------------------------------------------------------------------------- focus events


def test_two_leave_rule(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid = attempt["id"]
    path = attempt_path(aid, "/focus-events")
    r = call(
        api,
        "POST",
        path,
        token=token,
        json={"seq": 1, "type": "VISIBILITY_HIDDEN", "client_at": datetime.now(UTC).isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "WARNING", "focus_leaves": 1, "leave_limit": 2, "result": None}
    # The same seq again (a re-sent event) is counted once.
    for _ in range(3):
        r = call(api, "POST", path, token=token, json={"seq": 1, "type": "VISIBILITY_HIDDEN"})
        assert r.status_code == 200, r.text
        assert (r.json()["status"], r.json()["focus_leaves"]) == ("WARNING", 1)
    state = call(api, "GET", attempt_path(aid), token=token).json()
    assert (state["state"], state["focus_leaves"]) == ("OPEN", 1)
    assert state["question"] is not None  # the attempt carries on after a warning
    # An old seq can't lower or raise the count.
    r = call(api, "POST", path, token=token, json={"seq": 1, "type": "FULLSCREEN_EXIT"})
    assert r.json()["focus_leaves"] == 1

    r = call(api, "POST", path, token=token, json={"seq": 2, "type": "FULLSCREEN_EXIT"})
    assert r.status_code == 200, r.text
    ended = r.json()
    assert (ended["status"], ended["focus_leaves"]) == ("TERMINATED", 2)
    assert ended["result"]["outcome"] == "ENDED_EARLY"
    assert ended["result"]["passed"] is False
    assert ended["result"]["valid_until"] is None
    assert ended["result"]["next_allowed_at"] is not None
    assert ended["result"]["attempt_id"] == aid

    # After scoring: CLOSED with the same result, nothing counted, nothing answerable.
    r = call(api, "POST", path, token=token, json={"seq": 3, "type": "VISIBILITY_HIDDEN"})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["focus_leaves"]) == ("CLOSED", 2)
    assert r.json()["result"] == ended["result"]
    r = call(api, "POST", path, json={"seq": 4, "type": "WINDOW_BLUR"})  # no token, scored
    assert r.status_code == 200
    assert r.json()["status"] == "CLOSED"
    r = answer(api, aid, token, attempt["question"]["id"], 0)
    assert (r.status_code, code(r)) == (409, "ATTEMPT_CLOSED")
    assert call(api, "GET", attempt_path(aid, "/result")).json() == ended["result"]
    body = status_of(api, pid, slot)
    assert body["status"] == "RETAKE_LOCKED"
    assert body["result"]["outcome"] == "ENDED_EARLY"
    assert call(api, "GET", f"{BASE}/me/role-assessments").json()[0]["outcome"] == "ENDED_EARLY"


def test_focus_event_client_time_is_untrusted(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    path = attempt_path(attempt["id"], "/focus-events")
    far = (datetime.now(UTC) + timedelta(days=400)).isoformat()
    r = call(
        api,
        "POST",
        path,
        token=token,
        json={"seq": 1, "type": "PAGE_UNLOAD", "client_at": far, "fullscreen_supported": False},
    )
    assert r.status_code == 200, r.text  # stored as null, not refused
    assert r.json()["focus_leaves"] == 1
    naive = call(
        api,
        "POST",
        path,
        token=token,
        json={"seq": 2, "type": "WINDOW_BLUR", "client_at": "2026-01-01T00:00:00"},
    )
    assert naive.status_code in (200, 422)


def test_focus_events_cannot_be_sent_for_a_finished_attempt_by_someone_else(
    api: Api, api2: Api
) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    newcomer(api2)
    r = call(
        api2,
        "POST",
        attempt_path(attempt["id"], "/focus-events"),
        token=token,
        json={"seq": 1, "type": "VISIBILITY_HIDDEN"},
    )
    assert r.status_code == 404
    assert call(api, "GET", attempt_path(attempt["id"])).json()["focus_leaves"] == 0


# ------------------------------------------------------------------------------- IDOR


def test_other_developers_get_404_on_every_attempt_route(api: Api, api2: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid, qid = attempt["id"], attempt["question"]["id"]
    routes: list[tuple[str, str, Any]] = [
        ("GET", attempt_path(aid), None),
        ("POST", attempt_path(aid, "/resume"), None),
        ("POST", attempt_path(aid, "/answer"), {"question_id": qid, "choice": 0}),
        ("POST", attempt_path(aid, "/finish"), None),
        ("POST", attempt_path(aid, "/focus-events"), {"seq": 1, "type": "VISIBILITY_HIDDEN"}),
        ("POST", attempt_path(aid, "/heartbeat"), {"visible": True, "fullscreen": True}),
        ("GET", attempt_path(aid, "/result"), None),
    ]
    newcomer(api2)
    for method, path, body in routes:
        for tok in (token, None, "x" * 43):  # even with the owner's token: no existence leak
            kw: dict[str, Any] = {} if body is None else {"json": body}
            r = call(api2, method, path, token=tok, **kw)
            assert r.status_code == 404, (method, path, r.status_code, r.text)
    assert call(api2, "GET", f"{BASE}/me/role-assessments").json() == []
    # Unknown attempt ids look the same.
    for method, path, body in routes:
        kw = {} if body is None else {"json": body}
        r = call(api2, method, path.replace(aid, UNKNOWN), token=token, **kw)
        assert r.status_code == 404, (method, path)
    # The owner is untouched.
    state = call(api, "GET", attempt_path(aid), token=token).json()
    assert (state["current_index"], state["focus_leaves"], state["state"]) == (0, 0, "OPEN")


@pytest.mark.parametrize("role", ["CLIENT", "ADMIN"])
def test_clients_and_admins_cannot_use_attempt_routes(api: Api, api2: Api, role: str) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    aid, qid = attempt["id"], attempt["question"]["id"]
    api2.sign_in_as(role)
    for method, path, body in (
        ("GET", attempt_path(aid), None),
        ("POST", attempt_path(aid, "/resume"), None),
        ("POST", attempt_path(aid, "/answer"), {"question_id": qid, "choice": 0}),
        ("POST", attempt_path(aid, "/finish"), None),
        ("POST", attempt_path(aid, "/focus-events"), {"seq": 1, "type": "VISIBILITY_HIDDEN"}),
        ("POST", attempt_path(aid, "/heartbeat"), {"visible": True, "fullscreen": True}),
        ("GET", attempt_path(aid, "/result"), None),
    ):
        kw: dict[str, Any] = {} if body is None else {"json": body}
        r = call(api2, method, path, token=token, **kw)
        assert r.status_code in (403, 404), (role, method, path, r.status_code)
    api2.client.cookies.clear()
    assert call(api2, "GET", attempt_path(aid)).status_code == 401
    assert call(api2, "GET", attempt_path(aid, "/result")).status_code == 401


# ------------------------------------------------------------------------- rate limits


def test_heartbeats_and_starts_are_rate_limited(api: Api) -> None:
    pid, slot = shared_project(api)
    newcomer(api)
    attempt, token = begin(api, pid, slot)
    path = attempt_path(attempt["id"], "/heartbeat")
    statuses = [
        call(api, "POST", path, token=token, json={"visible": True, "fullscreen": True}).status_code
        for _ in range(12)
    ]
    assert statuses[:10] == [200] * 10
    assert 429 in statuses[10:]
    reset_limits(api)
    starts = [start(api, pid, slot, version=1).status_code for _ in range(12)]
    assert starts[0] == 200  # resumed
    assert 429 in starts
    reset_limits(api)


# ------------------------------------------------------------------------ response scan


def test_no_answer_data_in_any_candidate_or_client_response(api: Api, api2: Api) -> None:
    """Walks every JSON response of a complete flow — success and error — as the candidate and as
    the project's client (§15 first bullet). `call()` already refuses answer keys as it goes; this
    makes the coverage explicit and counts what was looked at."""
    start_at = len(SEEN)
    client = api.sign_in_as("CLIENT")
    pid, slots = publish(api)
    slot = slots["React"]
    dev = newcomer(api2)
    status_of(api2, pid, slot)
    attempt, token = begin(api2, pid, slot)
    aid = attempt["id"]
    key = answer_key(api2, aid)
    # Errors on the way.
    answer(api2, aid, token, UNKNOWN, 0)
    answer(api2, aid, None, attempt["question"]["id"], 0)
    call(api2, "GET", attempt_path(aid, "/result"))
    start(api2, pid, slot)
    call(api2, "POST", attempt_path(aid, "/resume"))
    call(
        api2,
        "POST",
        attempt_path(aid, "/focus-events"),
        token=token,
        json={"seq": 1, "type": "WINDOW_BLUR"},
    )
    new = call(api2, "POST", attempt_path(aid, "/resume")).json()
    token = new["attempt_token"]
    call(
        api2,
        "POST",
        attempt_path(aid, "/heartbeat"),
        token=token,
        json={"visible": True, "fullscreen": True},
    )
    question = new["question"]
    for i, k in enumerate(key):
        r = answer(api2, aid, token, question["id"], k["answer"] if i % 3 else None)
        question = r.json().get("question")
    call(api2, "GET", attempt_path(aid, "/result"))
    call(api2, "GET", attempt_path(aid))
    answer(api2, aid, token, UNKNOWN, 1)  # after scoring: ATTEMPT_CLOSED with a result
    call(api2, "POST", attempt_path(aid, "/finish"), token=token)
    call(api2, "GET", f"{BASE}/me/role-assessments")
    status_of(api2, pid, slot)
    # Bidding: the gate's 409, the eligibility preview, the bid, and the client's view of it.
    add = call(api2, "POST", f"{BASE}/projects/{pid}/bids/eligibility", json=bid_body(slot))
    assert add.status_code == 200, add.text
    call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    call(api2, "GET", f"{BASE}/me/bids")
    api.login(client)
    view = call(api, "GET", f"{BASE}/projects/{pid}/bids")
    assert view.status_code == 200, view.text
    assert len(SEEN) - start_at >= 25
    assert dev.user_id


def test_response_models_have_no_answer_fields() -> None:
    from pydantic import BaseModel  # noqa: PLC0415

    from app.schemas import bids as bid_schemas  # noqa: PLC0415
    from app.schemas import role_assessments as schemas  # noqa: PLC0415

    def fields(model: type[BaseModel], seen: set[type]) -> Iterator[tuple[str, str]]:
        if model in seen:
            return
        seen.add(model)
        for name, info in model.model_fields.items():
            yield model.__name__, name
            for sub in _models_in(info.annotation):
                yield from fields(sub, seen)

    def _models_in(annotation: Any) -> Iterator[type[BaseModel]]:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield annotation
        for arg in getattr(annotation, "__args__", ()):
            yield from _models_in(arg)

    outputs = [
        getattr(schemas, n)
        for n in dir(schemas)
        if n.endswith("Out") and isinstance(getattr(schemas, n), type)
    ] + [bid_schemas.AssessmentLineOut, bid_schemas.NewcomerEvidence, bid_schemas.ClientBidOut]
    assert len(outputs) >= 10
    seen: set[type] = set()
    found = [(m, f) for model in outputs for m, f in fields(model, seen) if f in FORBIDDEN_KEYS]
    assert not found, found


# ------------------------------------------------------------------------- bidding gate


def test_a_newcomer_needs_a_pass_to_bid(api: Api, api2: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slots = publish(api)
    slot = slots["React"]
    dev = newcomer(api2)
    r = call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    assert r.status_code == 409, r.text
    assert code(r) == "ROLE_ASSESSMENT_REQUIRED"
    payload = r.json()["error"]["assessment"]
    assert payload["status"] == "REQUIRED"
    assert payload["blueprint"]["competencies"]
    assert payload["rules_version"] >= 1
    # The eligibility preview carries the status too.
    r = call(api2, "POST", f"{BASE}/projects/{pid}/bids/eligibility", json=bid_body(slot))
    assert r.status_code == 200, r.text
    assert r.json()["assessment"]["status"] == "REQUIRED"
    assert r.json()["eligible"] is False
    assert any("passing role assessment" in s for s in strings(r.json()))
    # A failed attempt doesn't unlock it and is described honestly.
    pass_via_test_route(api2, dev, pid, slot, "fail")
    r = call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    assert (r.status_code, code(r)) == (409, "ROLE_ASSESSMENT_REQUIRED")
    assert r.json()["error"]["assessment"]["status"] == "RETAKE_LOCKED"
    r = call(api2, "POST", f"{BASE}/projects/{pid}/bids/eligibility", json=bid_body(slot))
    assert r.json()["assessment"]["status"] == "RETAKE_LOCKED"
    assert r.json()["eligible"] is False
    assert any("below the pass mark" in s for s in strings(r.json())), r.json()


def test_an_attempt_ended_by_leaving_is_explained(api: Api) -> None:
    pid, slot = shared_project(api)
    dev = newcomer(api)
    pass_via_test_route(api, dev, pid, slot, "ended")
    r = call(api, "POST", f"{BASE}/projects/{pid}/bids/eligibility", json=bid_body(slot))
    assert r.status_code == 200, r.text
    assert any("ended early, so it can't count as a pass" in s for s in strings(r.json()))
    assert r.json()["assessment"]["status"] == "RETAKE_LOCKED"
    assert call(api, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot)).status_code == 409


def test_a_pass_unlocks_bidding_and_the_client_sees_the_result_only(api: Api, api2: Api) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slots = publish(api)
    slot = slots["React"]
    dev = newcomer(api2)
    attempt, token = begin(api2, pid, slot)
    last = play(api2, attempt, token, plan=lambda i: i != 0)  # one wrong: a pass, not a perfect one
    assert last["result"]["passed"] is True, last
    # Whatever the client sends, the server links the evidence itself.
    bad = call(
        api2,
        "POST",
        f"{BASE}/projects/{pid}/bids",
        json=bid_body(slot, assessment_evidence_id=UNKNOWN),
    )
    assert bad.status_code == 422
    created = call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    assert created.status_code == 201, created.text
    assert "assessment_evidence_id" not in created.json()
    bid_id = created.json()["id"]
    # Editing other fields keeps working; forcing an evidence id doesn't.
    assert (
        call(api2, "PATCH", f"{BASE}/bids/{bid_id}", json={"price_paisa": 1_700_000}).status_code
        == 200
    )
    assert (
        call(
            api2, "PATCH", f"{BASE}/bids/{bid_id}", json={"assessment_evidence_id": UNKNOWN}
        ).status_code
        == 422
    )

    api.login(client)
    view = call(api, "GET", f"{BASE}/projects/{pid}/bids")
    assert view.status_code == 200, view.text
    mine = next(b for b in view.json()["bids"] if b["developer_id"] == dev.user_id)
    evidence = mine["newcomer_evidence"]
    assert evidence["kind"] == "ROLE"
    line = evidence["assessment"]
    assert set(line) == {"score", "outcome", "strongest", "weakest", "taken_at"}
    assert line["outcome"] == "PASSED"
    assert line["score"] == last["result"]["score"]
    assert line["strongest"]
    assert line["weakest"]
    assert mine["eligible"] is not None
    # No focus events, flags, leaves, answers or tokens anywhere in the client's view.
    blob = repr(view.json()).lower()
    for word in ("focus", "flag", "leave", "heartbeat", "attempt_token", "correct", "answer"):
        assert word not in blob, word
    assert any(f"Role assessment {line['score']} · passed" in s for s in strings(mine))


def test_moving_a_bid_to_another_slot_rechecks_the_assessment(api: Api, api2: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, slots = publish(api, ("React", "FastAPI"), team=2)
    react, fastapi = slots["React"], slots["FastAPI"]
    dev = newcomer(api2)
    add_skill(api2, dev, "FastAPI")
    pass_via_test_route(api2, dev, pid, react, "pass")
    assert status_of(api2, pid, react)["status"] == "PASSED"
    assert status_of(api2, pid, fastapi)["status"] in ("REQUIRED", "FALLBACK_PRACTICE")
    created = call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(react))
    assert created.status_code == 201, created.text
    bid_id = created.json()["id"]
    if status_of(api2, pid, fastapi)["status"] != "REQUIRED":
        pytest.skip("FastAPI has no servable assessment on this database")
    r = call(api2, "PATCH", f"{BASE}/bids/{bid_id}", json={"slot_id": fastapi})
    assert r.status_code == 409, r.text
    assert code(r) == "ROLE_ASSESSMENT_REQUIRED"
    assert r.json()["error"]["assessment"]["status"] == "REQUIRED"
    # The bid stays where it was.
    mine = call(api2, "GET", f"{BASE}/me/bids").json()["items"]
    assert next(b for b in mine if b["id"] == bid_id)["slot_id"] == react
    # After passing the second role it moves.
    pass_via_test_route(api2, dev, pid, fastapi, "pass")
    r = call(api2, "PATCH", f"{BASE}/bids/{bid_id}", json={"slot_id": fastapi})
    assert r.status_code == 200, r.text
    assert r.json()["slot_id"] == fastapi


def test_practice_result_still_counts_where_no_assessment_exists_for_the_client_view(
    api: Api, api2: Api
) -> None:
    client = api.sign_in_as("CLIENT")
    found = None
    for name in ("Flutter", "DevOps", "UI/UX", "Testing", "Node.js", "PostgreSQL"):
        pid, slots = publish(api, (name,))
        dev = newcomer(api2, name)
        if status_of(api2, pid, slots[name])["status"] == "FALLBACK_PRACTICE":
            found = (pid, slots[name], dev)
            break
    if found is None:
        pytest.skip("every other skill has a servable blueprint on this database")
    pid, slot, dev = found
    assert call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot)).status_code == 201
    api.login(client)
    view = call(api, "GET", f"{BASE}/projects/{pid}/bids").json()
    mine = next(b for b in view["bids"] if b["developer_id"] == dev.user_id)
    assert mine["newcomer_evidence"]["kind"] == "PRACTICE"
    assert mine["newcomer_evidence"]["assessment"] is None


# ------------------------------------------------------------------------------- admin


def admin_get(api: Api, path: str, **kw: Any) -> Any:
    return api.get(f"{BASE}/admin{path}", **kw)


def find_item(items: list[dict[str, Any]], attempt_id: str) -> dict[str, Any] | None:
    return next((i for i in items if i["attempt_id"] == attempt_id), None)


def test_admin_review_queue_and_detail(api: Api, api2: Api, api3: Api) -> None:  # noqa: PLR0915 - one flow, step by step
    pid, slot = shared_project(api)
    dev = newcomer(api2)
    ended = pass_via_test_route(api2, dev, pid, slot, "ended")
    aid = str(ended["attempt_id"])
    admin = api3.sign_in_as("ADMIN")
    assert admin.user_id

    items = admin_get(api3, "/assessments").json()
    item = find_item(items, aid)
    assert item is not None
    assert item["candidate_id"] == dev.user_id
    assert (item["flagged"], item["passed"], item["terminated_reason"]) == (
        True,
        False,
        "FOCUS_LIMIT",
    )
    assert item["focus_leaves"] == 2
    assert item["voided"] is False
    assert item["reviewed_at"] is None
    flagged = admin_get(api3, "/assessments", params={"flagged": "true"}).json()
    assert find_item(flagged, aid) is not None
    assert all(i["flagged"] for i in flagged)
    clean = admin_get(api3, "/assessments", params={"flagged": "false"}).json()
    assert find_item(clean, aid) is None
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    assert find_item(admin_get(api3, "/assessments", params={"from": future}).json(), aid) is None
    assert find_item(admin_get(api3, "/assessments", params={"from": past}).json(), aid) is not None
    assert find_item(admin_get(api3, "/assessments", params={"to": past}).json(), aid) is None
    skill = skill_ids(api3)["React"]
    assert find_item(admin_get(api3, "/assessments", params={"skill_id": skill}).json(), aid)
    other = skill_ids(api3)["DevOps"]
    assert (
        find_item(admin_get(api3, "/assessments", params={"skill_id": other}).json(), aid) is None
    )
    assert admin_get(api3, "/assessments", params={"flagged": "maybe"}).status_code == 422
    assert admin_get(api3, "/assessments", params={"skill_id": "x"}).status_code == 422

    detail = admin_get(api3, f"/assessments/{aid}")
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert [e["seq"] for e in d["focus_events"]] == [1, 2]
    assert {e["type"] for e in d["focus_events"]} == {"VISIBILITY_HIDDEN"}
    assert len(d["answers"]) > 2
    assert sum(1 for a in d["answers"] if a["choice"] is not None) == 2
    assert all(isinstance(a["correct"], bool) for a in d["answers"])
    assert sum(1 for a in d["answers"] if a["correct"]) == 2  # the two it answered were right
    assert all(a["choice"] is None and a["correct"] is False for a in d["answers"][2:])
    assert d["breakdown"]
    assert d["deadline_at"]
    assert d["extra_time_seconds"] == 0

    # Mark reviewed.
    r = api3.post(f"{BASE}/admin/assessments/{aid}/review")
    assert r.status_code == 200, r.text
    assert r.json()["reviewed_at"] is not None
    reviewed = find_item(admin_get(api3, "/assessments").json(), aid)
    assert reviewed is not None
    assert reviewed["reviewed_at"] is not None
    assert api3.post(f"{BASE}/admin/assessments/{UNKNOWN}/review").status_code == 404
    assert admin_get(api3, f"/assessments/{UNKNOWN}").status_code == 404
    assert admin_get(api3, "/assessments/not-a-uuid").status_code == 422
    # A practice attempt is not a role assessment.
    tests = api2.get(f"{BASE}/skill-tests").json()
    practice = api2.post(f"{BASE}/skill-tests/{tests[0]['id']}/attempts")
    assert practice.status_code == 201, practice.text
    pa = practice.json()["id"]
    assert admin_get(api3, f"/assessments/{pa}").status_code == 404
    assert api3.post(f"{BASE}/admin/assessments/{pa}/review").status_code == 404


ADMIN_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/assessments", None),
    ("GET", f"/assessments/{UNKNOWN}", None),
    ("POST", f"/assessments/{UNKNOWN}/void", {"reason": "x" * 25}),
    ("POST", f"/assessments/{UNKNOWN}/review", None),
    ("POST", f"/users/{UNKNOWN}/accommodation", {"extra_time_pct": 25, "note": ""}),
    ("GET", "/question-bank", None),
    ("PATCH", f"/question-bank/{UNKNOWN}", {"text": "Edited text here"}),
    ("POST", f"/question-bank/{UNKNOWN}/approve", None),
    ("POST", f"/question-bank/{UNKNOWN}/retire", None),
]


@pytest.mark.parametrize("role", ["CLIENT", "DEVELOPER"])
def test_admin_assessment_routes_are_hidden_from_other_roles(api: Api, role: str) -> None:
    api.sign_in_as(role)
    for method, path, body in ADMIN_ROUTES:
        kw: dict[str, Any] = {} if body is None else {"json": body}
        r = api.request(method, f"{BASE}/admin{path}", **kw)
        assert r.status_code == 404, (role, method, path, r.status_code, r.text)


def test_admin_assessment_routes_need_a_session(api: Api) -> None:
    for method, path, body in ADMIN_ROUTES:
        kw: dict[str, Any] = {} if body is None else {"json": body}
        r = api.request(method, f"{BASE}/admin{path}", **kw)
        assert r.status_code in (401, 404), (method, path, r.status_code)


def test_admin_void_and_accommodation_need_step_up_then_work(  # noqa: PLR0915 - one flow, step by step
    api: Api, api2: Api, api3: Api, migration_url: str
) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slots = publish(api)
    slot = slots["React"]
    dev = newcomer(api2)
    attempt, token = begin(api2, pid, slot)
    result = play(api2, attempt, token)["result"]
    assert result["passed"]
    aid = attempt["id"]
    bid = call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    assert bid.status_code == 201, bid.text
    bid_id = bid.json()["id"]

    admin = api3.sign_in_as("ADMIN")
    # Without a step-up: refused, and nothing changes.
    reason = "Sat the test with another person helping; confirmed by an admin."
    r = api3.post(f"{BASE}/admin/assessments/{aid}/void", json={"reason": reason})
    assert (r.status_code, code(r)) == (403, "STEP_UP_REQUIRED")
    r = api3.post(
        f"{BASE}/admin/users/{dev.user_id}/accommodation", json={"extra_time_pct": 25, "note": "n"}
    )
    assert (r.status_code, code(r)) == (403, "STEP_UP_REQUIRED")
    assert status_of(api2, pid, slot)["status"] == "PASSED"
    # Invalid bodies are 422 whatever the step-up state.
    assert (
        api3.post(f"{BASE}/admin/assessments/{aid}/void", json={"reason": "too short"}).status_code
        == 422
    )
    assert api3.post(f"{BASE}/admin/assessments/{aid}/void", json={}).status_code == 422
    assert (
        api3.post(
            f"{BASE}/admin/assessments/{aid}/void", json={"reason": reason, "extra": 1}
        ).status_code
        == 422
    )

    assert api3.post(f"{BASE}/auth/step-up", json={"code": "000000"}).status_code == 401
    code_now = next_totp(admin.totp_secret or "")
    assert api3.post(f"{BASE}/auth/step-up", json={"code": code_now}).status_code == 204

    assert (
        api3.post(f"{BASE}/admin/assessments/{UNKNOWN}/void", json={"reason": reason}).status_code
        == 404
    )
    r = api3.post(f"{BASE}/admin/assessments/{aid}/void", json={"reason": reason})
    assert r.status_code == 200, r.text
    assert r.json()["attempt_id"] == aid
    assert r.json()["bids_affected"] == 1
    # Voiding twice changes nothing: refused, or accepted as a no-op that keeps the first reason.
    again = api3.post(
        f"{BASE}/admin/assessments/{aid}/void", json={"reason": "Second reason, written later on."}
    )
    assert again.status_code in (200, 409), again.text
    if again.status_code == 200:
        assert again.json()["bids_affected"] == 0
    detail = admin_get(api3, f"/assessments/{aid}").json()
    assert detail["voided"] is True
    assert detail["void_reason"] == reason

    # The developer: the pass is gone, retake is allowed at once, history says so.
    body = status_of(api2, pid, slot)
    assert body["status"] == "REQUIRED"
    assert body["result"]["outcome"] == "VOIDED"
    assert body["result"]["passed"] is False
    assert body["result"]["next_allowed_at"] is None
    hist = call(api2, "GET", f"{BASE}/me/role-assessments").json()
    assert hist[0]["outcome"] == "VOIDED"
    assert hist[0]["passed"] is False
    r = call(api2, "POST", f"{BASE}/projects/{pid}/bids", json=bid_body(slot))
    assert (r.status_code, code(r)) == (409, "ROLE_ASSESSMENT_REQUIRED")
    # The affected bidder was told.
    engine = create_engine(migration_url)
    with engine.connect() as conn:
        told: int = conn.execute(
            text(
                "SELECT count(*) FROM notifications WHERE user_id = :u "
                "AND type = 'ROLE_ASSESSMENT_VOIDED'"
            ),
            {"u": uuid.UUID(dev.user_id)},
        ).scalar_one()
    engine.dispose()
    assert told == 1
    # The client's view says so, without the reason an admin wrote.
    api.login(client)
    view = call(api, "GET", f"{BASE}/projects/{pid}/bids")
    assert view.status_code == 200, view.text
    mine = next(b for b in view.json()["bids"] if b["id"] == bid_id)
    assert mine["newcomer_evidence"]["assessment"]["outcome"] == "VOIDED"
    assert any("Role assessment voided by an admin" in s for s in strings(mine)), mine
    assert not any("another person" in s for s in strings(view.json()))
    # ...and the developer can start straight away (voided attempts don't count).
    again_started = start(api2, pid, slot)
    assert again_started.status_code == 201, again_started.text
    open_aid = again_started.json()["id"]
    assert open_aid != aid
    # Voiding an attempt that is still running ends it (scored as voided), and frees the retake.
    r = api3.post(f"{BASE}/admin/assessments/{open_aid}/void", json={"reason": reason})
    assert r.status_code == 200, r.text
    ended = call(api2, "GET", attempt_path(open_aid)).json()
    assert ended["state"] == "SCORED"
    assert ended["result"]["outcome"] == "VOIDED"
    assert ended["result"]["passed"] is False
    assert status_of(api2, pid, slot)["status"] == "REQUIRED"
    reset_limits(api3)

    # Accommodation: bad values, unknown or non-developer targets, then extra time on the next
    # attempt only.
    path = f"{BASE}/admin/users/%s/accommodation"
    assert api3.post(path % dev.user_id, json={"extra_time_pct": 30, "note": ""}).status_code == 422
    assert (
        api3.post(path % dev.user_id, json={"extra_time_pct": 25, "note": "x" * 301}).status_code
        == 422
    )
    assert api3.post(path % dev.user_id, json={"extra_time_pct": 25, "extra": 1}).status_code == 422
    assert api3.post(path % UNKNOWN, json={"extra_time_pct": 25, "note": ""}).status_code == 404
    assert (
        api3.post(path % client.user_id, json={"extra_time_pct": 25, "note": ""}).status_code == 404
    )
    api5 = api2  # the second developer is a new account on the same browser
    dev2 = newcomer(api5)
    r = api3.post(path % dev2.user_id, json={"extra_time_pct": 50, "note": "Screen reader user"})
    assert r.status_code == 200, r.text
    assert r.json()["extra_time_pct"] == 50
    assert r.json()["note"] == "Screen reader user"
    body = status_of(api5, pid, slot)
    assert body["blueprint"]["extra_time_seconds"] == body["blueprint"]["time_limit_seconds"] // 2
    started, _tok = begin(api5, pid, slot)
    limit = body["blueprint"]["time_limit_seconds"]
    assert when(started["deadline_at"]) - when(started["started_at"]) == timedelta(
        seconds=limit + limit // 2
    )
    detail2 = admin_get(api3, f"/assessments/{started['id']}").json()
    assert detail2["extra_time_seconds"] == limit // 2
    # Removing it (0) leaves the running attempt alone and stops it for later ones.
    r = api3.post(path % dev2.user_id, json={"extra_time_pct": 0, "note": ""})
    assert r.status_code == 200
    assert (
        admin_get(api3, f"/assessments/{started['id']}").json()["extra_time_seconds"] == limit // 2
    )
    assert status_of(api5, pid, slot)["blueprint"]["extra_time_seconds"] == 0


# ------------------------------------------------------------------------- question bank


def insert_question(conn: Any, skill_id: Any, **over: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "skill": skill_id,
        "text": "Which hook runs after every render?",
        "options": '["useEffect","useMemo","useRef","useId"]',
        "correct": 0,
        "active": False,
        "comp": None,
        "expl": None,
        "slug": None,
    }
    values.update(over)
    conn.execute(
        text(
            "INSERT INTO question_bank (id, skill_id, text, options, correct_index, difficulty, "
            "active, competency_id, explanation, slug) VALUES (:id, :skill, :text, "
            "CAST(:options AS jsonb), :correct, 2, :active, :comp, :expl, :slug)"
        ),
        values,
    )
    return uuid.UUID(str(values["id"]))


@pytest.fixture
def scratch_skill(migration_url: str) -> Iterator[dict[str, Any]]:
    """A skill of its own with an inactive practice test of two questions (so the shared bank and
    the public test list are untouched), and a competency to approve questions under."""
    engine = create_engine(migration_url)
    sid, tid = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        domain: Any = conn.execute(text("SELECT domain FROM skills LIMIT 1")).scalar_one()
        conn.execute(
            text("INSERT INTO skills (id, name, domain, active) VALUES (:i, :n, :d, false)"),
            {"i": sid, "n": f"zz-scratch-{sid.hex[:8]}", "d": domain},
        )
        conn.execute(
            text(
                "INSERT INTO skill_tests (id, skill_id, title, question_count, time_limit_seconds, "
                "active) VALUES (:i, :s, 'Scratch test', 2, 600, false)"
            ),
            {"i": tid, "s": sid},
        )
        comp: Any = conn.execute(
            text("SELECT id FROM competencies ORDER BY code LIMIT 1")
        ).scalar_one()
    made: list[uuid.UUID] = []
    try:
        yield {"engine": engine, "skill": sid, "comp": comp, "made": made}
    finally:
        with engine.begin() as conn:  # approved/retired rows are kept by a trigger: lift it here
            conn.execute(text("ALTER TABLE question_bank DISABLE TRIGGER question_bank_immutable"))
            conn.execute(text("DELETE FROM question_bank WHERE skill_id = :s"), {"s": sid})
            conn.execute(text("ALTER TABLE question_bank ENABLE TRIGGER question_bank_immutable"))
            conn.execute(text("DELETE FROM skill_tests WHERE id = :t"), {"t": tid})
            conn.execute(text("DELETE FROM skills WHERE id = :s"), {"s": sid})
        engine.dispose()


def test_question_bank_list_filters_and_shape(api: Api) -> None:
    api.sign_in_as("ADMIN")
    r = admin_get(api, "/question-bank", params={"status": "APPROVED", "limit": 5})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 5
    for q in rows:
        assert q["status"] == "APPROVED"
        assert len(q["options"]) == 4
        assert 0 <= q["correct_index"] <= 3
        assert q["review_level"] in ("SELF_VERIFIED", "HUMAN_APPROVED")
        assert {"times_served", "verification", "explanation", "version", "active"} <= set(q)
    skill = skill_ids(api)["React"]
    react = admin_get(api, "/question-bank", params={"skill_id": skill, "limit": 200}).json()
    assert {q["skill"] for q in react} == {"React"}
    hard = admin_get(api, "/question-bank", params={"difficulty": 3, "limit": 50}).json()
    assert {q["difficulty"] for q in hard} == {3}
    page2 = admin_get(api, "/question-bank", params={"status": "APPROVED", "limit": 5, "offset": 5})
    assert {q["id"] for q in page2.json()}.isdisjoint({q["id"] for q in rows})
    for bad in (
        {"limit": 201},
        {"limit": 0},
        {"offset": -1},
        {"difficulty": 4},
        {"difficulty": 0},
        {"status": "LIVE"},
        {"source": "AI"},
        {"skill_id": "x"},
        {"competency_id": "x"},
    ):
        assert admin_get(api, "/question-bank", params=bad).status_code == 422, bad


def test_question_bank_review_workflow(api: Api, scratch_skill: dict[str, Any]) -> None:
    engine, skill, comp = scratch_skill["engine"], scratch_skill["skill"], scratch_skill["comp"]
    with engine.begin() as conn:
        draft = insert_question(conn, skill, expl="useEffect runs after render.", comp=comp)
        bare = insert_question(conn, skill)  # no competency or explanation
    admin = api.sign_in_as("ADMIN")
    base = f"{BASE}/admin/question-bank"
    assert admin.user_id

    # A draft can be edited; every edit is a new version, and options must stay four and distinct.
    r = api.patch(
        f"{base}/{draft}", json={"text": "Which hook runs after each render?", "difficulty": 3}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["version"], r.json()["difficulty"], r.json()["status"]) == (2, 3, "DRAFT")
    for bad in (
        {"options": ["a", "a", "b", "c"]},
        {"options": ["a", "b", "c"]},
        {"options": ["a", "b", "c", " "]},
        {"correct_index": 4},
        {"difficulty": 5},
        {"text": "ab"},
        {"status": "APPROVED"},
        {"review_level": "HUMAN_APPROVED"},
        {"times_served": 0},
        {"competency_id": "x"},
    ):
        assert api.patch(f"{base}/{draft}", json=bad).status_code == 422, bad
    assert api.patch(f"{base}/{UNKNOWN}", json={"text": "Edited text"}).status_code == 404

    # Approval needs a competency and an explanation.
    r = api.post(f"{base}/{bare}/approve")
    assert (r.status_code, code(r)) == (422, "VALIDATION_ERROR")
    r = api.post(f"{base}/{draft}/approve")
    assert r.status_code == 200, r.text
    q = r.json()
    assert (q["status"], q["review_level"]) == ("APPROVED", "HUMAN_APPROVED")
    assert q["reviewed_by_name"] == "Test User"  # the seeded admin's display name
    assert q["reviewed_at"] is not None
    assert api.post(f"{base}/{UNKNOWN}/approve").status_code == 404

    # An approved question's content can't be edited (create a new version instead).
    r = api.patch(f"{base}/{draft}", json={"text": "A different question text?"})
    assert (r.status_code, code(r)) == (409, "INVALID_STATE")
    r = api.patch(f"{base}/{draft}", json={"correct_index": 2})
    assert r.status_code == 409
    after = admin_get(api, "/question-bank", params={"skill_id": str(skill)}).json()
    assert next(x for x in after if x["id"] == str(draft))["correct_index"] == 0

    # Retire an approved question; retiring twice is harmless; a retired one can't be approved.
    r = api.post(f"{base}/{draft}/retire")
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["active"]) == ("RETIRED", False)
    assert api.post(f"{base}/{draft}/retire").status_code == 200
    r = api.post(f"{base}/{draft}/approve")
    assert (r.status_code, code(r)) == (409, "INVALID_STATE")
    assert api.post(f"{base}/{UNKNOWN}/retire").status_code == 404


def test_retiring_a_question_that_would_break_a_practice_test_is_refused(
    api: Api, scratch_skill: dict[str, Any]
) -> None:
    engine, skill = scratch_skill["engine"], scratch_skill["skill"]
    with engine.begin() as conn:  # the practice test needs two active questions
        first = insert_question(conn, skill, active=True)
        second = insert_question(conn, skill, active=True, text="Which hook keeps a mutable ref?")
    api.sign_in_as("ADMIN")
    base = f"{BASE}/admin/question-bank"
    for qid in (first, second):
        r = api.post(f"{base}/{qid}/retire")
        assert (r.status_code, code(r)) == (409, "INVALID_STATE")
        assert "fewer than 2 questions" in r.json()["error"]["message"]
    rows = {
        q["id"]: q for q in admin_get(api, "/question-bank", params={"skill_id": str(skill)}).json()
    }
    assert all(
        rows[str(q)]["active"] and rows[str(q)]["status"] != "RETIRED" for q in (first, second)
    )
    # With a spare question the same retire is fine.
    with engine.begin() as conn:
        insert_question(conn, skill, active=True, text="Which hook memoises a value?")
    r = api.post(f"{base}/{first}/retire")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "RETIRED"
    # ...but not the next one (two would be needed).
    r = api.post(f"{base}/{second}/retire")
    assert r.status_code == 409


# ----------------------------------------------------------------- configuration checks


def test_permissions_policy_does_not_block_full_screen(client: TestClient) -> None:
    """The app never restricts full screen (role assessment spec §15); the edge's own header is
    pinned by tests/edge/test_edge.py::test_permissions_policy_allows_full_screen."""
    policy = client.get("/api/v1/health").headers.get("permissions-policy", "")
    assert "fullscreen" not in policy, policy


def route_paths(app: Any) -> list[str]:
    return [str(ctx.path) for ctx in iter_route_contexts(app.router.routes)]


def test_no_answer_key_route_outside_the_test_environment() -> None:
    dev_app = create_app(make_settings(DEVSYNC_ENV=Environment.DEVELOPMENT))
    paths = route_paths(dev_app) + list(dev_app.openapi()["paths"])
    assert not [p for p in paths if "answer-key" in p or "answer_key" in p], paths
    assert not [p for p in paths if "__test__" in p], paths
    assert any("/assessment-attempts/" in p for p in paths)  # the product routes are there
    # In the test environment the routes exist but are hidden from the published contract.
    test_app = create_app(make_settings())
    assert any("answer-key" in p for p in route_paths(test_app))  # the walk does see them
    assert not [p for p in test_app.openapi()["paths"] if "answer-key" in p or "__test__" in p]
    # Nothing in the product's contract names a correct answer.
    schemas = test_app.openapi()["components"]["schemas"]
    for name in (
        "AttemptStateOut",
        "StartedOut",
        "QuestionOut",
        "AnswerOut",
        "AssessmentResultOut",
    ):
        assert not set(schemas[name]["properties"]) & FORBIDDEN_KEYS, name
