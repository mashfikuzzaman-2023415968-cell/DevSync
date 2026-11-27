"""Evidence event schemas (spec §9.1.6, D149): every one of the 22 catalogue types has a schema,
accepts a good payload and refuses a bad one; payloads never carry money, days or free text that
could hold reasons; the catalogue, the schemas and the database CHECK list the same types."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.workspace import ACTIVITY_TYPES
from app.schemas.activity import SCHEMAS, InvalidEventError, validate_event_data

pytestmark = pytest.mark.unit

ID = str(uuid.uuid4())
TASK = {"task_id": ID, "milestone_id": ID, "assignee_id": ID, "estimate_hours": "8.0"}

GOOD: dict[str, dict[str, Any]] = {
    "checkin.posted": {
        "checkin_id": ID,
        "week_start": "2026-11-23",
        "on_time": True,
        "has_blockers": False,
    },
    "checkin.missed": {"week_start": "2026-11-23"},
    "comment.posted": {"comment_id": ID, "target_type": "TASK", "target_id": ID, "mentions": [ID]},
    "comment.replied": {
        "comment_id": ID,
        "reply_to_id": ID,
        "to_author_id": ID,
        "response_seconds": 3600,
    },
    "task.moved": {**TASK, "from_status": "TODO", "to_status": "IN_PROGRESS"},
    "task.done": TASK,
    "task.reopened": {**TASK, "to_status": "REVIEW"},
    "task.evidence_added": {"task_id": ID, "evidence_id": ID, "kind": "PR"},
    "milestone.submitted": {"milestone_id": ID, "round": 1},
    "milestone.approved": {"milestone_id": ID, "round": 2},
    "milestone.changes_requested": {"milestone_id": ID, "round": 1},
    "milestone.auto_approved": {"milestone_id": ID, "round": 1},
    "work.started": {"task_id": ID, "milestone_id": ID},
    "blocker.reported": {"checkin_id": ID},
    "blocker.answered": {"checkin_id": ID, "comment_id": ID, "reporter_id": ID},
    "github.pr_merged": {"repo": "acme/inventory", "pr_number": 12},
    "github.review_given": {"repo": "acme/inventory", "pr_number": 12},
    "split.proposed": {"milestone_id": ID, "split_id": ID},
    "split.agreed": {"milestone_id": ID, "split_id": ID},
    "split.objected": {"milestone_id": ID, "split_id": ID},
    "member.left": {"member_id": ID, "slot_label": "Backend", "how": "LEFT"},
    "member.replaced": {"member_id": ID, "slot_label": "Backend"},
}

# One bad payload per type: a missing field, a wrong type or value, or an extra field.
BAD: dict[str, dict[str, Any]] = {
    "checkin.posted": {**GOOD["checkin.posted"], "on_time": "maybe"},
    "checkin.missed": {},
    "comment.posted": {**GOOD["comment.posted"], "mentions": [ID] * 11},
    "comment.replied": {**GOOD["comment.replied"], "response_seconds": -1},
    "task.moved": {**GOOD["task.moved"], "to_status": "FINISHED"},
    "task.done": {**TASK, "estimate_hours": "0"},
    "task.reopened": {**TASK},
    "task.evidence_added": {**GOOD["task.evidence_added"], "kind": "VIDEO"},
    "milestone.submitted": {"milestone_id": ID, "round": 0},
    "milestone.approved": {"milestone_id": ID},
    "milestone.changes_requested": {"milestone_id": "not-a-uuid", "round": 1},
    "milestone.auto_approved": {"milestone_id": ID, "round": 101},
    "work.started": {"task_id": ID},
    "blocker.reported": {"checkin_id": ID, "text": "secret"},
    "blocker.answered": {"checkin_id": ID, "comment_id": ID},
    "github.pr_merged": {"repo": "", "pr_number": 12},
    "github.review_given": {"repo": "acme/inventory", "pr_number": 0},
    "split.proposed": {**GOOD["split.proposed"], "shares": {ID: 5000}},
    "split.agreed": {"split_id": ID},
    "split.objected": {**GOOD["split.objected"], "reason": "unfair"},
    "member.left": {**GOOD["member.left"], "how": "FIRED"},
    "member.replaced": {**GOOD["member.replaced"], "price_paisa": 100},
}

MONEYISH = ("paisa", "price", "days", "reason", "amount", "share", "budget")


def test_the_catalogue_the_schemas_and_the_database_agree() -> None:
    assert set(SCHEMAS) == set(ACTIVITY_TYPES) == set(GOOD) == set(BAD)
    assert len(ACTIVITY_TYPES) == 22  # §9.1.6


@pytest.mark.parametrize("event_type", sorted(GOOD))
def test_every_schema_accepts_a_good_payload(event_type: str) -> None:
    stored = validate_event_data(event_type, GOOD[event_type])
    assert isinstance(stored, dict)


@pytest.mark.parametrize("event_type", sorted(BAD))
def test_every_schema_refuses_a_bad_payload(event_type: str) -> None:
    with pytest.raises(InvalidEventError):
        validate_event_data(event_type, BAD[event_type])


def test_unknown_types_are_refused() -> None:
    for name in ("task.created", "", "TASK.DONE"):
        with pytest.raises(InvalidEventError):
            validate_event_data(name, {})


@pytest.mark.parametrize("event_type", sorted(SCHEMAS))
def test_no_schema_has_a_field_for_money_days_or_reasons(event_type: str) -> None:
    fields = SCHEMAS[event_type].model_fields
    assert not [f for f in fields if any(word in f for word in MONEYISH)], event_type


def test_payloads_are_stored_as_json() -> None:
    stored = validate_event_data("task.done", TASK)
    assert stored["estimate_hours"] == "8.0"
    assert stored["task_id"] == ID
