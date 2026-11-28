"""The shared workspace vocabularies (`app/core/workspace_types.py`): the models re-export the
very same objects (so the DB enums, the API schemas and the services can't drift apart), the
activity catalogue has a payload schema for every type and no duplicates, and the task
statuses run in board order."""

from __future__ import annotations

import pytest

from app.core import workspace_types as wt
from app.models import workspace as models
from app.schemas import activity

pytestmark = pytest.mark.unit


def test_the_models_re_export_the_same_objects() -> None:
    for name in ("TaskStatus", "TaskDifficulty", "EvidenceKind", "CommentTarget", "ACTIVITY_TYPES"):
        assert getattr(models, name) is getattr(wt, name), name


def test_every_activity_type_has_a_schema_and_appears_once() -> None:
    assert len(set(wt.ACTIVITY_TYPES)) == len(wt.ACTIVITY_TYPES) == 22
    for kind in wt.ACTIVITY_TYPES:
        assert kind in activity.SCHEMAS, kind


def test_task_statuses_run_in_board_order() -> None:
    assert [s.value for s in wt.TaskStatus] == ["TODO", "IN_PROGRESS", "REVIEW", "DONE"]
    assert set(models.STATUS_PROGRESS) == set(wt.TaskStatus)
    assert {k.value for k in wt.EvidenceKind} == {"FILE", "LINK", "PR", "SCREENSHOT"}
    assert {t.value for t in wt.CommentTarget} == {"TASK", "MILESTONE", "CHECKIN"}
