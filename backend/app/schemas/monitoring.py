"""Monitoring contracts (spec §10.2 Monitoring, §9.10–9.11, §13.5 #29/#38/#39; D151, D152).

The dashboard and risks are role-shaped (D130's pattern): the client's and the admin's models
carry the budget; members' never do, and members never see BUDGET or AUTO_APPROVAL_SOON risks.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.tasks import PersonRef

Health = Literal["HEALTHY", "AT_RISK", "CRITICAL"]
Severity = Literal["CRITICAL", "MEDIUM", "LOW"]


class ProjectRisk(BaseModel):
    id: uuid.UUID
    type: str
    severity: Severity
    entity_type: str
    entity_id: str | None
    title: str
    why: str = Field(description="One plain sentence: why this is a risk")
    actions: list[str]
    opened_at: datetime


class RiskList(BaseModel):
    items: list[ProjectRisk]
    evaluated_at: datetime | None


class Schedule(BaseModel):
    actual_pct: int = Field(ge=0, le=100, description="Σ share × progress")
    planned_pct: int = Field(ge=0, le=100, description="Σ share planned to be done by today")


class ForecastSummary(BaseModel):
    finish_day: int
    finish_date: date | None
    baseline_days: int
    impact_days: int


class NextMilestone(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    progress_pct: int = Field(ge=0, le=100)
    planned_finish_date: date | None
    forecast_finish_date: date | None


class TaskCounts(BaseModel):
    todo: int
    in_progress: int
    review: int
    done: int


class Budget(BaseModel):
    budget_paisa: int
    released_paisa: int
    committed_paisa: int
    remaining_paisa: int


class DashboardForMember(BaseModel):
    view: Literal["member"] = "member"
    progress_pct: int = Field(ge=0, le=100)
    schedule: Schedule
    forecast: ForecastSummary | None
    health: Health
    overall_risk: Severity | None
    top_risks: list[ProjectRisk]
    next_milestone: NextMilestone | None
    tasks: TaskCounts
    evaluated_at: datetime | None = Field(description="When the risks were last evaluated")


class DashboardForClient(DashboardForMember):
    view: Literal["client"] = "client"  # type: ignore[assignment]
    budget: Budget


class ActivityItem(BaseModel):
    id: uuid.UUID
    type: str
    actor: PersonRef | None
    subject: PersonRef | None
    summary: str = Field(description="A plain sentence, built from the event, never free text")
    entity_type: str
    entity_id: uuid.UUID | None
    at: datetime


class MemberEvidence(BaseModel):
    member: PersonRef
    slot_label: str
    status: str
    checkins_on_time: int
    checkins_expected: int
    tasks_done: int
    hours_done: str = Field(description="Estimate hours of tasks they finished (decimal text)")
    comments: int
    replies: int
    blockers_answered: int
    last_active_at: datetime | None


class EvidenceSummary(BaseModel):
    members: list[MemberEvidence]


class MyProject(BaseModel):
    """One of the caller's projects, for "My projects" and the developer dashboard (§13.5 #13,
    #9). Progress and risk come from the project's dashboard while it is in progress."""

    project_id: uuid.UUID
    title: str
    status: str
    role: str = Field(description="The caller's place in the team (the slot label)")
    is_lead: bool
    progress_pct: int | None = Field(ge=0, le=100, description="Null before the project starts")
    next_deadline: date | None = Field(description="The next milestone's forecast finish")
    next_milestone: str | None
    overall_risk: Severity | None
    health: Health | None


EX_MY_PROJECT = {
    "project_id": "9b2e7d4a-6c1f-4a8e-b3d2-1f0e9c8b7a65",
    "title": "Inventory dashboard",
    "status": "IN_PROGRESS",
    "role": "React developer",
    "is_lead": True,
    "progress_pct": 49,
    "next_deadline": "2026-12-03",
    "next_milestone": "Dashboard frontend",
    "overall_risk": "CRITICAL",
    "health": "AT_RISK",
}


EX_RISK = {
    "id": "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
    "type": "CRITICAL_PATH_DELAY",
    "severity": "CRITICAL",
    "entity_type": "MILESTONE",
    "entity_id": "2d4f6a8c-1b3d-4e5f-8a7b-9c0d1e2f3a4b",
    "title": "Dashboard frontend late pushes the deadline by 2 days",
    "why": "Dashboard frontend is on the critical path and is forecast to finish on day 18 "
    "instead of day 16, at its current pace.",
    "actions": ["REPLAN", "MESSAGE_TEAM"],
    "opened_at": "2026-11-23T06:00:00Z",
}
EX_RISKS = {"items": [EX_RISK], "evaluated_at": "2026-11-23T06:15:00Z"}
EX_DASHBOARD = {
    "view": "client",
    "progress_pct": 49,
    "schedule": {"actual_pct": 49, "planned_pct": 45},
    "forecast": {
        "finish_day": 25,
        "finish_date": "2026-12-08",
        "baseline_days": 23,
        "impact_days": 2,
    },
    "health": "AT_RISK",
    "overall_risk": "CRITICAL",
    "top_risks": [EX_RISK],
    "next_milestone": {
        "id": "2d4f6a8c-1b3d-4e5f-8a7b-9c0d1e2f3a4b",
        "name": "Inventory API",
        "status": "ACTIVE",
        "progress_pct": 70,
        "planned_finish_date": "2026-11-23",
        "forecast_finish_date": "2026-11-29",
    },
    "tasks": {"todo": 9, "in_progress": 0, "review": 0, "done": 11},
    "evaluated_at": "2026-11-23T06:15:00Z",
    "budget": {
        "budget_paisa": 12000000,
        "released_paisa": 0,
        "committed_paisa": 0,
        "remaining_paisa": 12000000,
    },
}
EX_ACTIVITY = {
    "items": [
        {
            "id": "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e",
            "type": "task.done",
            "actor": {"id": "5f0c6c1e-2a43-4d9b-9a53-0a1f5a1b2c3d", "name": "Nusrat Jahan"},
            "subject": {"id": "5f0c6c1e-2a43-4d9b-9a53-0a1f5a1b2c3d", "name": "Nusrat Jahan"},
            "summary": "Nusrat Jahan finished a task",
            "entity_type": "TASK",
            "entity_id": "9b2e7d4a-6c1f-4a8e-b3d2-1f0e9c8b7a65",
            "at": "2026-11-23T06:00:00Z",
        }
    ],
    "next_cursor": None,
}
EX_EVIDENCE = {
    "members": [
        {
            "member": {"id": "5f0c6c1e-2a43-4d9b-9a53-0a1f5a1b2c3d", "name": "Nusrat Jahan"},
            "slot_label": "Backend developer",
            "status": "ACTIVE",
            "checkins_on_time": 2,
            "checkins_expected": 2,
            "tasks_done": 7,
            "hours_done": "7.0",
            "comments": 4,
            "replies": 1,
            "blockers_answered": 1,
            "last_active_at": "2026-11-23T06:00:00Z",
        }
    ]
}
