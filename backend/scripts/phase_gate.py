"""The phase gate (spec §16.5): `make gate PHASE=N`.

Runs the 20 gate steps in order, stops at the first failure unless
`--keep-going`, prints a summary table, writes `runs/gates/phase-N.json`,
appends the result to PROGRESS.md and writes `.phase` on PASS.

Steps for parts of the system that don't exist yet report `N/A (from phase K)`
with the reason, so the same gate grows with the project. Never weaken a step
to pass (spec §16.10).

Runs on the host with the standard library only; every Python tool runs in the
`tests` container (python:3.12) and scanners run from pinned images.

Usage:
  python3 backend/scripts/phase_gate.py --phase 0 [--keep-going] [--offline] [--only a,b]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
RUNS = ROOT / "runs" / "gates"
PROJECT = "devsync-test"
COMPOSE = [
    "docker",
    "compose",
    "-p",
    PROJECT,
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.test.yml",
]

# Pinned scanner images (update deliberately, spec §14.21).
SEMGREP_IMAGE = "semgrep/semgrep:1.95.0"
GITLEAKS_IMAGE = "zricethezav/gitleaks:v8.21.2"
TRIVY_IMAGE = "aquasec/trivy:0.57.1"
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.63.0-noble"


# Coverage thresholds by phase (spec §16.5): (backend, frontend).
def coverage_thresholds(phase: int) -> tuple[int, int]:
    """Backend/frontend line+branch coverage minimums for a phase."""
    if phase <= 3:
        return 75, 60
    if phase <= 9:
        return 85, 70
    return 90, 75


# Modules that need ≥ 95% from the phase they appear in (spec §16.5 step 9).
CRITICAL_MODULES = (
    "app/core/security.py",
    "app/core/sessions.py",
    "app/core/csrf.py",
    "app/core/authz.py",
    "app/core/ratelimit.py",
    "app/core/redirects.py",
    "app/core/money.py",
    "app/services/ledger",
    "app/uploads/",
    "app/algorithms/",
)
INITIAL_JS_BUDGET_GZIP = 250 * 1024
ROUTE_CHUNK_BUDGET_GZIP = 150 * 1024  # spec §13.7
SCENE_CHUNK_BUDGET_GZIP = 220 * 1024  # spec §13.12 (lazy 3D chunk)
SCENE_MODULE = "src/components/three/TalentConstellation.tsx"
LANDING_MODULE = "src/features/landing/LandingPage.tsx"
DEV_TOOL_MARKERS = ("UiKitPage", "StillsPage", "__stillReady")


@dataclass
class StepResult:
    """One row of the gate table."""

    number: int
    name: str
    status: str  # PASS | FAIL | N/A | SKIP
    seconds: float
    notes: str = ""


@dataclass
class Gate:
    """Gate run state."""

    phase: int
    offline: bool
    keep_going: bool
    only: set[str] = field(default_factory=set)
    results: list[StepResult] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


class StepFailed(Exception):  # noqa: N818 - reads as a verdict in step code
    """Raised by a step with a short reason."""


class NotApplicable(Exception):  # noqa: N818
    """Raised by a step that does not apply to this phase yet."""


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def run(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command; on failure raise StepFailed with the tail of its output."""
    # Plain output: the gate parses test counts, and colour codes would break that.
    merged = {
        **os.environ,
        "HOST_UID_GID": f"{os.getuid()}:{os.getgid()}",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        **(env or {}),
    }
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged,
        timeout=timeout,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if proc.stdout:
        proc.stdout = ANSI_ESCAPE.sub("", proc.stdout)
    if check and proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").strip().splitlines()[-25:])
        raise StepFailed(f"`{' '.join(cmd[:6])}…` exited {proc.returncode}\n{tail}")
    return proc


