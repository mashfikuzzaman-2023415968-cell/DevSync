"""Demo readiness check (spec §17.0): `make demo-check DEMO=N`.

For a demo group it (1) runs the phase gate for the group's last phase (which chains the earlier
phases), (2) resets and loads that stage's seed, (3) runs the scripted walkthrough
`e2e/demos/demo-N.spec.ts` on chromium, firefox, webkit and a mobile viewport, three times, with
video on, and (4) writes `runs/demos/demo-N.md` (gate result, captured artifacts, known
limitations) for the student to rehearse with. Run from the repo root with the demo stack up.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
# DEMO → (last phase of the group, seed stage).
GROUPS = {1: (5, 1), 2: (12, 2), 3: (15, 3)}
BROWSERS = ("chromium", "firefox", "webkit", "mobile")
REPEATS = 3


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT, text=True, check=False)


def _playwright_cmd(demo: int) -> list[str]:
    """Run the walkthrough in the pinned Playwright image on the test stack's nginx network."""
    nginx = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "devsync-test",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.test.yml",
            "ps",
            "-q",
            "nginx",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    projects = [a for b in BROWSERS for a in ("--project", b)]
    return [
        "docker", "run", "--rm", f"--network=container:{nginx}", "--ipc=host",
        "-v", f"{ROOT}/frontend:/web", "-w", "/web", "-e", "HOME=/tmp",
        "-e", "E2E_BASE_URL=https://localhost:8443",
        "mcr.microsoft.com/playwright:v1.63.0-noble",
        "npx", "playwright", "test", f"e2e/demos/demo-{demo}.spec.ts",
        *projects, f"--repeat-each={REPEATS}", "--reporter=list",
    ]  # fmt: skip


def _write_report(demo: int, stage: int, gate_ok: bool, walkthrough_ok: bool) -> Path:
    out = ROOT / "runs" / "demos"
    out.mkdir(parents=True, exist_ok=True)
    report = out / f"demo-{demo}.md"
    shots = sorted((ROOT / "frontend" / "test-results").glob(f"**/demo-{demo}-*/*.png"))
    shot_lines = [f"- `{p.relative_to(ROOT)}`" for p in shots] or [
        "- (see frontend/playwright-report)"
    ]
    lines = [
        f"# Demo {demo} readiness — {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        f"- Phase gate (through phase {GROUPS[demo][0]}): **{'PASS' if gate_ok else 'FAIL'}**",
        f"- Seed: stage {stage} (`make seed-demo STAGE={stage}`)",
        f"- Walkthrough `e2e/demos/demo-{demo}.spec.ts` on {', '.join(BROWSERS)} ×{REPEATS}: "
        f"**{'PASS' if walkthrough_ok else 'FAIL'}**",
        "",
        "## Captured screenshots",
        *shot_lines,
        "",
        "## Known limitations",
        "- Simulated payments and SMS; demo accounts and one-time passwords in "
        f"`runs/demos/accounts-{stage}.txt` (gitignored).",
        "- Registration, email/OTP verification and admin TOTP are shown live; the automated "
        "walkthrough focuses on the planning and sealed-bidding highlights.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="DevSync demo readiness check")
    parser.add_argument("--demo", type=int, default=1)
    args = parser.parse_args()
    if args.demo not in GROUPS:
        raise SystemExit(f"unknown demo {args.demo}")
    phase, stage = GROUPS[args.demo]

    gate = _run(["python3", "backend/scripts/phase_gate.py", "--phase", str(phase)])
    reset = _run(["make", "demo-reset", f"STAGE={stage}"])
    walk = _run(_playwright_cmd(args.demo))

    report = _write_report(
        args.demo, stage, gate.returncode == 0 and reset.returncode == 0, walk.returncode == 0
    )
    print(f"demo-check: wrote {report.relative_to(ROOT)}")
    return 0 if gate.returncode == 0 and reset.returncode == 0 and walk.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
