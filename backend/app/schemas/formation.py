"""Team formation API schemas (spec §10.2 Formation, §13.9; contract-first §10.4).

Scores are plain numbers rounded to 4 places (fitness) or 3 (shares, terms) by the service (D105);
money is integer paisa. A run's `result` is written once by the formation job and returned as-is.
Bidders never see other bids: a "why not selected" explanation names no rival, price or person.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import StrictRequest

RunStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "INFEASIBLE", "FAILED", "TIMED_OUT"]
Preset = Literal["balanced", "quality", "fast", "budget"]
Term = Literal["comp", "team", "time", "cost"]


def _share(default: Decimal | None = None) -> Decimal | None:
    """A 0–1 value with at most 3 decimal places."""
    return Field(default=default, ge=Decimal(0), le=Decimal(1), max_digits=4, decimal_places=3)


Share = Field(ge=Decimal(0), le=Decimal(1), max_digits=4, decimal_places=3)


class WeightsIn(StrictRequest):
    """Priority weights C1–C4 (0–1 each); normalised to sum 1 by the server."""

    competency: Decimal = Share
    teamwork: Decimal = Share
    time: Decimal = Share
    cost: Decimal = Share

    @model_validator(mode="after")
    def _some_weight(self) -> WeightsIn:
        if self.competency + self.teamwork + self.time + self.cost <= 0:
            raise ValueError("at least one weight must be above zero")
        return self


class FormationRunCreate(StrictRequest):
    """Start a run. The seed is chosen by the server (sending one is refused)."""

    preset: Preset = "balanced"
    weights: WeightsIn | None = None  # default: the preset's weights
    min_newcomers: int | None = Field(default=None, ge=0, le=2)  # default: the fairness setting
    min_performance: Decimal | None = _share()  # default: the project's minimum standards
    min_competency: Decimal | None = _share()


class FormationRunAccepted(BaseModel):
    """202: the run is queued; follow it at `/jobs/{job_id}/events`."""

    run_id: uuid.UUID
    job_id: uuid.UUID
    status: RunStatus
    progress: int = Field(ge=0, le=100)


class WeightsOut(BaseModel):
    competency: float
    teamwork: float
    time: float
    cost: float


class RunParams(BaseModel):
    preset: Preset
    weights: WeightsOut
    min_newcomers: int
    min_performance: float
    min_competency: float
    mode: Literal["devsync", "pcs_replication"]


class Contribution(BaseModel):
    comp: float
    team: float
    time: float
    cost: float
    perf: float
    total: float


class TeamMemberOut(BaseModel):
    bid_id: uuid.UUID
    developer_id: uuid.UUID
    developer_name: str
    slot_id: uuid.UUID
    slot_label: str
    price_paisa: int
    days_needed: int
    is_newcomer: bool
    competency: float
    teamwork: float
    contribution: Contribution


class Verification(BaseModel):
    available: bool
    reason: str | None
    optimal: bool | None
    gap: float | None
    exact_fitness: float | None
    feasible_count: int | None


class Fairness(BaseModel):
    requested_k: int
    applied_k: int
    cost: float  # cost of fairness (F0 − Fk) / |F0|
    binding: bool
    price_difference_paisa: int
    baseline_fitness: float | None
    reason: str | None  # MAX_FEASIBLE_K when the requested k was not feasible


class TeamOption(BaseModel):
    bid_ids: list[uuid.UUID]
    fitness: float
    price_paisa: int
    newcomers: int
    mean_competency: float
    mean_teamwork: float
    max_days: int
    recommended: bool


class RelaxationOut(BaseModel):
    step: int
    p0: float
    c0: float


class RunResult(BaseModel):
    feasible: bool
    team: list[TeamMemberOut]
    fitness: float | None
    price_paisa: int
    budget_after_fee_paisa: int
    budget_share: float
    max_days: int
    deadline_days: int
    schedule_share: float
    newcomers: int
    risks: list[str]
    deciding_term: Term | None
    runner_up_difference: dict[str, float]
    verification: Verification
    fairness: Fairness
    top: list[TeamOption]
    convergence: list[float | None]
    iterations: int
    early_stopped: bool
    timed_out: bool
    candidates: int
    relaxations: list[RelaxationOut]


class FormationRunSummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: RunStatus
    preset: Preset
    min_newcomers: int
    fitness: float | None
    optimal: bool | None
    price_paisa: int | None
    created_at: datetime
    finished_at: datetime | None
    confirmed: bool


class FormationRunOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: RunStatus
    job_id: uuid.UUID | None
    seed: int
    settings_version: int
    params: RunParams
    result: RunResult | None
    error_code: str | None
    runtime_ms: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    confirmed: bool
    can_confirm: bool


class AdminRunOut(FormationRunSummary):
    project_title: str
    runtime_ms: int | None
    verified: bool | None  # last admin re-run reproduced the result (None: never verified)


class ConfirmOut(BaseModel):
    team_id: uuid.UUID
    project_status: str
    members: int
    invitations_sent: bool  # False in Phase 7: invitations go out in Phase 8 (D108)


class SlotComparison(BaseModel):
    """The selected bid in the same slot that this bid was compared with: its days and price
    only (§9.8's concrete hint), never who placed it."""

    selected_days: int
    selected_price_paisa: int
    your_days: int
    your_price_paisa: int


class BidExplanationOut(BaseModel):
    """Why a bid was not selected (§9.8), for its bidder only."""

    bid_id: uuid.UUID
    project_title: str
    reasons: list[str]  # NOT_SELECTED, NOT_SHORTLISTED, …
    main_gap: Term | None
    hint: str | None
    gap: float | None  # how far the best team with this bid was from the recommended one
    price_counterfactual_paisa: int | None  # the highest price at which it would have been chosen
    compare: SlotComparison | None
    created_at: datetime


_RUN_ID = "5f0c2b7e-3d4a-4e8b-9c1d-2a3b4c5d6e7f"
_PROJECT_ID = "6a1d3c8f-4e5b-4f9c-8d2e-3b4c5d6e7f80"
_JOB_ID = "0b7c1a52-8d1e-4f55-9a3e-2f1c6f2d9b10"
EX_ACCEPTED = {"run_id": _RUN_ID, "job_id": _JOB_ID, "status": "QUEUED", "progress": 0}
EX_SUMMARY = {
    "id": _RUN_ID,
    "project_id": _PROJECT_ID,
    "status": "SUCCEEDED",
    "preset": "balanced",
    "min_newcomers": 1,
    "fitness": 0.6844,
    "optimal": True,
    "price_paisa": 4_250_000,
    "created_at": "2026-11-22T06:00:00Z",
    "finished_at": "2026-11-22T06:00:02Z",
    "confirmed": False,
}
EX_CONFIRM = {"team_id": _RUN_ID, "project_status": "TEAM_PENDING", "members": 3,
              "invitations_sent": False}  # fmt: skip
EX_EXPLANATION = {
    "bid_id": _RUN_ID,
    "project_title": "Online ordering system",
    "reasons": ["NOT_SELECTED"],
    "main_gap": "cost",
    "hint": "A lower price would have helped most.",
    "gap": 0.0412,
    "price_counterfactual_paisa": 1_600_000,
    "compare": {
        "selected_days": 18,
        "selected_price_paisa": 1_700_000,
        "your_days": 20,
        "your_price_paisa": 2_000_000,
    },
    "created_at": "2026-11-22T06:05:00Z",
}
_BID_A = "7b2e4d90-5f6c-4a0d-9e3f-4c5d6e7f8091"
_BID_B = "8c3f5ea1-6a7d-4b1e-8f40-5d6e7f8091a2"
_SLOT = "9d40a6b2-7b8e-4c2f-9a51-6e7f8091a2b3"
_MEMBER = {
    "bid_id": _BID_A,
    "developer_id": "a0e1b7c3-8c9f-4d30-8b62-7f8091a2b3c4",
    "developer_name": "Nusrat Jahan",
    "slot_id": _SLOT,
    "slot_label": "React",
    "price_paisa": 2_400_000,
    "days_needed": 18,
    "is_newcomer": False,
    "competency": 0.65,
    "teamwork": 0.66,
    "contribution": {"comp": 0.228, "team": 0.165, "time": 0.08, "cost": 0.04, "perf": 0.0,
                     "total": 0.513},
}  # fmt: skip
EX_RUN = {
    "id": _RUN_ID,
    "project_id": _PROJECT_ID,
    "status": "SUCCEEDED",
    "job_id": _JOB_ID,
    "seed": 1_204_771_935,
    "settings_version": 5,
    "params": {
        "preset": "balanced",
        "weights": {"competency": 0.35, "teamwork": 0.25, "time": 0.2, "cost": 0.2},
        "min_newcomers": 1,
        "min_performance": 0.45,
        "min_competency": 0.4,
        "mode": "devsync",
    },
    "result": {
        "feasible": True,
        "team": [_MEMBER, {**_MEMBER, "bid_id": _BID_B, "developer_name": "Arif Hasan",
                           "is_newcomer": True}],
        "fitness": 0.9412,
        "price_paisa": 4_300_000,
        "budget_after_fee_paisa": 10_800_000,
        "budget_share": 0.398,
        "max_days": 22,
        "deadline_days": 30,
        "schedule_share": 0.733,
        "newcomers": 1,
        "risks": [],
        "deciding_term": "cost",
        "runner_up_difference": {"comp": -0.02, "team": 0.0, "time": 0.01, "cost": 0.04},
        "verification": {"available": True, "reason": None, "optimal": True, "gap": 0.0,
                         "exact_fitness": 0.9412, "feasible_count": 6},
        "fairness": {"requested_k": 1, "applied_k": 1, "cost": 0.0213, "binding": True,
                     "price_difference_paisa": -500_000, "baseline_fitness": 0.9617,
                     "reason": None},
        "top": [{"bid_ids": [_BID_A, _BID_B], "fitness": 0.9412, "price_paisa": 4_300_000,
                 "newcomers": 1, "mean_competency": 0.47, "mean_teamwork": 0.58, "max_days": 22,
                 "recommended": True}],
        "convergence": [0.91, 0.93, 0.9412],
        "iterations": 41,
        "early_stopped": True,
        "timed_out": False,
        "candidates": 5,
        "relaxations": [],
    },
    "error_code": None,
    "runtime_ms": 412,
    "created_at": "2026-11-22T06:00:00Z",
    "started_at": "2026-11-22T06:00:01Z",
    "finished_at": "2026-11-22T06:00:01Z",
    "confirmed": False,
    "can_confirm": True,
}  # fmt: skip
EX_ADMIN_PAGE = {
    "items": [{**EX_SUMMARY, "project_title": "Online ordering system", "runtime_ms": 412,
               "verified": True}],
    "next_cursor": None,
}  # fmt: skip