def in_tests(
    args: list[str], *, timeout: int = 1800, no_deps: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a command inside the `tests` container (python 3.12 + dev tooling)."""
    base = [*COMPOSE, "run", "--rm", "-T"]
    if no_deps:
        base.append("--no-deps")
    return run([*base, "tests", *args], timeout=timeout)


# --------------------------------------------------------------------------- steps


def step_environment(g: Gate) -> str:
    notes = []
    for tool, args in (("docker", ["--version"]), ("node", ["--version"]), ("npm", ["--version"])):
        if not shutil.which(tool):
            raise StepFailed(f"{tool} not installed")
        notes.append(run([tool, *args]).stdout.strip().split("\n")[0])
    run(["docker", "info", "--format", "{{.ServerVersion}}"])
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"]).stdout.split()
    suspicious = [f for f in untracked if re.search(r"(\.env$|\.pem$|\.key$|id_rsa|\.p12$)", f)]
    if suspicious:
        raise StepFailed(f"untracked secret-like files: {suspicious}")
    if not (ROOT / ".env").exists():
        run([sys.executable, "backend/scripts/gen_env.py"])
        notes.append("generated .env")
    if not (ROOT / "infra/nginx/certs/dev.crt").exists():
        run(["sh", "infra/nginx/make-certs.sh"])
        notes.append("generated dev cert")
    return "; ".join(notes)


def step_build(g: Gate) -> str:
    run([*COMPOSE, "--profile", "tools", "build"], timeout=3600)
    run(["npm", "ci", "--no-audit", "--no-fund"], cwd=FRONTEND, timeout=1800)
    run(["npm", "run", "build"], cwd=FRONTEND, timeout=900)
    notes = check_bundle_budget()
    if g.phase >= 2:
        notes += "; " + check_no_dev_tools()
        # Development-tools build (UI kit, stills) for the visual step; never deployed.
        run(
            ["npx", "vite", "build", "--outDir", "dist-kit", "--emptyOutDir"],
            cwd=FRONTEND,
            env={"VITE_DEV_TOOLS": "1"},
            timeout=900,
        )
    return notes


def _gzip_size(path: Path) -> int:
    import gzip  # noqa: PLC0415

    return len(gzip.compress(path.read_bytes()))


def _chunk_closure(manifest: dict[str, Any], key: str) -> set[str]:
    """Files a manifest entry needs at load time (itself + static imports, recursively)."""
    files: set[str] = set()
    stack = [key]
    seen: set[str] = set()
    while stack:
        k = stack.pop()
        if k in seen or k not in manifest:
            continue
        seen.add(k)
        files.add(manifest[k]["file"])
        stack.extend(manifest[k].get("imports", []))
    return files


def check_bundle_budget() -> str:
    """Initial JS ≤ 250 KB, homepage initial ≤ 250 KB, route chunks ≤ 150 KB, 3D chunk ≤ 220 KB
    (all gzip, spec §13.7 and §13.12)."""
    dist = FRONTEND / "dist"
    manifest = json.loads((dist / ".vite" / "manifest.json").read_text(encoding="utf-8"))
    entry = next(k for k, v in manifest.items() if v.get("isEntry"))
    initial_files = _chunk_closure(manifest, entry)
    initial = sum(_gzip_size(dist / f) for f in initial_files)
    if initial > INITIAL_JS_BUDGET_GZIP:
        raise StepFailed(f"initial JS {initial / 1024:.1f} KB gzip > 250 KB budget")
    notes = [f"initial JS {initial / 1024:.1f} KB"]
    if LANDING_MODULE in manifest:
        home_files = initial_files | _chunk_closure(manifest, LANDING_MODULE)
        home = sum(_gzip_size(dist / f) for f in home_files)
        if home > INITIAL_JS_BUDGET_GZIP:
            raise StepFailed(f"homepage initial JS {home / 1024:.1f} KB gzip > 250 KB budget")
        notes.append(f"homepage {home / 1024:.1f} KB")
    too_big = []
    for key, chunk in manifest.items():
        if not chunk["file"].endswith(".js") or chunk["file"] in initial_files:
            continue
        size = _gzip_size(dist / chunk["file"])
        limit = SCENE_CHUNK_BUDGET_GZIP if key == SCENE_MODULE else ROUTE_CHUNK_BUDGET_GZIP
        if size > limit:
            too_big.append(f"{key} {size / 1024:.1f} KB > {limit // 1024} KB")
        if key == SCENE_MODULE:
            notes.append(f"3D chunk {size / 1024:.1f} KB")
    if too_big:
        raise StepFailed(f"chunk budgets exceeded: {too_big}")
    return ", ".join(notes) + " gzip (budgets 250/150/220 KB)"


def check_no_dev_tools() -> str:
    """The UI kit and stills renderer never ship (spec §17 Phase 2 #8–9)."""
    hits = [
        f.name
        for f in (FRONTEND / "dist" / "assets").glob("*.js")
        for marker in DEV_TOOL_MARKERS
        if marker in f.read_text(encoding="utf-8")
    ]
    if hits:
        raise StepFailed(f"development tools found in the production build: {sorted(set(hits))}")
    return "no dev tools in dist"


def step_lint(g: Gate) -> str:
    in_tests(["ruff", "format", "--check", "."], no_deps=True)
    in_tests(["ruff", "check", "."], no_deps=True)
    run(["npx", "eslint", ".", "--max-warnings", "0"], cwd=FRONTEND)
    run(["npx", "prettier", "--check", "."], cwd=FRONTEND)
    return "ruff, eslint, prettier clean"


def step_types(g: Gate) -> str:
    in_tests(["mypy"], no_deps=True)
    run(["npx", "tsc", "-b", "--noEmit"], cwd=FRONTEND)
    return "mypy (strict core) + tsc strict clean"


def step_static_security(g: Gate) -> str:
    in_tests(["bandit", "-q", "-c", "pyproject.toml", "-r", "app", "-ll"], no_deps=True)
    notes = ["bandit"]
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ROOT}:/repo:ro",
            "-w",
            "/repo",
            GITLEAKS_IMAGE,
            "detect",
            "--no-git",
            "--source",
            "/repo",
            "--config",
            "/repo/.gitleaks.toml",
            "--no-banner",
            "--redact",
        ],
        timeout=600,
    )
    notes.append("gitleaks")
    if g.offline:
        notes.append("semgrep skipped (--offline: registry rules need network)")
    else:
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{ROOT}:/src",
                "-w",
                "/src",
                SEMGREP_IMAGE,
                "semgrep",
                "scan",
                "--error",
                "--metrics=off",
                "--quiet",
                "--config",
                "p/owasp-top-ten",
                "--config",
                "p/python",
                "--config",
                "p/react",
                "--config",
                "p/secrets",
                "--config",
                "infra/semgrep/devsync.yml",
                "--exclude",
                "node_modules",
                "--exclude",
                ".venv",
                "--exclude",
                "dist",
                "--exclude",
                "tests",
                "--exclude",
                "e2e",
            ],
            timeout=1800,
        )
        notes.append("semgrep")
    return ", ".join(notes) + " clean"


