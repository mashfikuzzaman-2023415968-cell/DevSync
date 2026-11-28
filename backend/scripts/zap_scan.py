"""DAST: ZAP's passive (baseline) scan of the running test stack (spec §16.6; D157, D171).

Used by `make zap` and gate step 17. Run on the host from the repository root, with the test
stack up (`make test-stack-up`):

1. `zap_session.py` (in the `tests` container) seeds a developer and signs in through Nginx; the
   session cookie comes back on stdout and is handed to ZAP only (never logged or written to the
   report folder; the plan that carries it is deleted after the scan).
2. ZAP (`zaproxy/zap-stable`, pinned by tag and digest, D171) runs an Automation Framework plan
   inside Nginx's network namespace against `https://localhost:8443`: the session is added to
   every request by the replacer; the spider and the client spider start from the public pages
   and the main signed-in pages and API reads (a workspace included); the test-only router,
   sign-out, the SSE streams and signed file URLs are excluded; passive rules only (nothing is
   attacked or changed). ZAP accepts the test stack's self-signed certificate; TLS stays on.
3. The JSON report decides: any High or Medium alert fails, unless `infra/zap/ignore.json` lists
   that alert with the DECISIONS entry that shows it is a false positive (the entry must exist).

Reports: `runs/zap/<UTC timestamp>/` (report.json, report.html, summary.txt). Exit 0 = pass.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMAGE = (
    "zaproxy/zap-stable:2.17.0@sha256:"
    "9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af"
)
COMPOSE = [
    "docker", "compose", "-p", "devsync-test",
    "-f", "docker-compose.yml", "-f", "docker-compose.test.yml",
]  # fmt: skip
NGINX = "devsync-test-nginx-1"
TARGET = "https://localhost:8443"
IGNORE_FILE = ROOT / "infra" / "zap" / "ignore.json"
DECISIONS = ROOT / "DECISIONS.md"
FAILING = {"3": "High", "2": "Medium"}

# Pages a signed-in developer opens (the SPA shell plus the API reads behind them).
START_PAGES = [
    "/", "/login", "/register", "/dev", "/dev/find", "/dev/bids", "/dev/projects",
    "/dev/profile", "/dev/reputation", "/notifications", "/settings",
]  # fmt: skip
START_API = [
    "/api/v1/health", "/api/v1/me", "/api/v1/me/projects", "/api/v1/me/bids",
    "/api/v1/notifications", "/api/v1/notifications/unread-count",
    "/api/v1/notification-preferences", "/api/v1/projects/search", "/api/v1/skills",
    "/api/v1/public/stats",
]  # fmt: skip
EXCLUDE = [
    r".*/api/v1/__test__/.*",  # the test-only router (resets limits, seeds data)
    r".*/api/v1/auth/logout.*",
    r".*/api/v1/notifications/stream.*",  # SSE: would hold the spider open
    r".*/api/v1/jobs/.*/events.*",
    r".*/api/v1/files/blob/.*",  # signed, short-lived URLs
]


SECRET_COOKIE = re.compile(r"(__Host-ds_[a-z]+=)[^;\s\"']+")


def redact(text: str, cookie: str) -> str:
    """ZAP echoes its plan (the replacer's value included) in its output: drop the session."""
    return SECRET_COOKIE.sub(r"\1<redacted>", text.replace(cookie, "<redacted>"))


def _plan(cookie: str, workspace: str) -> str:
    urls = [f"{TARGET}{p}" for p in [*START_PAGES, f"/w/{workspace}/overview"]]
    api = [f"{TARGET}{p}" for p in [*START_API, f"/api/v1/projects/{workspace}/dashboard"]]
    # `/me` answers 200 only when signed in: if the session didn't take, the plan fails here
    # instead of passing a scan that only ever saw sign-in pages.
    signed_in = {"url": f"{TARGET}/api/v1/me", "method": "GET", "responseCode": 200}
    plan = {
        "env": {
            "contexts": [
                {
                    "name": "devsync",
                    "urls": [f"{TARGET}/"],
                    "includePaths": [f"{re.escape(TARGET)}/.*"],
                    "excludePaths": EXCLUDE,
                }
            ],
            "parameters": {"failOnError": True, "progressToStdout": True},
        },
        "jobs": [
            {
                "type": "replacer",
                "parameters": {"deleteAllRules": True},
                "rules": [
                    {
                        "description": "devsync test session",
                        "url": f"{re.escape(TARGET)}/.*",
                        "matchType": "req_header",
                        "matchString": "Cookie",
                        "matchRegex": False,
                        "replacementString": cookie,
                        "tokenProcessing": False,
                    }
                ],
            },
            {"type": "passiveScan-config", "parameters": {"maxAlertsPerRule": 10}},
            {
                "type": "requestor",
                "requests": [signed_in, *({"url": u, "method": "GET"} for u in [*urls, *api])],
            },
            {
                "type": "spider",
                "parameters": {"context": "devsync", "url": f"{TARGET}/", "maxDuration": 2},
            },
            {
                "type": "spiderClient",
                "parameters": {"context": "devsync", "url": f"{TARGET}/dev", "maxDuration": 2},
            },
            {"type": "passiveScan-wait", "parameters": {"maxDuration": 5}},
            *[
                {
                    "type": "report",
                    "parameters": {
                        "template": template,
                        "reportDir": "/zap/wrk/",
                        "reportFile": name,
                        "reportTitle": "DevSync DAST (ZAP baseline)",
                    },
                }
                for template, name in (
                    ("traditional-json", "report.json"),
                    ("traditional-html", "report.html"),
                )
            ],
        ],
    }
    return json.dumps(plan, indent=2)  # JSON is valid YAML for ZAP's plan loader


def _session() -> str:
    proc = subprocess.run(
        [*COMPOSE, "run", "--rm", "-T", "tests", "python", "scripts/zap_session.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if proc.returncode != 0 or not lines:
        # stderr only: the session never travels through a log.
        sys.exit(f"zap: could not get a session ({proc.returncode}): {proc.stderr.strip()[-400:]}")
    return str(json.loads(lines[-1])["cookie"])


def _ignored() -> dict[str, str]:
    """pluginid -> decision id, each one checked against DECISIONS.md."""
    if not IGNORE_FILE.exists():
        return {}
    entries = json.loads(IGNORE_FILE.read_text(encoding="utf-8"))
    decisions = DECISIONS.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for e in entries:
        decision = str(e["decision"])
        if not re.fullmatch(r"D\d+", decision) or f"**{decision} ·" not in decisions:
            sys.exit(f"zap: ignore entry {e} names no DECISIONS entry")
        out[str(e["pluginid"])] = decision
    return out


def _verdict(report: Path) -> tuple[bool, str]:
    data = json.loads(report.read_text(encoding="utf-8"))
    ignored = _ignored()
    counts = {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
    failing: list[str] = []
    for site in data.get("site", []):
        for alert in site.get("alerts", []):
            level = {"3": "High", "2": "Medium", "1": "Low", "0": "Informational"}.get(
                str(alert.get("riskcode")), "Informational"
            )
            counts[level] += 1
            pid = str(alert.get("pluginid"))
            if str(alert.get("riskcode")) in FAILING and pid not in ignored:
                urls = sorted({i.get("uri", "") for i in alert.get("instances", [])})[:3]
                failing.append(f"{level} {pid} {alert.get('name')}: {', '.join(urls)}")
    summary = (
        f"High {counts['High']}, Medium {counts['Medium']}, Low {counts['Low']}, "
        f"Informational {counts['Informational']}"
    )
    if ignored:
        summary += f"; ignored with decisions: {', '.join(sorted(set(ignored.values())))}"
    if failing:
        return False, summary + "\n" + "\n".join(failing)
    return True, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="report folder")
    args = parser.parse_args()
    if not shutil.which("docker"):
        sys.exit("zap: docker is needed")
    running = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=True
    ).stdout.split()
    if NGINX not in running:
        sys.exit("zap: the test stack isn't running (make test-stack-up)")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or ROOT / "runs" / "zap" / stamp
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o777)  # ZAP runs as its own user in the container
    plan = out / "plan.yaml"
    cookie = _session()
    plan.write_text(_plan(cookie, str(uuid.uuid4())), encoding="utf-8")
    plan.chmod(0o644)
    try:
        proc = subprocess.run(
            [
                "docker", "run", "--rm", "--network", f"container:{NGINX}",
                "-v", f"{out}:/zap/wrk:rw", IMAGE,
                # Its own proxy port: it shares Nginx's network, where 8080 is taken.
                "zap.sh", "-cmd", "-port", "8099", "-autorun", "/zap/wrk/plan.yaml",
            ],
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )  # fmt: skip
    finally:
        plan.unlink(missing_ok=True)  # it carried the session
    output = redact(proc.stdout + proc.stderr, cookie)
    (out / "zap-output.txt").write_text(output, encoding="utf-8")
    for name in ("report.json", "report.html"):  # belt and braces: no session in a report
        path = out / name
        if path.exists():
            path.write_text(redact(path.read_text(encoding="utf-8"), cookie), encoding="utf-8")
    report = out / "report.json"
    if f"Difference in response code values for message GET {TARGET}/api/v1/me" in output:
        sys.exit(f"zap: the scan wasn't signed in (GET /api/v1/me); see {out}/zap-output.txt")
    if proc.returncode == 1:  # 0 = clean, 2 = plan warnings only; 1 = a job failed
        sys.exit(f"zap: the scan plan failed; see {out}/zap-output.txt")
    if not report.exists():
        tail = "\n".join(output.strip().splitlines()[-15:])
        sys.exit(f"zap: no report (exit {proc.returncode}); see {out}/zap-output.txt\n{tail}")
    ok, summary = _verdict(report)
    (out / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    rel = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"zap: {'PASS' if ok else 'FAIL'} — {summary.splitlines()[0]} (report: {rel})")
    if not ok:
        print("\n".join(summary.splitlines()[1:]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
