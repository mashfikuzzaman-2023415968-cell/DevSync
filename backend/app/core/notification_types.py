"""One catalogue of notification types and their §12 categories (spec §12; D162, D163).

Every in-app notification and every non-account email names a `NotificationType`; each type
belongs to exactly one `Category` — a §12 row — and the user's switches are kept per category
(`notification_preferences.type`). Defaults follow §12's columns; mentions have an email that is
off by default (D153). Account and security emails are not here: they can't be switched off.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Category(StrEnum):
    BIDS_RECEIVED = "bids_received"
    BIDDING_OUTCOME = "bidding_outcome"
    FORMATION = "formation"
    SELECTED = "selected"
    BID_UPDATES = "bid_updates"
    INVITATION_RESPONSES = "invitation_responses"
    TEAM = "team"
    TASK_ASSIGNED = "task_assigned"
    MENTIONS = "mentions"
    BLOCKERS = "blockers"
    CHECKIN_REMINDER = "checkin_reminder"
    CRITICAL_RISK = "critical_risk"
    VERIFICATION = "verification"


@dataclass(frozen=True)
class CategoryInfo:
    label: str
    in_app: bool  # default
    email: bool  # default
    email_available: bool  # §12 has an email for this row (mentions: opt-in, D153)


CATEGORIES: dict[Category, CategoryInfo] = {
    Category.BIDS_RECEIVED: CategoryInfo(
        "New bids on your projects (daily email digest)", True, True, True
    ),
    Category.BIDDING_OUTCOME: CategoryInfo("Bidding closed or too few bids", True, True, True),
    Category.FORMATION: CategoryInfo(
        "Team formation finished and repairs ready", True, False, False
    ),
    Category.SELECTED: CategoryInfo("You were selected for a team", True, True, True),
    Category.BID_UPDATES: CategoryInfo("Changes to your bids", True, False, False),
    Category.INVITATION_RESPONSES: CategoryInfo(
        "Invitations accepted, declined or expired", True, False, False
    ),
    Category.TEAM: CategoryInfo("Project started, team lead and team changes", True, True, True),
    Category.TASK_ASSIGNED: CategoryInfo("A task was assigned to you", True, False, False),
    Category.MENTIONS: CategoryInfo("Someone mentioned you", True, False, True),
    Category.BLOCKERS: CategoryInfo("A teammate reported a blocker", True, False, False),
    Category.CHECKIN_REMINDER: CategoryInfo("Weekly check-in reminder", True, True, True),
    Category.CRITICAL_RISK: CategoryInfo(
        "A critical risk opened on your project", True, True, True
    ),
    Category.VERIFICATION: CategoryInfo("Assessment and verification results", True, False, False),
}


class NotificationType(StrEnum):
    # Phase 5–6: bidding
    NEW_BIDS = "NEW_BIDS"
    BIDDING_CLOSED = "BIDDING_CLOSED"
    TOO_FEW_BIDS = "TOO_FEW_BIDS"
    TOO_FEW_BIDS_REMINDER = "TOO_FEW_BIDS_REMINDER"
    PROJECT_CANCELLED = "PROJECT_CANCELLED"
    PROJECT_TERMS_CHANGED = "PROJECT_TERMS_CHANGED"
    BID_INELIGIBLE = "BID_INELIGIBLE"
    BIDDING_REOPENED = "BIDDING_REOPENED"
    SLOT_CLOSED = "SLOT_CLOSED"
    ROLE_ASSESSMENT_VOIDED = "ROLE_ASSESSMENT_VOIDED"
    # Phase 7–8: formation and the team
    FORMATION_FINISHED = "FORMATION_FINISHED"
    REPAIR_READY = "REPAIR_READY"
    BID_NOT_SELECTED = "BID_NOT_SELECTED"
    INVITATION_SELECTED = "INVITATION_SELECTED"
    INVITATION_ACCEPTED = "INVITATION_ACCEPTED"
    INVITATION_DECLINED = "INVITATION_DECLINED"
    INVITATION_EXPIRED = "INVITATION_EXPIRED"
    PROJECT_STARTED = "PROJECT_STARTED"
    LEAD_CHOSEN = "LEAD_CHOSEN"
    LEAD_CHANGED = "LEAD_CHANGED"
    LEAD_DECLINED = "LEAD_DECLINED"
    LEAD_CHANGE_REQUESTED = "LEAD_CHANGE_REQUESTED"
    LEAD_CHANGE_DECIDED = "LEAD_CHANGE_DECIDED"
    MEMBER_LEFT = "MEMBER_LEFT"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    REMOVAL_DECIDED = "REMOVAL_DECIDED"
    # Phase 9: the workspace
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASKS_UNASSIGNED = "TASKS_UNASSIGNED"
    MENTIONED = "MENTIONED"
    BLOCKER_REPORTED = "BLOCKER_REPORTED"
    CHECKIN_REMINDER = "CHECKIN_REMINDER"
    RISK_CRITICAL = "RISK_CRITICAL"


CATEGORY_OF: dict[NotificationType, Category] = {
    NotificationType.NEW_BIDS: Category.BIDS_RECEIVED,
    NotificationType.BIDDING_CLOSED: Category.BIDDING_OUTCOME,
    NotificationType.TOO_FEW_BIDS: Category.BIDDING_OUTCOME,
    NotificationType.TOO_FEW_BIDS_REMINDER: Category.BIDDING_OUTCOME,
    NotificationType.PROJECT_CANCELLED: Category.BIDDING_OUTCOME,
    NotificationType.PROJECT_TERMS_CHANGED: Category.BID_UPDATES,
    NotificationType.BID_INELIGIBLE: Category.BID_UPDATES,
    NotificationType.BIDDING_REOPENED: Category.BID_UPDATES,
    NotificationType.SLOT_CLOSED: Category.BID_UPDATES,
    NotificationType.BID_NOT_SELECTED: Category.BID_UPDATES,
    NotificationType.ROLE_ASSESSMENT_VOIDED: Category.VERIFICATION,
    NotificationType.FORMATION_FINISHED: Category.FORMATION,
    NotificationType.REPAIR_READY: Category.FORMATION,
    NotificationType.INVITATION_SELECTED: Category.SELECTED,
    NotificationType.INVITATION_ACCEPTED: Category.INVITATION_RESPONSES,
    NotificationType.INVITATION_DECLINED: Category.INVITATION_RESPONSES,
    NotificationType.INVITATION_EXPIRED: Category.INVITATION_RESPONSES,
    NotificationType.PROJECT_STARTED: Category.TEAM,
    NotificationType.LEAD_CHOSEN: Category.TEAM,
    NotificationType.LEAD_CHANGED: Category.TEAM,
    NotificationType.LEAD_DECLINED: Category.TEAM,
    NotificationType.LEAD_CHANGE_REQUESTED: Category.TEAM,
    NotificationType.LEAD_CHANGE_DECIDED: Category.TEAM,
    NotificationType.MEMBER_LEFT: Category.TEAM,
    NotificationType.MEMBER_REMOVED: Category.TEAM,
    NotificationType.REMOVAL_DECIDED: Category.TEAM,
    NotificationType.TASK_ASSIGNED: Category.TASK_ASSIGNED,
    NotificationType.TASKS_UNASSIGNED: Category.TASK_ASSIGNED,
    NotificationType.MENTIONED: Category.MENTIONS,
    NotificationType.BLOCKER_REPORTED: Category.BLOCKERS,
    NotificationType.CHECKIN_REMINDER: Category.CHECKIN_REMINDER,
    NotificationType.RISK_CRITICAL: Category.CRITICAL_RISK,
}

if set(CATEGORY_OF) != set(NotificationType):  # import-time guard: every type has its row
    raise RuntimeError("a notification type has no §12 category")

# Account and security emails (§12 row 1): always sent, never switchable (D163).
ACCOUNT_TEMPLATES = frozenset(
    {"verify_email", "reset_password", "account_exists", "account_locked", "new_device",
     "password_changed"}
)  # fmt: skip
# Every other email template names the type whose category switch governs it.
TEMPLATE_TYPE: dict[str, NotificationType] = {
    "bidding_closed": NotificationType.BIDDING_CLOSED,
    "too_few_bids": NotificationType.TOO_FEW_BIDS,
    "new_bids_digest": NotificationType.NEW_BIDS,
    "invitation_selected": NotificationType.INVITATION_SELECTED,
    "invitation_replacement": NotificationType.INVITATION_SELECTED,
    "project_started": NotificationType.PROJECT_STARTED,
    "team_lead": NotificationType.LEAD_CHOSEN,
    "lead_changed": NotificationType.LEAD_CHANGED,
    "mentioned": NotificationType.MENTIONED,
    "checkin_reminder": NotificationType.CHECKIN_REMINDER,
    "risk_critical": NotificationType.RISK_CRITICAL,
}


def category(kind: NotificationType | str) -> Category:
    """The §12 row of a type; anything outside the catalogue is refused (D162)."""
    return CATEGORY_OF[NotificationType(kind)]
