"""Demo readiness check (spec §17.0, §13.8 item 10): `make demo-check DEMO=N`.

For a demo group it
1. runs the phase gate for the group's last phase (which chains the earlier phases);
2. resets and loads that stage's seed — on the demo stack (`make demo-reset`) **and** on the test
   stack the walkthrough drives. The test stack gets a fresh random `DEMO_PASSWORD`, passed by
   name (never on a command line) to the seed and to Playwright, so the walkthrough can sign in
   as the seeded client;
3. runs the scripted walkthrough `e2e/demos/demo-N.spec.ts` on chromium, firefox, webkit and a
   mobile viewport, three times, with video;
4. collects the artefacts into `runs/demos/`: the step screenshots (`demo-N/<browser>/r<k>/`), the
   video (`demo-N.webm`, chromium, first run), the report `demo-N.md` (gate table from
   `runs/gates/phase-P.json`, a screenshot per step, known limitations) and the consistency
   gallery `demo-N-gallery.html` (every step in light and dark, desktop and mobile; static, no
   scripts).

`--report-only` skips 1–3 and rebuilds the report and gallery from the last run's files.
Run from the repo root with the demo stack up (`make demo-up`).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = ROOT / "runs"
DEMOS = RUNS / "demos"
TEST_RESULTS = ROOT / "frontend" / "test-results"
# DEMO → (last phase of the group, seed stage).
GROUPS = {1: (5, 1), 2: (12, 2), 3: (15, 3)}
BROWSERS = ("chromium", "firefox", "webkit", "mobile")
DESKTOP, MOBILE = "chromium", "mobile"
REPEATS = 3
# Gate notes can hold a whole tool log; the table keeps the start (the gate JSON has it all).
NOTES_MAX = 240

TEST_COMPOSE = [
    "docker", "compose", "-p", "devsync-test",
    "-f", "docker-compose.yml", "-f", "docker-compose.test.yml",
]  # fmt: skip

KNOWN_LIMITATIONS = {
    1: [
        "Payments and the payment-method check are simulated (D39); texts and emails are "
        "delivered to the local Mailpit on the demo stack (http://127.0.0.1:8025).",
        "Reputations of experienced developers are fixed Stage-1 snapshots (D44); the Phase 6 "
        "engine computes them from Demo 2 on. Newcomers use the §9.1.3 starting values.",
        "TOO_SLOW compares a bid with the whole-project deadline, not the slot's milestones "
        "(the paper's simplification, D54); availability is re-checked at invitation (Phase 8).",
        "The automated walkthrough runs on the test stack (test-only helpers read codes, links, "
        "TOTP and the skill test's answer key); live, the presenter reads codes from Mailpit and "
        "the admin TOTP secret from `runs/demos/accounts-1.txt` (gitignored).",
        "Demo accounts' passwords are random per reset (printed once to "
        "`runs/demos/accounts-1.txt`); `DEMO_PASSWORD=…` gives a fixed one for rehearsals.",
    ],
}


@dataclass(frozen=True)
class Step:
    """One captured walkthrough step (from the spec's steps.json)."""

    file: str
    dark: str | None
    caption: str


def _run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT, text=True, check=False, env=env)


