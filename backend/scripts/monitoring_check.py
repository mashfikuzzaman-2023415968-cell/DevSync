"""Phase 9 gate check: the seeded "Inventory dashboard" shows the documented risks and impact
(spec §17 Phase 9 "Gate checks", §18.2 item 2; D151, D154).

On the stage-2 seed (project day 12), evaluating the project now gives:
- forecast finish day 25 against a 23-day plan (+2 days);
- exactly these open risks: CRITICAL_PATH_DELAY (Dashboard frontend, CRITICAL), SLACK_EATEN
  (Inventory API, MEDIUM), DEADLINE_IMPACT (MEDIUM: 2 days ≤ 10% of 23), INACTIVE_MEMBER (MEDIUM,
  8 days);
- team health "At risk" and overall risk CRITICAL;
- the snapshot names the delayed milestones (Phase 11's post-mortem reads them).
It also proves a second evaluation changes nothing (idempotent). Exits non-zero on any difference.

    python scripts/monitoring_check.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.context import DbContext
from app.db.session import open_session
from app.models.projects import Milestone, Project
from app.models.workspace import ForecastSnapshot, Risk, RiskStatus
from app.services import monitoring

TITLE = "Inventory dashboard"
EXPECTED = [
    ("CRITICAL_PATH_DELAY", "CRITICAL", "Dashboard frontend"),
    ("DEADLINE_IMPACT", "MEDIUM", None),
    ("INACTIVE_MEMBER", "MEDIUM", None),
    ("SLACK_EATEN", "MEDIUM", "Inventory API"),
]


async def _state(pid: object) -> tuple[list[tuple[str, str, str | None]], dict[str, object]]:
    async with open_session(DbContext.system(), job=True) as db:
        names = {
            str(i): n
            for i, n in await db.execute(
                select(Milestone.id, Milestone.name).where(Milestone.project_id == pid)
            )
        }
        rows = (
            await db.execute(
                select(Risk.type, Risk.severity, Risk.entity_id).where(
                    Risk.project_id == pid, Risk.status == RiskStatus.OPEN
                )
            )
        ).all()
        snap = await db.scalar(
            select(ForecastSnapshot.forecast)
            .where(ForecastSnapshot.project_id == pid)
            .order_by(ForecastSnapshot.day.desc())
            .limit(1)
        )
    found = sorted((t.value, s.value, names.get(str(e)) if e else None) for t, s, e in rows)
    return found, dict(snap or {})


async def main() -> int:
    async with open_session(DbContext.system(), job=True) as db:
        pid = await db.scalar(select(Project.id).where(Project.title == TITLE))
    if pid is None:
        print(f"monitoring-check: no “{TITLE}” project (seed stage 2 first)", file=sys.stderr)
        return 1
    await monitoring.evaluate_project(pid, datetime.now(UTC))
    found, snap = await _state(pid)
    await monitoring.evaluate_project(pid, datetime.now(UTC))
    again, _ = await _state(pid)
    causes = [c["name"] for c in snap.get("causes", [])]  # type: ignore[attr-defined]
    problems = []
    if (snap.get("finish_day"), snap.get("impact_days"), snap.get("baseline_days")) != (25, 2, 23):
        problems.append(f"forecast {snap.get('finish_day')} (+{snap.get('impact_days')})")
    if found != EXPECTED:
        problems.append(f"risks {found}")
    if (snap.get("health"), snap.get("overall")) != ("AT_RISK", "CRITICAL"):
        problems.append(f"health {snap.get('health')}, overall {snap.get('overall')}")
    if "Dashboard frontend" not in causes:
        problems.append(f"causes {causes}")
    if again != found:
        problems.append("a second evaluation changed the risks")
    if problems:
        print(f"monitoring-check: FAILED: {'; '.join(problems)}", file=sys.stderr)
        return 1
    print(
        f"monitoring-check: {TITLE} forecast 25 (+2), {len(found)} risks as documented, "
        "health At risk, idempotent"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
