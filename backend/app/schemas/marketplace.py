"""Marketplace search and recommendations (spec §10 Marketplace, §9.16). Read-only.

These responses never include bid counts, prices or any bid data (sealed bids, §14.5). Search
filters are whitelisted (unknown params → 400 at the router); the query itself goes through
`plainto_tsquery` (§14.7). Public project views use the same item shape with limited columns.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


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


class RecommendedProject(BaseModel):
    """A recommended project with why it matched (spec §9.16)."""

    project: ProjectCard
    skill_match_count: int
