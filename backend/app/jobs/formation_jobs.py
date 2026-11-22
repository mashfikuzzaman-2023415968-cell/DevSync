"""Team formation jobs (spec §11, §9.2–§9.8; DECISIONS D105–D109).

- `formation.run` (high queue, 60 s, no retry): rebuilds the problem from the run's frozen
  snapshot, parameters and seed, runs the dial + PSO + exact verification + "why this team" in a
  worker thread, streams progress to `/jobs/{id}/events`, and stores the result. QUEUED → RUNNING
  → SUCCEEDED | INFEASIBLE | TIMED_OUT (best feasible team so far) | FAILED. The client is told.
- `formation.explanations` (default queue, 120 s, one retry): after a confirm, "why not selected"
  for each bid that was not chosen (§9.8), idempotent per run (one row per bid and run).
- `formation.verify` (default queue, 120 s, no retry): an admin's re-run of a finished run;
  records whether it reproduced the same team and fitness (D109).

Every write is a short SYSTEM transaction; nothing is held open while the optimiser runs.
"""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.algorithms import fitness as fit
from app.algorithms.bpso import PsoParams, run_bpso
from app.algorithms.exact_solver import ExactLimits, combinations_count, solve_exact
from app.algorithms.explain import why_not_selected
from app.algorithms.filtering import Mode
from app.algorithms.formation import FormationOutcome, run_formation
from app.core import task_queue
from app.core.clock import get_clock
from app.core.job_events import publish_sync
from app.core.logging import get_logger
from app.db.context import DbContext
from app.db.session import open_session
from app.jobs.queues import get_sync_redis
from app.jobs.runs import run_recorded
from app.models.bidding import Bid
from app.models.formation import BidExplanation, FormationRun, RunStatus, Team
from app.models.foundation import Job, JobStatus
from app.models.projects import Project
from app.services.notifications import notify

log = get_logger(__name__)

RUN_TIMEOUT_SECONDS = 60
EXPLAIN_TIMEOUT_SECONDS = 120
EXPLAIN_BUDGET_SECONDS = 90.0  # stop computing counterfactuals in time to write the rows
EXPLAIN_CAP = 50  # full analyses per run (§9.8); the rest get the reason code only
CONVERGENCE_POINTS = 200
PROGRESS_EVERY = 5  # iterations between progress events


# ------------------------------------------------------------------------------- problem


def problem_from(
    snapshot: dict[str, Any], params: dict[str, Any], *, k: int | None = None
) -> tuple[fit.Problem, PsoParams, ExactLimits]:
    """The pure problem, PSO parameters and exact limits a run was started with."""
    w = params["weights"]
    candidates = tuple(
        fit.Candidate(
            bid_id=c["bid_id"],
            developer_id=c["developer_id"],
            slot_id=c["slot_id"],
            competency=float(c["competency"]),
            teamwork=float(c["teamwork"]),
            performance=float(c["performance"]),
            days=int(c["days"]),
            price_paisa=int(c["price_paisa"]),
            newcomer=bool(c["newcomer"]),
            skills=frozenset(c["skills"]),
        )
        for c in snapshot["candidates"]
    )
    slots = {s: int(n) for s, n in snapshot["slots"].items()}
    problem = fit.Problem(
        candidates=candidates,
        slots=slots,
        deadline_days=int(snapshot["deadline_days"]),
        budget_after_fee_paisa=int(snapshot["budget_after_fee_paisa"]),
        weights=fit.Weights(w["competency"], w["teamwork"], w["time"], w["cost"]),
        min_newcomers=int(params["min_newcomers"] if k is None else k),
        required_skills=frozenset(snapshot["required_skills"]),
        include_performance=bool(params.get("include_performance", False)),
        mode=Mode(params.get("mode", "devsync")),
    )
    p = params["pso"]
    pso = PsoParams(
        particles=p["particles"],
        max_iter=p["max_iter"],
        z1=p["z1"],
        z2=p["z2"],
        inertia=p["inertia"],
        v_max=p["v_max"],
        bounds=(p["bounds"][0], p["bounds"][1]),
        early_stop_iters=p["early_stop_iters"],
    )
    e = params["exact"]
    return problem, pso, ExactLimits(e["max_candidates"], e["max_combinations"])


def _r(value: float | None, places: int = 3) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value + 0.0, places)


def _downsample(series: tuple[float, ...]) -> list[float | None]:
    if len(series) <= CONVERGENCE_POINTS:
        picked = list(series)
    else:
        step = (len(series) - 1) / (CONVERGENCE_POINTS - 1)
        picked = [series[round(i * step)] for i in range(CONVERGENCE_POINTS)]
    return [_r(v, 4) for v in picked]