def step_structure(g: Gate) -> str:
    run([sys.executable, "backend/scripts/check_forbidden.py", str(ROOT)])
    in_tests(["python", "scripts/check_layers.py"], no_deps=True)
    notes = ["forbidden patterns", "layers"]
    if g.phase >= 1:
        in_tests(["python", "scripts/check_rls.py"])
        notes.append("RLS coverage")
    else:
        notes.append("RLS coverage N/A (enforced from phase 1)")
    review = ROOT / "docs" / "security-reviews" / f"phase-{g.phase:02d}.md"
    if not review.exists():
        raise StepFailed(f"missing security review {review.relative_to(ROOT)} (spec §14.22)")
    text = review.read_text(encoding="utf-8")
    match = re.search(r"Unresolved high findings:\s*(\d+)", text)
    if not match:
        raise StepFailed("security review lacks an 'Unresolved high findings: N' line")
    if int(match.group(1)) != 0:
        raise StepFailed(f"security review lists {match.group(1)} unresolved high finding(s)")
    notes.append("security review present, 0 unresolved high")
    return ", ".join(notes)


def step_dependency_audit(g: Gate) -> str:
    if g.offline:
        raise NotApplicable("--offline: dependency databases need network (recorded)")
    pip_audit = [
        "pip-audit",
        "--strict",
        "--progress-spinner",
        "off",
        "-r",
        "requirements.lock",
        "-r",
        "requirements-dev.lock",
        "--require-hashes",
        "--disable-pip",
    ]
    try:
        in_tests(pip_audit, no_deps=True)
    except StepFailed as exc:
        # A timeout reaching the advisory database is not a finding: try once more. A real
        # vulnerability fails both attempts.
        if "Timeout" not in str(exc) and "timed out" not in str(exc):
            raise
        time.sleep(10)
        in_tests(pip_audit, no_deps=True)
    run(["npm", "audit", "--audit-level=high"], cwd=FRONTEND)
    for image in ("devsync/backend:local", "devsync/nginx:local"):
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock:ro",
                "-v",
                "devsync-trivy-cache:/root/.cache/trivy",  # reuse the DB between runs
                TRIVY_IMAGE,
                "image",
                "--quiet",
                # mirror.gcr.io is unreachable from some networks; use GitHub's registry.
                "--db-repository",
                "ghcr.io/aquasecurity/trivy-db:2",
                "--java-db-repository",
                "ghcr.io/aquasecurity/trivy-java-db:1",
                "--exit-code",
                "1",
                "--ignore-unfixed",
                "--severity",
                "HIGH,CRITICAL",
                image,
            ],
            timeout=1800,
        )
    return "pip-audit, npm audit, trivy (backend, nginx) clean"


def step_migrations(g: Gate) -> str:
    run([*COMPOSE, "down", "-v", "--remove-orphans"], timeout=300)
    run([*COMPOSE, "up", "-d", "--wait", "postgres", "redis"], timeout=600)
    in_tests(["alembic", "upgrade", "head"])
    in_tests(["alembic", "downgrade", "-1"])
    in_tests(["alembic", "upgrade", "head"])
    in_tests(["alembic", "check"])
    return "upgrade → downgrade -1 → upgrade on empty DB; no model drift"


