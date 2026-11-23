"""Phase 7 gate check: the seeded "Online ordering system" forms the documented team (§17 Phase 7),
and the homepage's fairness figures are that real run's (rule 0.2.6, D21, D113).

On the stage-2 seed (the project is FORMING, D116) it builds the candidate snapshot exactly as a
client's run would (Balanced preset, fairness dial 1), runs the formation with a fixed seed and
checks: the team equals `tests/fixtures/formation_expected_team.json` (by developer name), it
includes a newcomer, the exact solver confirms it optimal, and the cost of fairness is ≥ 0. A
second run from the same inputs gives the identical result (D109). `--write` rewrites the fixture
after a deliberate, reviewed change. Exits non-zero on any difference.

It also runs the dial at 0, 1 and 2 for the homepage's `frontend/src/content/homepage-example.json`
(newcomers in the team and the cost of fairness per setting; no names) and prints it on a line
starting `homepage-example: `; the gate compares that with the committed file, and
`--homepage PATH` writes it (the tests container mounts only `backend/`).

    python scripts/formation_check.py [--write]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.algorithms.formation import run_formation
from app.core.clock import get_clock
from app.db.context import DbContext
from app.db.session import open_session
from app.jobs.formation_jobs import problem_from
from app.models.identity import User
from app.models.projects import Project, ProjectStatus
from app.schemas.formation import FormationRunCreate
from app.services import platform_settings
from app.services.formation import build_snapshot

FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "formation_expected_team.json"
)
HOMEPAGE = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "content" / "homepage-example.json"
)
SEED = 20261207  # Demo 2's date
CLIENT_EMAIL = "rahim@devsync.local"


async def compute() -> tuple[dict[str, Any], dict[str, Any]]:
    async with open_session(DbContext.system(), job=True) as db:
        client = await db.scalar(select(User.id).where(User.email == CLIENT_EMAIL))
        project = await db.scalar(
            select(Project).where(Project.client_id == client,
                                  Project.title == "Online ordering system")
        )  # fmt: skip
        if project is None or project.status != ProjectStatus.FORMING:
            raise SystemExit("formation-check: the seeded ordering project is not FORMING")
        _version, settings = await platform_settings.get_active(db)
        snapshot, params = await build_snapshot(
            db, get_clock().now().date(), project, settings,
            FormationRunCreate(preset="balanced", min_newcomers=1),
        )  # fmt: skip
    homepage = _homepage(snapshot, params)
    outcomes = []
    for _ in range(2):
        problem, pso, limits = problem_from(snapshot, params)
        out = run_formation(problem, pso, SEED, limits=limits,
                            critical_skills=frozenset(snapshot["critical_skills"]))  # fmt: skip
        outcomes.append(out)
    first, second = outcomes
    if first.team != second.team or first.fitness != second.fitness:
        raise SystemExit("formation-check: the same inputs and seed gave different teams")
    cands = snapshot["candidates"]
    return {
        "seed": SEED,
        "preset": "balanced",
        "min_newcomers": 1,
        "candidates": len(cands),
        "team": sorted(cands[i]["developer_name"] for i in first.team),
        "newcomers": sorted(cands[i]["developer_name"] for i in first.team if cands[i]["newcomer"]),
        "fitness": round(first.fitness, 4),
        "optimal": first.verification.optimal,
        "cost_of_fairness": round(first.fairness.cost, 4),
    }, homepage


def _homepage(snapshot: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    dial = {}
    for k in (0, 1, 2):
        problem, pso, limits = problem_from(snapshot, params, k=k)
        out = run_formation(problem, pso, SEED, limits=limits)
        dial[str(k)] = {
            "newcomers": len(out.fairness.newcomers),
            "cost_of_fairness": round(out.fairness.cost, 4),
            "team_size": len(out.team),
            "optimal": out.verification.optimal,
        }
    return {
        "source": "A real DevSync run on the seeded “Online ordering system” (Balanced preset, "
        f"seed {SEED}); rebuilt by backend/scripts/formation_check.py --homepage.",
        "project": "Online ordering system",
        "dial": dial,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the seeded project's formation result")
    parser.add_argument("--write", action="store_true", help="rewrite the expected-team fixture")
    parser.add_argument("--homepage", type=Path, help="write homepage-example.json here")
    args = parser.parse_args()
    got, homepage = asyncio.run(compute())
    problems = []
    if not got["newcomers"]:
        problems.append("the team has no newcomer with the dial at 1")
    if got["optimal"] is not True:
        problems.append("the exact solver did not confirm the team optimal")
    if got["cost_of_fairness"] < 0:
        problems.append("negative cost of fairness")
    if args.homepage is not None:
        text = json.dumps(homepage, indent=2, ensure_ascii=False) + "\n"
        args.homepage.write_text(text, encoding="utf-8")
    print("homepage-example: " + json.dumps(homepage, ensure_ascii=False, sort_keys=True))
    if args.write:
        FIXTURE.write_text(json.dumps(got, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"formation-check: wrote {FIXTURE.name}")
    else:
        want = json.loads(FIXTURE.read_text(encoding="utf-8"))
        if got != want:
            problems.append(f"result {got} differs from {FIXTURE.name} {want}")
    for p in problems:
        print(f"formation-check: {p}")
    if not problems:
        team, newcomers = ", ".join(got["team"]), ", ".join(got["newcomers"])
        print(
            f"formation-check: {team} (newcomer {newcomers}), fitness {got['fitness']}, "
            f"optimal, cost of fairness {got['cost_of_fairness']:.2%}"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