def build_result(
    snapshot: dict[str, Any], problem: fit.Problem, out: FormationOutcome
) -> dict[str, Any]:
    """The stored `result` (schema `RunResult`)."""
    cands = snapshot["candidates"]
    why = out.why
    contributions = {b.bid_id: b for b in why.contributions} if why else {}
    team = []
    for i in out.team:
        c, b = cands[i], contributions[cands[i]["bid_id"]]
        team.append({
            "bid_id": c["bid_id"], "developer_id": c["developer_id"],
            "developer_name": c["developer_name"], "slot_id": c["slot_id"],
            "slot_label": c["slot_label"], "price_paisa": c["price_paisa"],
            "days_needed": c["days"], "is_newcomer": c["newcomer"],
            "competency": _r(c["competency"]), "teamwork": _r(c["teamwork"]),
            "contribution": {"comp": _r(b.comp), "team": _r(b.team), "time": _r(b.time),
                             "cost": _r(b.cost), "perf": _r(b.perf), "total": _r(b.total)},
        })  # fmt: skip
    v, f = out.verification, out.fairness
    summary = why.summary if why else None
    return {
        "feasible": out.feasible,
        "team": team,
        "fitness": _r(out.fitness, 4),
        "price_paisa": summary.price_paisa if summary else 0,
        "budget_after_fee_paisa": problem.budget_after_fee_paisa,
        "budget_share": _r(why.budget_share) if why else 0.0,
        "max_days": summary.max_days if summary else 0,
        "deadline_days": problem.deadline_days,
        "schedule_share": _r(why.schedule_share) if why else 0.0,
        "newcomers": summary.newcomers if summary else 0,
        "risks": [r.value for r in why.risks] if why else [],
        "deciding_term": why.deciding_term if why else None,
        "runner_up_difference": {k: _r(d) for k, d in why.runner_up_difference.items()}
        if why
        else {},
        "verification": {
            "available": v.available, "reason": v.reason, "optimal": v.optimal,
            "gap": _r(v.gap, 4), "exact_fitness": _r(v.exact_fitness, 4),
            "feasible_count": v.feasible_count,
        },
        "fairness": {
            "requested_k": f.requested_k, "applied_k": f.applied_k, "cost": _r(f.cost, 4) or 0.0,
            "binding": f.binding, "price_difference_paisa": f.price_difference_paisa,
            "baseline_fitness": _r(f.baseline_fitness, 4), "reason": f.reason,
        },
        "top": [
            {"bid_ids": [cands[i]["bid_id"] for i in t.team], "fitness": _r(t.fitness, 4),
             "price_paisa": t.price_paisa, "newcomers": t.newcomers,
             "mean_competency": _r(t.mean_competency), "mean_teamwork": _r(t.mean_teamwork),
             "max_days": t.max_days, "recommended": t.team == out.team}
            for t in out.top
        ],
        "convergence": _downsample(out.pso.convergence),
        "iterations": out.pso.iterations,
        "early_stopped": out.pso.early_stopped,
        "timed_out": out.timed_out,
        "candidates": problem.size,
        "relaxations": snapshot.get("relaxations", []),
    }  # fmt: skip


def outcome_for(
    run: FormationRun,
    *,
    should_stop: Callable[[], bool] | None = None,
    on_progress: Callable[[str, int, float], None] | None = None,
) -> tuple[fit.Problem, FormationOutcome]:
    problem, pso, limits = problem_from(run.candidate_snapshot, run.params)
    out = run_formation(
        problem, pso, run.seed, limits=limits,
        critical_skills=frozenset(run.candidate_snapshot.get("critical_skills", [])),
        should_stop=should_stop, on_progress=on_progress,
    )  # fmt: skip
    return problem, out


# ----------------------------------------------------------------------------- the run


async def _set_job(job_id: uuid.UUID | None, **values: Any) -> None:
    if job_id is None:
        return
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(Job).where(Job.id == job_id).values(**values))
        await db.commit()