def step_backend_tests(g: Gate) -> str:
    backend_min, _ = coverage_thresholds(g.phase)
    run([*COMPOSE, "up", "-d", "--wait", "postgres", "redis", "api", "nginx"], timeout=900)
    report = "/runs/gates/coverage-backend.json"
    in_tests(
        [
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "not perf and not chaos",
            "--cov=app",
            "--cov-branch",
            f"--cov-report=json:{report}",
            f"--cov-fail-under={backend_min}",
            "--junitxml=/runs/gates/junit-backend.xml",
        ],
        timeout=3600,
    )
    data = json.loads((RUNS / "coverage-backend.json").read_text(encoding="utf-8"))
    low = []
    for path, info in data["files"].items():
        if path.startswith(CRITICAL_MODULES) and info["summary"]["percent_covered"] < 95:
            low.append(f"{path} {info['summary']['percent_covered']:.1f}%")
    if low:
        raise StepFailed(f"security-critical modules below 95%: {low}")
    junit = (RUNS / "junit-backend.xml").read_text(encoding="utf-8")
    tests = int(re.search(r'tests="(\d+)"', junit).group(1))  # type: ignore[union-attr]
    skipped = int(re.search(r'skipped="(\d+)"', junit).group(1))  # type: ignore[union-attr]
    g.counts["backend_tests"] = tests - skipped
    total = data["totals"]["percent_covered"]
    return (
        f"{tests - skipped} passed, {skipped} skipped; coverage {total:.1f}% (min {backend_min}%)"
    )


def step_security_suite(g: Gate) -> str:
    if g.phase < 1:
        raise NotApplicable("security suite must be non-empty from phase 1")
    proc = in_tests(["pytest", "-q", "-p", "no:cacheprovider", "-m", "security"])
    if "no tests ran" in proc.stdout or " passed" not in proc.stdout:
        raise StepFailed("security suite is empty")
    return proc.stdout.strip().splitlines()[-1]


def step_api_contract(g: Gate) -> str:
    in_tests(["python", "scripts/check_openapi.py"], no_deps=True)
    if g.phase < 1:
        return "contract lint + committed openapi.json match; fuzzing from phase 1"
    in_tests(["pytest", "-q", "-p", "no:cacheprovider", "-m", "fuzz"])
    return "contract lint, openapi.json match, schemathesis clean"


def step_frontend_tests(g: Gate) -> str:
    _, frontend_min = coverage_thresholds(g.phase)
    out = run(
        [
            "npx",
            "vitest",
            "run",
            "--coverage",
            "--coverage.reporter=json-summary",
            "--coverage.reporter=text-summary",
            f"--coverage.thresholds.lines={frontend_min}",
            f"--coverage.thresholds.branches={frontend_min}",
            f"--coverage.thresholds.functions={frontend_min}",
            f"--coverage.thresholds.statements={frontend_min}",
        ],
        cwd=FRONTEND,
    ).stdout
    passed = re.search(r"Tests\s+(\d+) passed", out)
    g.counts["frontend_tests"] = int(passed.group(1)) if passed else 0
    summary = json.loads((FRONTEND / "coverage/coverage-summary.json").read_text(encoding="utf-8"))
    lines = summary["total"]["lines"]["pct"]
    return f"{g.counts['frontend_tests']} passed; coverage {lines}% lines (min {frontend_min}%)"


def _playwright(
    g: Gate,
    grep: str,
    projects: list[str],
    *,
    env: dict[str, str] | None = None,
    before: str = "",
    command: str | None = None,
    image: str = PLAYWRIGHT_IMAGE,
    docker_args: tuple[str, ...] = (),
) -> str:
    """Run Playwright (or `command`) in the pinned image on the nginx container's network."""
    nginx = run([*COMPOSE, "ps", "-q", "nginx"]).stdout.strip()
    if not nginx:
        raise StepFailed("nginx container is not running")
    args = ["npx", "playwright", "test", "--grep", grep, "--reporter=list"]
    for p in projects:
        args += ["--project", p]
    script = f"{before}{command or ' '.join(args)}"
    env_args: list[str] = []
    # HOME inside the throwaway Playwright container (not a host temp file).
    container_env = {"E2E_BASE_URL": "https://localhost:8443", "HOME": "/tmp", **(env or {})}  # noqa: S108
    for key, value in container_env.items():
        env_args += ["-e", f"{key}={value}"]
    proc = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            f"container:{nginx}",
            "-v",
            f"{FRONTEND}:/web",
            "-v",
            f"{RUNS}:/runs",
            "-w",
            "/web",
            *env_args,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--ipc=host",
            *docker_args,
            image,
            "sh",
            "-c",
            script,
        ],
        timeout=3600,
    )
    last = [
        ln
        for ln in proc.stdout.splitlines()
        if "passed" in ln or "failed" in ln or "LIGHTHOUSE" in ln or "fps" in ln
    ]
    return last[-1].strip() if last else "ok"