def _seed_test_stack(stage: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Wipe users and load the stage seed on the test stack (the walkthrough's backend)."""
    return _run(
        [
            *TEST_COMPOSE, "run", "--rm", "-T", "-e", "DEMO_PASSWORD", "tests", "sh", "-c",
            f"python scripts/demo_reset.py && python scripts/seed_demo.py --stage {stage}",
        ],
        env,
    )  # fmt: skip


def _playwright_cmd(demo: int) -> list[str]:
    """Run the walkthrough in the pinned Playwright image on the test stack's nginx network."""
    nginx = subprocess.run(
        [*TEST_COMPOSE, "ps", "-q", "nginx"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    projects = [a for b in BROWSERS for a in ("--project", b)]
    return [
        "docker", "run", "--rm", f"--network=container:{nginx}", "--ipc=host",
        # As the current user, so test-results stay removable (the gate's E2E step clears it).
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{ROOT}/frontend:/web", "-w", "/web", "-e", "HOME=/tmp",
        "-e", "E2E_BASE_URL=https://localhost:8443", "-e", "DEMO_PASSWORD",
        "mcr.microsoft.com/playwright:v1.63.0-noble",
        "npx", "playwright", "test", f"e2e/demos/demo-{demo}.spec.ts",
        *projects, f"--repeat-each={REPEATS}", "--reporter=list",
    ]  # fmt: skip


# --------------------------------------------------------------------------- artefacts


def collect(demo: int) -> tuple[Path, Path | None]:
    """Copy the step screenshots and the chromium video of the first run into runs/demos."""
    DEMOS.mkdir(parents=True, exist_ok=True)
    shots_src = TEST_RESULTS / f"demo-{demo}-shots"
    shots_dst = DEMOS / f"demo-{demo}"
    if shots_src.is_dir():
        shutil.rmtree(shots_dst, ignore_errors=True)
        shutil.copytree(shots_src, shots_dst)
    video = first_video(TEST_RESULTS, demo)
    target: Path | None = None
    if video is not None:
        target = DEMOS / f"demo-{demo}.webm"
        shutil.copyfile(video, target)
    return shots_dst, target


def first_video(results: Path, demo: int) -> Path | None:
    """The desktop-chromium video of the first repeat (folders of later repeats end -repeatN)."""
    candidates = [
        v
        for v in results.glob("*/video.webm")
        if f"demo-{demo}" in v.parent.name
        and v.parent.name.endswith(f"-{DESKTOP}")
        and "repeat" not in v.parent.name
    ]
    return sorted(candidates)[0] if candidates else None


def load_steps(shots: Path, browser: str, repeat: int = 0) -> list[Step]:
    path = shots / browser / f"r{repeat}" / "steps.json"
    if not path.is_file():
        return []
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [Step(str(s["file"]), s.get("dark"), str(s["caption"])) for s in raw]


def load_gate(phase: int) -> dict[str, Any] | None:
    path = RUNS / "gates" / f"phase-{phase}.json"
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def gate_lines(phase: int, gate: dict[str, Any] | None, ran_ok: bool | None) -> list[str]:
    """The gate result line and table. The line states the recorded result; when this run's
    gate exit code disagrees with the file (e.g. the gate stopped before writing), say so."""
    if gate is None:
        result = "not run" if ran_ok is None else ("PASS" if ran_ok else "FAIL")
        return [f"- Phase gate (through phase {phase}): **{result}** (no runs/gates file)"]
    result = str(gate.get("result", "UNKNOWN"))
    failed = gate.get("failed_step")
    line = (
        f"- Phase gate (through phase {phase}): **{result}**"
        + (f" at step {failed}" if result != "PASS" and failed else "")
        + f", finished {gate.get('finished_at', '?')}"
        + (" (offline)" if gate.get("offline") else "")
    )
    lines = [line]
    if ran_ok is not None and ran_ok != (result == "PASS"):
        lines.append(
            f"- Note: this run's gate exited {'0' if ran_ok else 'non-zero'}, which does not "
            "match the recorded result above."
        )
    lines += ["", "| Step | Name | Result | Seconds | Notes |", "|---|---|---|---|---|"]
    for s in gate.get("steps", []):
        lines.append(
            f"| {_cell(s.get('number', ''))} | {_cell(s.get('name', ''))} | "
            f"{_cell(s.get('status', ''))} | {float(s.get('seconds', 0)):.0f} | "
            f"{_cell(s.get('notes', ''))[:NOTES_MAX]} |"
        )
    return lines


def write_report(
    demo: int,
    *,
    gate_ran_ok: bool | None,
    seeded: bool | None,
    walkthrough_ok: bool | None,
    video: Path | None,
) -> Path:
    phase, stage = GROUPS[demo]
    shots = DEMOS / f"demo-{demo}"
    desktop = load_steps(shots, DESKTOP)
    mobile = {s.file: s for s in load_steps(shots, MOBILE)}

    def verdict(v: bool | None) -> str:
        return "not run (--report-only)" if v is None else ("PASS" if v else "FAIL")

    lines = [
        f"# Demo {demo} readiness — {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        *gate_lines(phase, load_gate(phase), gate_ran_ok),
        "",
        f"- Seed: stage {stage} on the demo and test stacks: **{verdict(seeded)}**",
        f"- Walkthrough `e2e/demos/demo-{demo}.spec.ts` on {', '.join(BROWSERS)} ×{REPEATS}: "
        f"**{verdict(walkthrough_ok)}**",
        "- Video (chromium, first run): "
        + (f"[{video.name}]({video.name})" if video else "not recorded"),
        f"- Consistency gallery (light/dark, desktop/mobile): "
        f"[demo-{demo}-gallery.html](demo-{demo}-gallery.html)",
        "",
        "## Walkthrough steps",
    ]
    if not desktop:
        lines.append("- No screenshots captured (the walkthrough did not run or failed early).")
    for i, step in enumerate(desktop, start=1):
        lines += ["", f"### {i}. {step.caption}", ""]
        lines.append(f"![{step.caption}](demo-{demo}/{DESKTOP}/r0/{step.file})")
        links = []
        if step.dark:
            links.append(f"[dark](demo-{demo}/{DESKTOP}/r0/{step.dark})")
        m = mobile.get(step.file)
        if m is not None:
            links.append(f"[mobile](demo-{demo}/{MOBILE}/r0/{m.file})")
            if m.dark:
                links.append(f"[mobile dark](demo-{demo}/{MOBILE}/r0/{m.dark})")
        if links:
            lines += ["", "Also: " + " · ".join(links)]
    lines += ["", "## Known limitations", *(f"- {x}" for x in KNOWN_LIMITATIONS.get(demo, []))]
    report = DEMOS / f"demo-{demo}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


GALLERY_CSS = """
:root { --bg:#f7f7f8; --fg:#16181d; --muted:#5b6170; --card:#fff; --line:#dfe1e6; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111317; --fg:#eceef2; --muted:#9aa1ae; --card:#1a1d23; --line:#2c3039; }
}
* { box-sizing: border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size:22px; margin:0 0 4px; } p.lead { color:var(--muted); margin:0 0 24px; }
section { background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:16px; margin:0 0 20px; }
h2 { font-size:16px; margin:0 0 12px; }
.grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));
  align-items:start; }
figure { margin:0; } figcaption { color:var(--muted); font-size:13px; margin-bottom:6px; }
img { display:block; width:100%; height:auto; border:1px solid var(--line); border-radius:8px; }
.missing { color:var(--muted); font-style:italic; font-size:13px; }
"""


def write_gallery(demo: int) -> Path:
    """Every walkthrough step side by side: desktop and mobile, light and dark (§13.8 item 10)."""
    shots = DEMOS / f"demo-{demo}"
    desktop = load_steps(shots, DESKTOP)
    mobile = {s.file: s for s in load_steps(shots, MOBILE)}

    def figure(label: str, browser: str, file: str | None) -> str:
        if not file:
            missing = '<p class="missing">not captured</p>'
            return f"<figure><figcaption>{label}</figcaption>{missing}</figure>"
        src = html.escape(f"demo-{demo}/{browser}/r0/{file}", quote=True)
        return (
            f"<figure><figcaption>{label}</figcaption>"
            f'<a href="{src}"><img src="{src}" alt="{html.escape(label)}" loading="lazy"></a>'
            "</figure>"
        )

    sections = []
    for i, step in enumerate(desktop, start=1):
        m = mobile.get(step.file)
        sections.append(
            f'<section><h2>{i}. {html.escape(step.caption)}</h2><div class="grid">'
            + figure("Desktop · light", DESKTOP, step.file)
            + figure("Desktop · dark", DESKTOP, step.dark)
            + figure("Mobile · light", MOBILE, m.file if m else None)
            + figure("Mobile · dark", MOBILE, m.dark if m else None)
            + "</div></section>"
        )
    if not sections:
        sections.append('<p class="missing">No screenshots captured yet: run make demo-check.</p>')
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Demo {demo} gallery</title><style>{GALLERY_CSS}</style></head><body>"
        f"<h1>Demo {demo} screen gallery</h1>"
        f'<p class="lead">Every walkthrough step in light and dark, desktop (Chromium) and mobile '
        f"(iPhone 14), from the first run of {datetime.now(UTC).date().isoformat()}. Review them "
        "side by side for consistency before presenting.</p>" + "".join(sections) + "</body></html>"
    )
    out = DEMOS / f"demo-{demo}-gallery.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="DevSync demo readiness check")
    parser.add_argument("--demo", type=int, default=1)
    parser.add_argument(
        "--report-only", action="store_true", help="rebuild report and gallery from the last run"
    )
    args = parser.parse_args()
    if args.demo not in GROUPS:
        raise SystemExit(f"unknown demo {args.demo}")
    phase, stage = GROUPS[args.demo]

    gate_ok = seeded = walk_ok = None
    if not args.report_only:
        gate_ok = (
            _run(["python3", "backend/scripts/phase_gate.py", "--phase", str(phase)]).returncode
            == 0
        )
        reset = _run(["make", "demo-reset", f"STAGE={stage}"])
        # A fresh password for the test stack's demo accounts, known only to this run.
        env = {**os.environ, "DEMO_PASSWORD": secrets.token_urlsafe(18)}
        test_seed = _seed_test_stack(stage, env)
        seeded = reset.returncode == 0 and test_seed.returncode == 0
        walk_ok = _run(_playwright_cmd(args.demo), env).returncode == 0

    _shots, video = collect(args.demo)
    if video is None:
        existing = DEMOS / f"demo-{args.demo}.webm"
        video = existing if existing.is_file() else None
    report = write_report(
        args.demo, gate_ran_ok=gate_ok, seeded=seeded, walkthrough_ok=walk_ok, video=video
    )
    gallery = write_gallery(args.demo)
    print(f"demo-check: wrote {report.relative_to(ROOT)} and {gallery.relative_to(ROOT)}")
    if args.report_only:
        return 0
    return 0 if gate_ok and seeded and walk_ok else 1


if __name__ == "__main__":
    sys.exit(main())