async def execute_run(run_id: uuid.UUID) -> RunStatus:
    """Run one formation run (idempotent: a run that already started is left alone)."""
    clock = get_clock()
    async with open_session(DbContext.system(), job=True) as db:
        run = await db.scalar(select(FormationRun).where(FormationRun.id == run_id)
                              .with_for_update())  # fmt: skip
        if run is None or run.status != RunStatus.QUEUED:
            return run.status if run is not None else RunStatus.FAILED
        run.status = RunStatus.RUNNING
        run.started_at = clock.now()
        await db.commit()
        await db.refresh(run)
        db.expunge(run)
    job_id = run.job_id
    await _set_job(job_id, status=JobStatus.RUNNING, started_at=run.started_at, progress=1)
    redis = get_sync_redis()
    events_id = job_id or run.id
    publish_sync(redis, events_id, {"type": "status", "status": "RUNNING", "progress": 1,
                                    "run_id": str(run.id)})  # fmt: skip
    timeout = float(run.params["pso"]["timeout_seconds"])
    began = time.monotonic()
    max_iter = int(run.params["pso"]["max_iter"])

    def should_stop() -> bool:
        return time.monotonic() - began >= timeout

    def on_progress(phase: str, iteration: int, best: float) -> None:
        if iteration % PROGRESS_EVERY:
            return
        base = 5 if phase == "k0" else 50
        progress = min(95, base + int(45 * iteration / max_iter))
        event: dict[str, Any] = {"type": "iteration", "progress": progress, "iteration": iteration}
        if math.isfinite(best):
            event["best_fitness"] = round(best, 4)
        try:
            publish_sync(redis, events_id, event)
        except Exception:  # progress is best effort; the run goes on
            log.warning("formation_progress_publish_failed", run_id=str(run.id))

    try:
        problem, out = await asyncio.to_thread(
            outcome_for, run, should_stop=should_stop, on_progress=on_progress
        )
        result = build_result(run.candidate_snapshot, problem, out)
    except Exception as exc:
        code = type(exc).__name__[:64]
        await _finish(run, RunStatus.FAILED, None, began, code)
        publish_sync(redis, events_id, {"type": "done", "status": "FAILED", "progress": 100,
                                        "run_id": str(run.id)})  # fmt: skip
        raise
    status = (
        RunStatus.INFEASIBLE if not out.feasible
        else RunStatus.TIMED_OUT if out.timed_out
        else RunStatus.SUCCEEDED
    )  # fmt: skip
    await _finish(run, status, result, began, None)
    publish_sync(redis, events_id, {"type": "done", "status": status.value, "progress": 100,
                                    "run_id": str(run.id)})  # fmt: skip
    return status


async def _finish(
    run: FormationRun, status: RunStatus, result: dict[str, Any] | None, began: float,
    error_code: str | None,
) -> None:  # fmt: skip
    now = get_clock().now()
    runtime = int((time.monotonic() - began) * 1000)
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(
            update(FormationRun).where(FormationRun.id == run.id).values(
                status=status, result=result, runtime_ms=runtime, finished_at=now,
                error_code=error_code,
            )
        )  # fmt: skip
        if run.job_id is not None:
            job_status = JobStatus.FAILED if status is RunStatus.FAILED else JobStatus.SUCCEEDED
            await db.execute(update(Job).where(Job.id == run.job_id).values(
                status=job_status, progress=100, finished_at=now, error_code=error_code,
            ))  # fmt: skip
        project = await db.scalar(select(Project).where(Project.id == run.project_id))
        if project is not None and status is not RunStatus.FAILED:
            body = {
                RunStatus.SUCCEEDED: "Your recommended team is ready to review.",
                RunStatus.TIMED_OUT: "The search hit its time limit; the best team found so far "
                "is ready to review.",
                RunStatus.INFEASIBLE: "No team fits all the requirements. Review the settings "
                "and try again.",
            }[status]
            notify(db, project.client_id, "FORMATION_FINISHED",
                   title="Team formation finished", body=body,
                   link=f"/client/projects/{project.id}/formation")  # fmt: skip
        await db.commit()


def formation_run(run_id: str) -> str:
    """RQ entry point for `formation.run`."""
    return asyncio.run(execute_run(uuid.UUID(run_id))).value


def enqueue_run(run_id: uuid.UUID) -> str:
    return task_queue.enqueue("formation.run", str(run_id))


# ----------------------------------------------------------------------- explanations


def _solver(problem: fit.Problem, pso: PsoParams, seed: int, limits: ExactLimits) -> Any:
    exact = (
        problem.size <= limits.max_candidates
        and combinations_count(problem) <= limits.max_combinations
    )

    def solve(p: fit.Problem) -> tuple[tuple[int, ...], float]:
        if exact:
            r = solve_exact(p, limits)
            return r.best, r.fitness
        res = run_bpso(p, pso, seed)
        return res.team, res.fitness

    return solve