DEMO_PHASES = {5, 12, 15}

# Runs inside the test network; the dev certificate is self-signed.
HEALTH_PROBE = (
    "import httpx\n"
    "r = httpx.get('https://nginx:8443/api/v1/health',\n"
    "    verify=False,\n"  # forbidden-ok: self-signed dev cert, internal test network
    "    headers={'Host': 'localhost'})\n"
    "print(r.status_code, r.headers.get('content-security-policy'))"
)


def step_e2e(g: Gate) -> str:
    projects = (
        ["chromium", "firefox", "webkit", "mobile"] if g.phase in DEMO_PHASES else ["chromium"]
    )
    repeats = 3 if g.phase in DEMO_PHASES else 1
    notes = []
    for _ in range(repeats):
        notes.append(_playwright(g, "@e2e", projects))
    # Edge behaviour (HTTPS redirect, headers, limits) is checked from inside the network.
    edge = in_tests(["pytest", "-q", "-p", "no:cacheprovider", "-m", "edge"])
    notes.append("edge: " + edge.stdout.strip().splitlines()[-1])
    return "; ".join(notes)


def step_a11y(g: Gate) -> str:
    return _playwright(g, "@a11y", ["chromium"])


GPU_IMAGE = "devsync-playwright-gpu:1.63.0"


# Mesa drivers by vendor: Intel (ANV) and AMD (RADV) are mature; NVIDIA's open NVK driver
# stalls the GPU process intermittently, so it is used only when nothing else exists.
PREFERRED_GPU_VENDORS = ("0x8086", "0x1002")


def _gpu_device_args() -> tuple[str, ...]:
    """Pass one GPU into the container (spec §13.12 measures 60 fps on real hardware)."""
    nodes = sorted(Path("/sys/class/drm").glob("renderD*"))
    if not nodes:
        raise StepFailed("the 3D frame-rate check needs a GPU (/dev/dri); run the gate on a laptop")

    def vendor(node: Path) -> str:
        try:
            return (node / "device" / "vendor").read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    chosen = next((n for n in nodes if vendor(n) in PREFERRED_GPU_VENDORS), nodes[0])
    render = Path("/dev/dri") / chosen.name
    cards = [
        Path("/dev/dri") / c.name
        for c in (chosen / "device" / "drm").iterdir()
        if c.name.startswith("card")
    ]
    args: list[str] = []
    for dev in [render, *cards]:
        args += ["--device", str(dev), "--group-add", str(dev.stat().st_gid)]
    return tuple(args)


def _gpu_image() -> str:
    run(
        ["docker", "build", "-q", "-t", GPU_IMAGE, str(ROOT / "infra" / "playwright-gpu")],
        timeout=1800,
    )
    return GPU_IMAGE


KIT_SERVER = (
    "npx vite preview --outDir dist-kit --port 4173 --strictPort --host 127.0.0.1 "
    ">/tmp/kit.log 2>&1 & sleep 3; "
)


def step_visual(g: Gate) -> str:
    if g.phase < 2:
        raise NotApplicable("visual regression starts in phase 2")
    baselines = FRONTEND / "e2e" / "__screenshots__"
    if not baselines.exists() or not any(baselines.rglob("*.png")):
        raise StepFailed("no visual baselines committed (run `make visual-update`)")
    note = _playwright(
        g, "@visual", ["chromium"], env={"KIT_URL": "http://127.0.0.1:4173"}, before=KIT_SERVER
    )
    count = len(list(baselines.rglob("*.png")))
    return f"{note}; {count} baselines"


def step_performance(g: Gate) -> str:
    if g.phase < 2:
        raise NotApplicable("performance budgets start in phase 2")
    notes = []
    lighthouse = _playwright(
        g,
        "",
        [],
        env={"LH_URL": "https://localhost:8443/", "LH_OUT": "/runs/lighthouse.json"},
        command="node scripts/lighthouse.mjs",
    )
    notes.append(lighthouse)
    fps = _playwright(
        g, "@perf", ["chromium-gpu"], image=_gpu_image(), docker_args=_gpu_device_args()
    )
    notes.append(f"frame rate on the GPU: {fps}")
    if g.phase >= 4:
        in_tests(["pytest", "-q", "-p", "no:cacheprovider", "-m", "perf"])
        notes.append("algorithm budgets met")
    summary = json.loads((RUNS / "lighthouse.json").read_text(encoding="utf-8"))
    scores = "; ".join(
        f"{r['profile']} {r['scores']['performance']}/{r['scores']['accessibility']}/"
        f"{r['scores']['best-practices']}/{r['scores']['seo']} LCP {r['lcpMs']}ms"
        for r in summary["results"]
    )
    return f"Lighthouse {scores}; " + "; ".join(notes[1:])


