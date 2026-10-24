"""Marketplace search and recommendations (spec §10 Marketplace, §9.16). Read-only.

These responses never include bid counts, prices or any bid data (sealed bids, §14.5). Search
filters are whitelisted (unknown params → 400 at the router); the query itself goes through
`plainto_tsquery` (§14.7). Public project views use the same item shape with limited columns.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.projects import CpmNodeOut, PlanEdge


class ProjectCard(BaseModel):
    """A project in a search or public list — no bid data."""

    id: uuid.UUID
    title: str
    summary: str
    status: str
    budget_paisa: int
    deadline_days: int
    team_size: int
    bidding_deadline: datetime | None
    skills: list[str]
    created_at: datetime
    open_for_bids: bool  # BIDDING and before the bidding deadline (server time)


class RecommendedProject(BaseModel):
    """A recommended project with why it matched (spec §9.16)."""

    project: ProjectCard
    skill_match_count: int
    matched_skills: list[str]  # your skills this project needs (deadline fits your usual pace)
    typical_days: int | None  # your median days on those skills, when you have past bids


class SlotCard(BaseModel):
    """A project slot a developer can bid on (no bid data)."""

    id: uuid.UUID
    label: str
    skill: str
    skill_id: uuid.UUID
    count: int


class ProjectClient(BaseModel):
    """Who posted the project: the organisation from the client profile, else their display
    name. Shown to signed-in callers only (never to anonymous visitors). The client rating
    arrives with reviews (Phase 11)."""

    name: str


class ProjectMilestone(BaseModel):
    """One milestone of the published plan: name, duration and state."""

    id: uuid.UUID
    name: str
    duration_days: int
    status: str


class ProjectSchedule(BaseModel):
    """The published plan's CPM schedule for the mini Gantt (day offsets from the start)."""

    duration: int
    nodes: list[CpmNodeOut]
    edges: list[PlanEdge]


class ProjectDetail(ProjectCard):
    """A single open project with its slots, for the developer's bid sheet (spec §13.5 #11).

    Never carries bid data (sealed, §14.5). `milestones` is empty and `schedule` null until the
    project has a baseline plan (written at publish)."""

    description: str
    requirements: str
    start_date: date | None
    client: ProjectClient | None  # null for anonymous visitors
    slots: list[SlotCard]
    milestones: list[ProjectMilestone]
    schedule: ProjectSchedule | None