def explanations_for(run: FormationRun, *, out_of_time: Callable[[], bool]) -> list[dict[str, Any]]:
    """Rows for every bid of the run's project that was not selected (pure apart from time)."""
    result = run.result or {}
    applied = int((result.get("fairness") or {}).get("applied_k", run.params["min_newcomers"]))
    problem, pso, limits = problem_from(run.candidate_snapshot, run.params, k=applied)
    ids = [c["bid_id"] for c in run.candidate_snapshot["candidates"]]
    chosen = {m["bid_id"] for m in result.get("team", [])}
    team = tuple(i for i, b in enumerate(ids) if b in chosen)
    best = fit.fitness(problem, team)
    solve = _solver(problem, pso, run.seed, limits)
    losers = sorted((i for i in range(problem.size) if i not in team),
                    key=lambda i: (-problem.terms(i).total, i))  # fmt: skip
    rows = []
    for n, i in enumerate(losers):
        row: dict[str, Any] = {"bid_id": ids[i], "reasons": {"codes": ["NOT_SELECTED"]},
                               "price_counterfactual_paisa": None, "main_gap": None}  # fmt: skip
        if n < EXPLAIN_CAP and not out_of_time():
            w = why_not_selected(problem, i, team, best, solve)
            row["reasons"]["gap"] = _r(w.gap, 4)
            row["price_counterfactual_paisa"] = w.counterfactual_price_paisa
            row["main_gap"] = w.main_gap
        rows.append(row)
    for bid_id in run.candidate_snapshot.get("not_shortlisted", []):
        rows.append({"bid_id": bid_id, "reasons": {"codes": ["NOT_SHORTLISTED"]},
                     "price_counterfactual_paisa": None, "main_gap": None})  # fmt: skip
    for bid_id, reason in run.candidate_snapshot.get("rejected", []):
        rows.append({"bid_id": bid_id, "reasons": {"codes": [reason]},
                     "price_counterfactual_paisa": None, "main_gap": None})  # fmt: skip
    return rows


async def write_explanations(run_id: uuid.UUID) -> dict[str, int]:
    async with open_session(DbContext.system(), job=True) as db:
        run = await db.scalar(select(FormationRun).where(FormationRun.id == run_id))
        confirmed = await db.scalar(select(Team.id).where(Team.run_id == run_id))
        if run is None or confirmed is None:
            return {"explanations": 0}
        db.expunge(run)
    began = time.monotonic()
    rows = await asyncio.to_thread(
        explanations_for, run,
        out_of_time=lambda: time.monotonic() - began >= EXPLAIN_BUDGET_SECONDS,
    )  # fmt: skip
    async with open_session(DbContext.system(), job=True) as db:
        known = set(
            (await db.scalars(select(Bid.id).where(Bid.project_id == run.project_id))).all()
        )
        values = [{"run_id": run_id, **r, "bid_id": uuid.UUID(r["bid_id"])} for r in rows
                  if uuid.UUID(r["bid_id"]) in known]  # fmt: skip
        if values:
            await db.execute(pg_insert(BidExplanation).values(values).on_conflict_do_nothing(
                constraint="uq_bid_explanations_bid_run"))  # fmt: skip
        await db.commit()
    return {"explanations": len(values)}


def formation_explanations(run_id: str) -> dict[str, int]:
    """RQ entry point for `formation.explanations` (recorded in `jobs`)."""
    return asyncio.run(
        run_recorded("formation.explanations", lambda: write_explanations(uuid.UUID(run_id)))
    )


def enqueue_explanations(run_id: uuid.UUID) -> str:
    return task_queue.enqueue("formation.explanations", str(run_id))


# ----------------------------------------------------------------------------- verify


async def execute_verify(run_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """Re-run a finished run from its frozen inputs; record whether it reproduced (D109)."""
    now = get_clock().now()
    await _set_job(job_id, status=JobStatus.RUNNING, started_at=now, progress=1)
    try:
        async with open_session(DbContext.system(), job=True) as db:
            run = await db.scalar(select(FormationRun).where(FormationRun.id == run_id))
            if run is None or run.result is None:
                raise LookupError("formation run")
            db.expunge(run)
        _problem, out = await asyncio.to_thread(outcome_for, run)
        stored = run.result
        team = [m["bid_id"] for m in stored.get("team", [])]
        ids = [c["bid_id"] for c in run.candidate_snapshot["candidates"]]
        again = [ids[i] for i in out.team]
        reproduced = sorted(team) == sorted(again) and stored.get("fitness") == _r(out.fitness, 4)
        verification = {
            "reproduced": reproduced, "team_matches": sorted(team) == sorted(again),
            "fitness": _r(out.fitness, 4), "optimal": out.verification.optimal,
            "at": get_clock().now().isoformat(),
        }  # fmt: skip
        async with open_session(DbContext.system(), job=True) as db:
            await db.execute(update(FormationRun).where(FormationRun.id == run_id).values(
                result={**stored, "admin_verification": verification}))  # fmt: skip
            await db.commit()
    except Exception as exc:
        await _set_job(job_id, status=JobStatus.FAILED, finished_at=get_clock().now(),
                       error_code=type(exc).__name__[:64])  # fmt: skip
        raise
    await _set_job(job_id, status=JobStatus.SUCCEEDED, progress=100, finished_at=get_clock().now())
    return reproduced


def formation_verify(run_id: str, job_id: str) -> bool:
    """RQ entry point for `formation.verify`."""
    return asyncio.run(execute_verify(uuid.UUID(run_id), uuid.UUID(job_id)))


def enqueue_verify(run_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return task_queue.enqueue("formation.verify", str(run_id), str(job_id))