def step_dast(g: Gate) -> str:
    if g.phase < 9:
        raise NotApplicable("ZAP baseline starts in phase 9")
    raise StepFailed("DAST step not implemented yet")


def step_phase_checks(g: Gate) -> str:
    checks: dict[int, Callable[[Gate], str]] = {
        0: phase0_checks,
        1: phase1_checks,
        2: phase2_checks,
        3: phase3_checks,
        4: phase4_checks,
        5: phase5_checks,
    }
    if g.phase not in checks:
        raise StepFailed(f"no PHASE_CHECKS defined for phase {g.phase}")
    return checks[g.phase](g)


def phase0_checks(g: Gate) -> str:
    ps = run([*COMPOSE, "ps", "--format", "json"]).stdout.strip()
    services = [json.loads(line) for line in ps.splitlines() if line.strip()]
    unhealthy = [s["Service"] for s in services if s.get("Health") not in ("healthy", "")]
    if unhealthy:
        raise StepFailed(f"unhealthy services: {unhealthy}")
    probe = in_tests(["python", "-c", HEALTH_PROBE])
    # Compose prints container status lines first; the probe's answer is the last line.
    answer = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
    if not answer.startswith("200") or not answer.endswith("form-action 'none'"):
        raise StepFailed(f"health via nginx: {answer}")
    return f"{len(services)} services healthy; https health 200 with headers"


AUDIT_CHAIN_CHECK = (
    "import os\n"
    "from sqlalchemy import create_engine, text\n"
    "e = create_engine(os.environ['MIGRATION_DATABASE_URL'])\n"
    "with e.connect() as c:\n"
    "    broken = c.execute(text('SELECT audit_verify_chain()')).scalar()\n"
    "    rows = c.execute(text('SELECT count(*) FROM audit_log')).scalar()\n"
    "print(f'rows={rows} broken={broken}')\n"
    "raise SystemExit(0 if broken is None and rows > 0 else 1)\n"
)


def phase1_checks(g: Gate) -> str:
    """Spec §17 Phase 1 gate checks."""
    phase0_checks(g)
    in_tests(
        [
            "pytest", "-q", "-p", "no:cacheprovider",
            "tests/security/test_registration_verification.py::test_full_registration_and_verification",
            "tests/security/test_admin_totp.py::test_admin_totp_success_and_wrong_code",
            "tests/security/test_login_sessions.py::test_login_rate_limit",
        ]
    )  # fmt: skip
    audit = in_tests(["python", "-c", AUDIT_CHAIN_CHECK]).stdout.strip().splitlines()[-1]
    return f"register+verify+login, admin TOTP, login 429 observed; audit chain intact ({audit})"


STILLS = FRONTEND / "src" / "assets" / "stills"


def stills_hash(files: list[str]) -> str:
    """Same hash as scripts/render-stills.mjs: sha256 over the scene files and tokens."""
    digest = hashlib.sha256()
    for name in files:
        digest.update((FRONTEND / name).read_bytes())
    return digest.hexdigest()


def phase2_checks(g: Gate) -> str:
    """Spec §17 Phase 2 gate checks."""
    p1 = phase1_checks(g)
    manifest = json.loads((STILLS / "stills-manifest.json").read_text(encoding="utf-8"))
    if stills_hash(manifest["hashed"]) != manifest["hash"]:
        raise StepFailed("stills are out of date with the scene or tokens (run `make stills`)")
    missing = [f for f in manifest["files"] if not (STILLS / f).exists()]
    if missing or not (FRONTEND / "public" / "social-preview.png").exists():
        raise StepFailed(f"missing stills: {missing or ['public/social-preview.png']}")
    skill = ROOT / ".claude" / "skills" / "devsync-ui" / "SKILL.md"
    if not skill.exists():
        raise StepFailed("devsync-ui skill missing (.claude/skills/devsync-ui/SKILL.md)")
    plan = (ROOT / "docs" / "plans" / "phase-02.md").read_text(encoding="utf-8")
    if "devsync-ui" not in plan:
        raise StepFailed("devsync-ui skill not listed in docs/plans/phase-02.md")
    check_no_dev_tools()
    return (
        f"{p1}; stills current ({len(manifest['files'])} files, "
        f"hash {manifest['hash'][:12]}); devsync-ui skill present and listed; no dev tools in dist"
    )


