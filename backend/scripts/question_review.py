"""Question bank review workflow (role assessment spec §13.3).

Self-verification before Demo 1 (rules 1–8) and the team's human review afterwards:

    python scripts/question_review.py blind SKILL OUT.json
        Questions of one skill as a fresh reviewer may see them: id, text, snippet, options —
        never the marked answer, explanation, competency or difficulty.
    python scripts/question_review.py apply SOLVES.json [SOLVES.json …] --checks CHECKS.json
        Merge the independent solves and the execution results into the YAML. A question is
        approved (`APPROVED`, `SELF_VERIFIED`) only if the reviewer picked the marked answer,
        found no other defensible option, the execution check passed (code questions) and it
        isn't marked weak. Others stay DRAFT with the failed record. A difficulty rated two
        levels away from the label is relabelled (new questions only; legacy ones stay DRAFT).
    python scripts/question_review.py report
        docs/question-review/verification-report.md (per skill: verified by execution, by
        independent solve only, failed, remaining risks).
    python scripts/question_review.py review-files
        docs/question-review/{skill}.md with an "Approved by: ______" line per question.
    python scripts/question_review.py approve docs/question-review/{skill}.md
        The team's filled-in file: named questions become HUMAN_APPROVED; questions with a
        correction note are retired in favour of a new DRAFT version (listing the attempts that
        used them is done in the database by the admin screen). Only self-verified questions can
        be human-approved.
    python scripts/question_review.py format
        Rewrite every YAML file in the canonical layout (snippets as literal blocks).

Never sets HUMAN_APPROVED except from a team member's named approval (rule "Never set
review_level: HUMAN_APPROVED … yourself").
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

BACKEND = Path(__file__).resolve().parent.parent
SOURCE = BACKEND / "scripts" / "seed_data" / "question_bank"
DOCS = BACKEND.parent / "docs" / "question-review"
LETTERS = "ABCD"


class _Literal(str):
    __slots__ = ()


def _literal(dumper: yaml.SafeDumper, data: _Literal) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


yaml.SafeDumper.add_representer(_Literal, _literal)


def _prepare(value: Any) -> Any:
    if isinstance(value, str) and "\n" in value:
        return _Literal(value if value.endswith("\n") else value + "\n")
    if isinstance(value, dict):
        return {k: _prepare(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_prepare(v) for v in value]
    return value


HEADER = (
    "# Question bank source for {skill} (role assessment spec §13). Edit here; the build\n"
    "# writes alembic/seed/question_bank_v2.json. Legacy questions keep their text and options\n"
    "# exactly as stored by migration 0004 (they are matched by text). See README.md.\n"
)


def load() -> dict[Path, dict[str, Any]]:
    return {p: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(SOURCE.glob("*.yaml"))}


def save(path: Path, doc: dict[str, Any]) -> None:
    text = yaml.safe_dump(_prepare(doc), sort_keys=False, allow_unicode=True, width=100)
    path.write_text(HEADER.format(skill=doc["skill"]) + text, encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# -------------------------------------------------------------------------------- blind


def blind(skill: str, out: Path) -> int:
    for _, doc in load().items():
        if doc["skill"].lower() == skill.lower():
            questions = [
                {"id": q["id"], "text": q["text"], "code_snippet": q.get("code_snippet"),
                 "options": {LETTERS[i]: o for i, o in enumerate(q["options"])}}
                for q in doc["questions"]
                if q.get("status") != "RETIRED"
            ]  # fmt: skip
            out.write_text(json.dumps({"skill": doc["skill"], "questions": questions}, indent=1,
                                      ensure_ascii=False), encoding="utf-8")  # fmt: skip
            print(f"{len(questions)} questions → {out}")
            return 0
    print(f"unknown skill {skill!r}")
    return 1


# -------------------------------------------------------------------------------- apply


def apply(solve_files: list[Path], checks_file: Path | None) -> int:
    solves: dict[str, dict[str, Any]] = {}
    for f in solve_files:
        solves.update(json.loads(f.read_text(encoding="utf-8")))
    checks: dict[str, str | None] = (
        json.loads(checks_file.read_text(encoding="utf-8")) if checks_file else {}
    )
    stamp = _now()
    tally: Counter[str] = Counter()
    for path, doc in load().items():
        changed = False
        for q in doc["questions"]:
            s = solves.get(q["id"])
            if s is None or q.get("status") in ("APPROVED", "RETIRED"):
                continue
            changed = True
            picked = LETTERS.index(s["answer"]) if isinstance(s["answer"], str) else s["answer"]
            agreement = picked == q["correct_index"] and not s.get("other_defensible", False)
            execution = q.get("check") == "execution"
            passed = (checks.get(q["id"], "missing") is None) if execution else True
            rated = int(s.get("difficulty", q["difficulty"]))
            legacy = "-legacy-" in q["id"]
            relabel = abs(rated - q["difficulty"]) >= 2
            q["verification"] = {
                "method": "execution" if execution else "independent_solve",
                "checks_passed": passed,
                "solver_agreement": agreement,
                "verified_at": stamp,
                "reviewer_answer": LETTERS[picked],
                "reviewer_difficulty": rated,
                **({"reviewer_note": s["note"]} if s.get("note") else {}),
            }
            if relabel and not legacy:
                q["difficulty"] = rated  # §13.3 rule 7: relabel, the allocation is re-checked
            ok = agreement and passed and not q.get("weak") and not (relabel and legacy)
            if ok:
                q.update(status="APPROVED", review_level="SELF_VERIFIED", reviewed_at=stamp)
                tally["approved"] += 1
            else:
                q.update(status="DRAFT", review_level="NONE", reviewed_at=None)
                tally["failed agreement" if not agreement else "failed check" if not passed
                      else "weak or legacy relabel"] += 1  # fmt: skip
        if changed:
            save(path, doc)
    print(dict(tally))
    return 0


# ------------------------------------------------------------------------------- report


def report() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Question bank verification report",
        "",
        f"Generated {_now()} by `scripts/question_review.py report` (role assessment spec §13.3).",
        "",
        "Every approved question passed (1) an execution check when its answer depends on what "
        "code does, and (2) an independent second solve by a fresh reviewer that saw only the "
        "question and options. Approved questions are `SELF_VERIFIED`: the team's human review "
        "follows after Demo 1 and upgrades them to `HUMAN_APPROVED`.",
        "",
        "| Skill | Questions | Approved | By execution | By independent solve only "
        "| Failed solve | Failed check | Weak (practice only) | Not yet verified |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    risks: list[str] = []
    for _, doc in load().items():
        qs = doc["questions"]
        c: Counter[str] = Counter()
        for q in qs:
            v = q.get("verification") or {}
            if q.get("status") == "APPROVED":
                c["approved"] += 1
                c["exec" if v.get("method") == "execution" else "solve"] += 1
            elif q.get("weak"):
                c["weak"] += 1
            elif not v:
                c["unverified"] += 1
            elif not v.get("solver_agreement"):
                c["failed_solve"] += 1
            elif not v.get("checks_passed"):
                c["failed_check"] += 1
        lines.append(
            f"| {doc['skill']} | {len(qs)} | {c['approved']} | {c['exec']} | {c['solve']} | "
            f"{c['failed_solve']} | {c['failed_check']} | {c['weak']} | {c['unverified']} |"
        )
        approved = Counter(
            (q["competency"], q["difficulty"]) for q in qs if q.get("status") == "APPROVED"
        )
        for comp in doc["competencies"]:
            per = [approved.get((comp["code"], d), 0) for d in (1, 2, 3)]
            if min(per) < 2:
                risks.append(
                    f"- {doc['skill']} · {comp['name']}: approved easy/medium/hard {per} — "
                    "blueprints use this competency only where the pool can supply it"
                )
    lines += [
        "",
        "## Remaining risks",
        "",
        "- No human has reviewed these questions yet; the independent solve catches ambiguity and "
        "wrong keys but not every outdated fact. The team review follows after Demo 1.",
        "- Questions marked `check: manual` (no executable answer) rest on the independent solve "
        "alone.",
        *risks,
        "",
    ]
    out = DOCS / "verification-report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    return 0


# ------------------------------------------------------------------------- review files


def review_files() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    for path, doc in load().items():
        names = {c["code"]: c["name"] for c in doc["competencies"]}
        out = [
            f"# {doc['skill']} questions — team review",
            "",
            "For each question: check the marked answer and the explanation. If it is right, write "
            "your name after **Approved by**. If something is wrong, write the fix after "
            "**Correction** instead (the question is retired and replaced). Then run "
            f"`make question-approve FILE=docs/question-review/{path.stem}.md`.",
            "",
        ]
        for q in doc["questions"]:
            if q.get("status") != "APPROVED":
                continue
            v = q.get("verification") or {}
            out += [
                f"## {q['id']}",
                "",
                f"{names.get(q['competency'], q['competency'])} · difficulty {q['difficulty']} · "
                f"{'execution check' if v.get('method') == 'execution' else 'independent solve'}"
                f" {'passed' if v.get('checks_passed') else 'FAILED'}",
                "",
                q["text"],
                "",
            ]
            if q.get("code_snippet"):
                out += ["```", q["code_snippet"].rstrip("\n"), "```", ""]
            for i, o in enumerate(q["options"]):
                mark = " ✔" if i == q["correct_index"] else ""
                out.append(f"- {LETTERS[i]}. {o}{mark}")
            out += ["", f"Explanation: {q.get('explanation') or ''}", "", "Approved by: ______",
                    "", "Correction: ______", ""]  # fmt: skip
        target = DOCS / f"{path.stem}.md"
        target.write_text("\n".join(out), encoding="utf-8")
        print(f"wrote {target}")
    return 0


# ------------------------------------------------------------------------ team approval

_BLANK = re.compile(r"^_*$")


def approve(review_file: Path) -> int:
    text = review_file.read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    decisions: dict[str, tuple[str | None, str | None]] = {}
    for section in sections:
        qid = section.split("\n", 1)[0].strip()
        name = re.search(r"^Approved by:\s*(.*)$", section, re.MULTILINE)
        fix = re.search(r"^Correction:\s*(.*)$", section, re.MULTILINE)
        who = name.group(1).strip() if name else ""
        note = fix.group(1).strip() if fix else ""
        decisions[qid] = (None if _BLANK.match(who) else who, None if _BLANK.match(note) else note)
    stamp = _now()
    refused: list[str] = []
    for path, doc in load().items():
        changed = False
        new_rows: list[dict[str, Any]] = []
        for q in doc["questions"]:
            decision = decisions.get(q["id"])
            if decision is None:
                continue
            who, note = decision
            if note:
                changed = True
                q["status"] = "RETIRED"
                copy = {k: v for k, v in q.items() if k not in ("verification",)}
                copy.update(
                    id=f"{q['id']}-v{int(q.get('version', 1)) + 1}", status="DRAFT",
                    review_level="NONE", reviewed_by_name=None, reviewed_at=None,
                    verification=None, version=int(q.get("version", 1)) + 1,
                    source="HUMAN", active=False, correction=note,
                )  # fmt: skip
                new_rows.append(copy)
            elif who:
                if q.get("review_level") != "SELF_VERIFIED" or q.get("status") != "APPROVED":
                    refused.append(q["id"])  # §16 case 48: only verified questions
                    continue
                changed = True
                q.update(review_level="HUMAN_APPROVED", reviewed_by_name=who, reviewed_at=stamp)
        if changed:
            doc["questions"].extend(new_rows)
            save(path, doc)
    for qid in refused:
        print(f"refused {qid}: only self-verified, approved questions can be human-approved")
    print(f"processed {len(decisions)} questions; run `make question-bank` to rebuild the seed")
    return 1 if refused else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("blind")
    b.add_argument("skill")
    b.add_argument("out", type=Path)
    a = sub.add_parser("apply")
    a.add_argument("solves", type=Path, nargs="+")
    a.add_argument("--checks", type=Path)
    sub.add_parser("report")
    sub.add_parser("review-files")
    ap = sub.add_parser("approve")
    ap.add_argument("file", type=Path)
    sub.add_parser("format")
    args = parser.parse_args(argv)
    if args.cmd == "blind":
        return blind(args.skill, args.out)
    if args.cmd == "apply":
        return apply(args.solves, args.checks)
    if args.cmd == "report":
        return report()
    if args.cmd == "review-files":
        return review_files()
    if args.cmd == "approve":
        return approve(args.file)
    for path, doc in load().items():
        save(path, doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
