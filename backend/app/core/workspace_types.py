"""Workspace vocabularies shared by the models, the schemas and the API (spec §8, §9.1.6).

They live in `core` because the layer rules let models, schemas and the API all import core,
while schemas and the API may not import models (`scripts/check_layers.py`). The models module
re-exports them, so services keep importing from `app.models.workspace`.
"""

from __future__ import annotations

import enum


class TaskStatus(enum.StrEnum):
    """§8 Task: TODO ↔ IN_PROGRESS ↔ REVIEW ↔ DONE, one step at a time (D143)."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    DONE = "DONE"


class TaskDifficulty(enum.StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class EvidenceKind(enum.StrEnum):
    FILE = "FILE"
    LINK = "LINK"
    PR = "PR"
    SCREENSHOT = "SCREENSHOT"


class CommentTarget(enum.StrEnum):
    """§7.5 plus CHECKIN for blocker replies (D146)."""

    TASK = "TASK"
    MILESTONE = "MILESTONE"
    CHECKIN = "CHECKIN"


# The §9.1.6 evidence catalogue: the only allowed `activity_events.type` values (a CHECK too).
ACTIVITY_TYPES: tuple[str, ...] = (
    "checkin.posted",
    "checkin.missed",
    "comment.posted",
    "comment.replied",
    "task.moved",
    "task.done",
    "task.reopened",
    "task.evidence_added",
    "milestone.submitted",
    "milestone.approved",
    "milestone.changes_requested",
    "milestone.auto_approved",
    "work.started",
    "blocker.reported",
    "blocker.answered",
    "github.pr_merged",
    "github.review_given",
    "split.proposed",
    "split.agreed",
    "split.objected",
    "member.left",
    "member.replaced",
)