def phase3_checks(g: Gate) -> str:
    """Spec §17 Phase 3 gate checks: a crafted polyglot upload is rejected, a signed URL
    expires (and a tampered one is refused), and test answers are absent from API responses."""
    p2 = phase2_checks(g)
    in_tests(
        [
            "pytest", "-q", "-p", "no:cacheprovider",
            "tests/security/test_profiles_files.py::test_dangerous_uploads_are_rejected",
            "tests/unit/test_uploads.py::test_appended_archive_is_rejected",
            "tests/unit/test_uploads.py::test_jpeg_polyglot_ending_in_an_end_marker_is_still_rejected",
            "tests/security/test_profiles_files.py::test_signed_url_expires_and_tampering_is_refused",
            "tests/unit/test_uploads.py::test_signed_url_expires",
            "tests/security/test_skill_tests.py::test_response_schemas_have_no_answer_fields",
            "tests/security/test_skill_tests.py::test_full_lifecycle_scores_and_adds_evidence",
            "tests/unit/test_question_bank_seed.py",
        ]
    )  # fmt: skip
    plan = (ROOT / "docs" / "plans" / "phase-03.md").read_text(encoding="utf-8")
    if "devsync-ui" not in plan:
        raise StepFailed("devsync-ui skill not listed in docs/plans/phase-03.md")
    return (
        f"{p2}; polyglot uploads rejected; signed URL expiry and tamper refused; "
        "answers absent from test responses; question bank seed valid"
    )


def phase4_checks(g: Gate) -> str:
    """Spec §17 Phase 4 gate checks: the §18.2 "Online ordering system" plan reproduces the
    documented CPM (duration 24, the critical path and Frontend's slack 4), a dependency cycle
    is rejected, the publish guards hold, and draft projects stay private in the database."""
    p3 = phase3_checks(g)
    in_tests(
        [
            "pytest", "-q", "-p", "no:cacheprovider",
            "tests/algorithms/test_cpm.py::test_ordering_system_matches_spec_18_2",
            "tests/algorithms/test_cpm.py::test_cycle_is_detected_and_reported_in_order",
            "tests/security/test_projects.py::test_preview_matches_spec_18_2",
            "tests/security/test_projects.py::test_dependency_cycle_rejected",
            "tests/security/test_projects.py::test_publish_requires_payment_then_succeeds",
            "tests/security/test_projects.py::test_editing_after_publish_is_rejected",
            "tests/integration/test_rls_projects.py::test_draft_is_private_but_bidding_is_public",
        ]
    )  # fmt: skip
    if not (ROOT / "docs" / "plans" / "phase-04.md").exists():
        raise StepFailed("docs/plans/phase-04.md is missing")
    if not (ROOT / "docs" / "design" / "erd.svg").exists():
        raise StepFailed("docs/design/erd.svg is missing (run `make erd`)")
    return (
        f"{p3}; §18.2 CPM golden values verified; dependency cycle rejected; publish guards "
        "hold; draft projects private in the DB; ERD generated"
    )


def phase5_checks(g: Gate) -> str:
    """Spec §17 Phase 5 gate checks: the §18.4 stage-1 seed reproduces the documented eligible /
    ineligible counts and reasons for "Online ordering system" (10 eligible; Shakib TOO_SLOW,
    Lamia NO_SKILL_EVIDENCE); Algorithm 1 boundaries and the newcomer rule hold; bids are sealed
    between developers; and the bidding-deadline job behaves."""
    p4 = phase4_checks(g)
    # The seed self-asserts the §18.4 counts (it exits non-zero on any mismatch).
    in_tests(["python", "scripts/seed_demo.py", "--stage", "1"])
    in_tests(
        [
            "pytest", "-q", "-p", "no:cacheprovider",
            "tests/algorithms/test_filtering.py::test_equal_to_every_threshold_passes",
            "tests/algorithms/test_filtering.py::test_newcomer_no_skill_evidence",
            "tests/algorithms/test_filtering.py::test_relaxation_reported_and_finds_candidates",
            "tests/security/test_bids.py::test_bids_are_sealed_between_developers",
            "tests/integration/test_rls_bids.py::test_a_bid_is_sealed_from_other_developers",
            "tests/jobs/test_bidding_deadline.py::test_too_few_bids_stays_bidding_notifies_once",
        ]
    )  # fmt: skip
    if not (ROOT / "docs" / "plans" / "phase-05.md").exists():
        raise StepFailed("docs/plans/phase-05.md is missing")
    return (
        f"{p4}; §18.4 stage-1 seed reproduces 10 eligible + TOO_SLOW/NO_SKILL_EVIDENCE; "
        "Algorithm 1 boundaries + newcomer rule; bids sealed; bidding-deadline job verified"
    )


def step_regression_guard(g: Gate) -> str:
    baseline_file = RUNS / "baseline.json"
    current = dict(g.counts)
    if not baseline_file.exists():
        return f"baseline created on PASS: {current}"
    baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
    dropped = {
        k: (baseline[k], current.get(k, 0)) for k in baseline if current.get(k, 0) < baseline[k]
    }
    if dropped:
        raise StepFailed(
            f"test counts dropped (baseline → now): {dropped}; needs a DECISIONS.md entry"
        )
    return f"no tests removed: {current} (baseline {baseline})"


