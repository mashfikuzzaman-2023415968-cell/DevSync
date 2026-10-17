"""Timed skill tests over HTTP (spec §17 Phase 3): lifecycle, server-side timer, attempt limits,
IDOR, and correct answers never present in any response (§14.13 row 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from app.core import clock
from app.schemas import skill_tests as schemas
from tests.helpers import Api

pytestmark = [pytest.mark.security, pytest.mark.api]

ANSWER_KEYS = {"correct_index", "is_correct", "answer_index", "solution", "explanation"}


def first_test(api: Api) -> dict[str, Any]:
    r = api.get("/api/v1/skill-tests")
    assert r.status_code == 200, r.text
    tests: list[dict[str, Any]] = r.json()
    assert len(tests) == 8
    return tests[0]


def start(api: Api, test_id: str) -> Any:
    return api.post(f"/api/v1/skill-tests/{test_id}/attempts")


def move_clock(monkeypatch: pytest.MonkeyPatch, delta: timedelta) -> None:
    monkeypatch.setattr(clock, "_clock", clock.FrozenClock(clock.get_clock().now() + delta))


def assert_no_answers(payload: Any) -> None:
    """No key anywhere in the payload names a correct answer."""
    if isinstance(payload, dict):
        assert not ANSWER_KEYS & set(payload), payload
        for value in payload.values():
            assert_no_answers(value)
    elif isinstance(payload, list):
        for value in payload:
            assert_no_answers(value)


def test_response_schemas_have_no_answer_fields() -> None:
    """The contract itself can't carry answers (schema assertion, §17 Phase 3 security)."""
    for model in (schemas.SkillTestOut, schemas.AttemptOut, schemas.AttemptQuestion,
                  schemas.AnswerAccepted):  # fmt: skip
        fields = set(model.model_fields)
        assert not fields & {"correct_index", "correct", "is_correct", "solution"}, model
    assert set(schemas.AttemptQuestion.model_fields) == {"id", "ordinal", "text", "options"}
    # The result reports a count of correct answers, never which ones.
    assert set(schemas.AttemptResult.model_fields) == {
        "id", "score", "correct", "total", "submitted_at", "added_to_profile"
    }  # fmt: skip


def test_full_lifecycle_scores_and_adds_evidence(api: Api, migration_url: str) -> None:
    user = api.sign_in_as("DEVELOPER")
    test = first_test(api)
    r = start(api, test["id"])
    assert r.status_code == 201, r.text
    attempt = r.json()
    assert len(attempt["questions"]) == 10
    assert len({q["id"] for q in attempt["questions"]}) == 10
    for q in attempt["questions"]:
        assert set(q) == {"id", "ordinal", "text", "options"}
        assert len(q["options"]) == 4
    deadline = datetime.fromisoformat(attempt["deadline_at"])
    started = datetime.fromisoformat(attempt["started_at"])
    assert deadline - started == timedelta(seconds=600)
    # Answer every question with the bank's correct answer (read with the migrator role).
    engine = create_engine(migration_url)
    with engine.connect() as conn:
        correct: dict[str, int] = dict(
            conn.execute(
                text("SELECT id::text, correct_index FROM question_bank WHERE id = ANY(:ids)"),
                {"ids": [uuid.UUID(q["id"]) for q in attempt["questions"]]},
            ).all()
        )
    for i, q in enumerate(attempt["questions"]):
        choice = correct[q["id"]] if i < 7 else (correct[q["id"]] + 1) % 4
        r = api.post(f"/api/v1/attempts/{attempt['id']}/answer",
                     json={"question_id": q["id"], "choice": choice})  # fmt: skip
        assert r.status_code == 200, r.text
        assert r.json()["answered"] == i + 1
        assert_no_answers(r.json())
    view = api.get(f"/api/v1/attempts/{attempt['id']}").json()
    assert len(view["answers"]) == 10
    assert_no_answers(view["questions"])
    r = api.post(f"/api/v1/attempts/{attempt['id']}/submit")
    assert r.status_code == 200, r.text
    result = r.json()
    assert (result["score"], result["correct"], result["total"]) == ("0.700", 7, 10)
    assert result["added_to_profile"] is True
    # Double submit.
    r = api.post(f"/api/v1/attempts/{attempt['id']}/submit")
    assert r.status_code == 409
    assert r.json()["error"]["current_state"] == "SUBMITTED"
    # Answering after submit.
    q = attempt["questions"][0]
    r = api.post(
        f"/api/v1/attempts/{attempt['id']}/answer", json={"question_id": q["id"], "choice": 0}
    )
    assert r.status_code == 409
    # Retake within 30 days.
    r = start(api, test["id"])
    assert r.status_code == 409
    assert r.json()["error"]["current_state"] == "RETAKE_LOCKED"
    assert r.json()["error"]["next_attempt_at"]
    listed = next(t for t in api.get("/api/v1/skill-tests").json() if t["id"] == test["id"])
    assert listed["last_score"] == "0.700"
    assert listed["next_attempt_at"] is not None
    # The verified score shows on the profile.
    profile = api.get(f"/api/v1/developers/{user.user_id}").json()
    assert profile["verified_scores"][0]["score"] == "0.700"
    # After 30 days a new scored attempt is allowed (age the attempt in the database).
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE test_attempts SET started_at = started_at - interval '31 days', "
                 "deadline_at = deadline_at - interval '31 days', "
                 "submitted_at = submitted_at - interval '31 days' WHERE id = :id"),
            {"id": uuid.UUID(attempt["id"])},
        )  # fmt: skip
    engine.dispose()
    r = start(api, test["id"])
    assert r.status_code == 201, r.text
    assert r.json()["id"] != attempt["id"]


