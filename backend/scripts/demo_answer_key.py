"""Demo answer key — an operator tool for the presenter's second screen (role assessment §14.1).

    DEVSYNC_DEMO_TOOLS=1 make demo-answer-key USER=rafsan

Waits for that user's next role assessment attempt to start on the demo stack (polling every 2 s,
up to 30 minutes), then prints each question's number, competency and correct option letter and
writes `runs/demos/answer-key.json` (gitignored, owner-only). The presenter starts this before
pressing Start and only reads it, so no click ever leaves the assessment page.

It is not part of the app: no HTTP route, never imported by the app, stdlib only. It runs on the
demo laptop's host and reads the demo database through the Postgres container as the migrator
role (operator credentials the web app never has). It refuses to run unless the shell sets
`DEVSYNC_DEMO_TOOLS=1`, unless the database is a demo one (its name ends in `_demo`), and inside
any container.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "demos" / "answer-key.json"
COMPOSE = [
    "docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml",
    "-f", "docker-compose.demo.yml",
]  # fmt: skip
DEMO_DB = "devsync_demo"
POLL_SECONDS = 2.0
TIMEOUT_SECONDS = 30 * 60
USER_RE = re.compile(r"^[a-z][a-z0-9._-]{1,40}$")
LETTERS = "ABCD"


class Refused(SystemExit):
    pass


def check_allowed(env: dict[str, str], database: str | None = None) -> None:
    """Refuse outside an operator's demo shell; `database` once known."""
    if env.get("DEVSYNC_DEMO_TOOLS") != "1":
        raise Refused("demo-answer-key: set DEVSYNC_DEMO_TOOLS=1 in this shell to use it")
    if Path("/.dockerenv").exists() or env.get("DEVSYNC_ENV"):
        raise Refused("demo-answer-key: run it on the demo laptop's host, not in a container")
    if database is not None and not database.endswith("_demo"):
        raise Refused(f"demo-answer-key: {database!r} is not a demo database (needs *_demo)")


def psql(sql: str, variables: dict[str, str]) -> list[list[str]]:
    """Run SQL in the demo Postgres container as the migrator; tab-separated rows."""
    cmd = [
        # PGPASSWORD is passed by name: Docker reads it from this process's environment, so the
        # password never appears in a command line.
        *COMPOSE, "exec", "-T", "-e", "PGPASSWORD", "postgres",
        "psql", "-U", "devsync_migrator", "-d", DEMO_DB, "-h", "localhost",
        "-v", "ON_ERROR_STOP=1", "-At", "-F", "\t", "-f", "-",
    ]  # fmt: skip
    for name, value in variables.items():
        cmd += ["-v", f"{name}={value}"]
    env = {
        **os.environ,
        "DEVSYNC_DB_NAME": DEMO_DB,
        "PGPASSWORD": os.environ.get("DEVSYNC_MIGRATOR_PASSWORD", ""),
    }
    result = subprocess.run(
        cmd, input=sql, capture_output=True, text=True, cwd=ROOT, env=env, timeout=60, check=False
    )
    if result.returncode != 0:
        raise SystemExit(f"demo-answer-key: database query failed: {result.stderr.strip()[-300:]}")
    return [line.split("\t") for line in result.stdout.splitlines() if line]


def _password_from_env_file() -> None:
    """The migrator password from the repository's .env (operator credentials)."""
    if os.environ.get("DEVSYNC_MIGRATOR_PASSWORD"):
        return
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEVSYNC_MIGRATOR_PASSWORD="):
                os.environ["DEVSYNC_MIGRATOR_PASSWORD"] = line.split("=", 1)[1].strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demo answer key (operator tool)")
    parser.add_argument("--user", required=True, help="demo account slug, e.g. rafsan")
    parser.add_argument("--watch", action="store_true", help="wait for the next attempt")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    check_allowed(dict(os.environ))
    if not USER_RE.match(args.user):
        raise SystemExit("demo-answer-key: USER must be a demo account slug such as rafsan")
    _password_from_env_file()
    ((database,),) = psql("SELECT current_database();", {})
    check_allowed(dict(os.environ), database)
    rows = psql(
        "SELECT id, now() FROM users WHERE email = :'email';",
        {"email": f"{args.user}@devsync.local"},
    )
    if not rows:
        raise SystemExit(f"demo-answer-key: no demo account {args.user}@devsync.local")
    user_id, since = rows[0]
    find = (
        "SELECT id FROM test_attempts WHERE user_id = :'uid' AND kind = 'ROLE' "
        "AND started_at >= :'since' ORDER BY started_at LIMIT 1;"
    )
    if not args.watch:
        find = find.replace("AND started_at >= :'since' ", "").replace(
            "ORDER BY started_at", "ORDER BY started_at DESC"
        )
    deadline = time.monotonic() + args.timeout
    print(f"demo-answer-key: waiting for {args.user}'s next role assessment…", flush=True)
    attempt: list[list[str]] = []
    while not attempt:
        attempt = psql(find, {"uid": user_id, "since": since})
        if attempt or not args.watch:
            break
        if time.monotonic() > deadline:
            raise SystemExit("demo-answer-key: no attempt started within the time limit")
        time.sleep(POLL_SECONDS)
    if not attempt:
        raise SystemExit(f"demo-answer-key: {args.user} has no role assessment attempt")
    key = psql(
        "SELECT u.ord, coalesce(c.name, ''), q.correct_index "
        "FROM test_attempts a "
        "CROSS JOIN LATERAL unnest(a.question_ids) WITH ORDINALITY u(qid, ord) "
        "JOIN question_bank q ON q.id = u.qid LEFT JOIN competencies c ON c.id = q.competency_id "
        "WHERE a.id = :'aid' ORDER BY u.ord;",
        {"aid": attempt[0][0]},
    )
    answers = [
        {"number": int(n), "competency": comp, "answer": LETTERS[int(idx)]} for n, comp, idx in key
    ]
    for a in answers:
        print(f"  Q{a['number']:>2}  {a['answer']}   {a['competency']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"user": args.user, "answers": answers}, indent=1), encoding="utf-8")
    OUT.chmod(0o600)
    print(f"demo-answer-key: wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