STEPS: list[tuple[str, str, Callable[[Gate], str]]] = [
    ("environment", "Environment", step_environment),
    ("build", "Build", step_build),
    ("lint", "Format & lint", step_lint),
    ("types", "Types", step_types),
    ("static-security", "Static security", step_static_security),
    ("forbidden", "Forbidden patterns / layers / RLS / review", step_structure),
    ("deps", "Dependency audit", step_dependency_audit),
    ("migrations", "Migrations", step_migrations),
    ("backend-tests", "Backend tests", step_backend_tests),
    ("security-suite", "Security suite", step_security_suite),
    ("api-contract", "API contract", step_api_contract),
    ("frontend-tests", "Frontend tests", step_frontend_tests),
    ("e2e", "E2E", step_e2e),
    ("a11y", "Accessibility", step_a11y),
    ("visual", "Visual regression", step_visual),
    ("perf", "Performance", step_performance),
    ("dast", "DAST", step_dast),
    ("phase-checks", "Phase-specific checks", step_phase_checks),
    ("regression", "Regression guard", step_regression_guard),
]


def print_table(results: list[StepResult]) -> None:
    print("\n step | status | time    | name                                       | notes")
    print("------+--------+---------+--------------------------------------------+------")
    for r in results:
        note = r.notes.splitlines()[0] if r.notes else ""
        print(f" {r.number:>4} | {r.status:<6} | {r.seconds:>6.1f}s | {r.name:<42} | {note}")


def write_report(g: Gate, passed: bool, failed_step: int | None) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    report = {
        "phase": g.phase,
        "result": "PASS" if passed else "FAIL",
        "failed_step": failed_step,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "offline": g.offline,
        "counts": g.counts,
        "steps": [asdict(r) for r in g.results],
    }
    (RUNS / f"phase-{g.phase}.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    progress = ROOT / "PROGRESS.md"
    if progress.exists() and not g.only:
        line = (
            f"| {report['finished_at']} | phase {g.phase} | {report['result']}"
            f"{f' (step {failed_step})' if failed_step else ''} | "
            f"backend {g.counts.get('backend_tests', '-')} / "
            f"frontend {g.counts.get('frontend_tests', '-')} tests |\n"
        )
        text = progress.read_text(encoding="utf-8")
        marker = "<!-- gate-log -->\n"
        if marker in text:
            text = text.replace(marker, marker + line, 1)
            progress.write_text(text, encoding="utf-8")
    if passed and not g.only:
        (ROOT / ".phase").write_text(f"{g.phase}\n", encoding="utf-8")
        baseline = RUNS / "baseline.json"
        old = json.loads(baseline.read_text(encoding="utf-8")) if baseline.exists() else {}
        merged = {k: max(old.get(k, 0), v) for k, v in {**old, **g.counts}.items()}
        baseline.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--only", default="", help="comma-separated step keys")
    args = parser.parse_args(argv[1:])
    g = Gate(
        phase=args.phase,
        offline=args.offline,
        keep_going=args.keep_going,
        only={s for s in args.only.split(",") if s},
    )
    RUNS.mkdir(parents=True, exist_ok=True)
    failed_step: int | None = None
    for number, (key, name, fn) in enumerate(STEPS, start=1):
        if g.only and key not in g.only:
            continue
        start = time.monotonic()
        print(f"\n=== step {number}: {name} ===", flush=True)
        try:
            notes = fn(g)
            result = StepResult(number, name, "PASS", time.monotonic() - start, notes)
        except NotApplicable as exc:
            result = StepResult(number, name, "N/A", time.monotonic() - start, str(exc))
        except (StepFailed, subprocess.TimeoutExpired, OSError, KeyError, ValueError) as exc:
            result = StepResult(number, name, "FAIL", time.monotonic() - start, str(exc))
            print(str(exc))
            failed_step = failed_step or number
        g.results.append(result)
        first_note = result.notes.splitlines()[0] if result.notes else ""
        print(f"--> {result.status} ({result.seconds:.1f}s) {first_note}")
        if result.status == "FAIL" and not g.keep_going:
            break
    passed = failed_step is None
    g.results.append(
        StepResult(
            20, "Report", "PASS" if passed else "FAIL", 0.0, f"runs/gates/phase-{g.phase}.json"
        )
    )
    write_report(g, passed, failed_step)
    print_table(g.results)
    verdict = (
        f"PHASE {g.phase} GATE: PASS"
        if passed
        else f"PHASE {g.phase} GATE: FAIL (step {failed_step})"
    )
    if g.only:
        verdict += f"  [partial run: {','.join(sorted(g.only))}]"
    print(f"\n{verdict}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