def test_one_open_attempt_at_a_time(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    test = first_test(api)
    first = start(api, test["id"]).json()
    r = start(api, test["id"])
    assert r.status_code == 409
    assert r.json()["error"]["current_state"] == "IN_PROGRESS"
    assert r.json()["error"]["attempt_id"] == first["id"]
    listed = next(t for t in api.get("/api/v1/skill-tests").json() if t["id"] == test["id"])
    assert listed["open_attempt_id"] == first["id"]


def test_deadline_passes_mid_attempt(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    api.sign_in_as("DEVELOPER")
    attempt = start(api, first_test(api)["id"]).json()
    q = attempt["questions"]
    ok = api.post(
        f"/api/v1/attempts/{attempt['id']}/answer", json={"question_id": q[0]["id"], "choice": 1}
    )
    assert ok.status_code == 200
    move_clock(monkeypatch, timedelta(seconds=601))
    r = api.post(
        f"/api/v1/attempts/{attempt['id']}/answer", json={"question_id": q[1]["id"], "choice": 1}
    )
    assert r.status_code == 409
    assert r.json()["error"]["current_state"] == "EXPIRED"
    # Reading the attempt after the deadline scores what was recorded.
    view = api.get(f"/api/v1/attempts/{attempt['id']}").json()
    assert view["submitted_at"] is not None
    assert view["score"] in ("0.000", "0.100")
    assert api.post(f"/api/v1/attempts/{attempt['id']}/submit").status_code == 409


def test_late_submit_scores_what_was_answered(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    api.sign_in_as("DEVELOPER")
    attempt = start(api, first_test(api)["id"]).json()
    move_clock(monkeypatch, timedelta(minutes=11))
    r = api.post(f"/api/v1/attempts/{attempt['id']}/submit")
    assert r.status_code == 200
    assert (r.json()["score"], r.json()["correct"]) == ("0.000", 0)


def test_answer_validation(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    attempt = start(api, first_test(api)["id"]).json()
    qid = attempt["questions"][0]["id"]
    url = f"/api/v1/attempts/{attempt['id']}/answer"
    for body in (
        {"question_id": qid, "choice": 4},
        {"question_id": qid, "choice": -1},
        {"question_id": str(uuid.uuid4()), "choice": 0},  # not part of this attempt
        {"question_id": qid, "choice": 0, "correct": True},
        {"question_id": qid},
    ):
        assert api.post(url, json=body).status_code == 422, body
    # Changing an answer replaces it.
    api.post(url, json={"question_id": qid, "choice": 0})
    api.post(url, json={"question_id": qid, "choice": 3})
    assert api.get(f"/api/v1/attempts/{attempt['id']}").json()["answers"] == {qid: 3}


def test_attempts_of_others_are_not_found(api: Api, api2: Api) -> None:
    api.sign_in_as("DEVELOPER")
    attempt = start(api, first_test(api)["id"]).json()
    qid = attempt["questions"][0]["id"]
    api2.sign_in_as("DEVELOPER")
    assert api2.get(f"/api/v1/attempts/{attempt['id']}").status_code == 404
    r = api2.post(
        f"/api/v1/attempts/{attempt['id']}/answer", json={"question_id": qid, "choice": 0}
    )
    assert r.status_code == 404
    assert api2.post(f"/api/v1/attempts/{attempt['id']}/submit").status_code == 404
    assert api.get(f"/api/v1/attempts/{attempt['id']}").json()["submitted_at"] is None


def test_unknown_test_and_non_developers(api: Api) -> None:
    api.sign_in_as("DEVELOPER")
    assert start(api, str(uuid.uuid4())).status_code == 404
    api.client.cookies.clear()
    api.sign_in_as("CLIENT")
    assert api.get("/api/v1/skill-tests").status_code == 403
    assert start(api, str(uuid.uuid4())).status_code == 403


def test_questions_are_random_per_attempt(api: Api) -> None:
    sets = []
    for _ in range(3):
        api.client.cookies.clear()
        api.sign_in_as("DEVELOPER")
        sets.append(
            frozenset(q["id"] for q in start(api, first_test(api)["id"]).json()["questions"])
        )
    assert len(set(sets)) > 1  # 16 choose 10: three identical draws are vanishingly unlikely
