"""Build and validate the question bank (role assessment spec §13; build spec §7.2).

Source: one YAML file per skill in `scripts/seed_data/question_bank/` holding the skill's
competency catalogue and its questions. The build validates every rule of spec §13.2–13.3 and
writes the frozen seed `alembic/seed/question_bank_v2.json` that migration 0011 loads:

    python scripts/build_question_bank.py                # validate and write the seed
    python scripts/build_question_bank.py --check        # validate; fail if the seed is stale

The 128 questions of the original bank (`*-legacy-NN`) keep their text and options exactly as
migration 0004 stored them from `skills_and_questions_v1.json` (frozen; written by an earlier
version of this script), because 0011 finds them by text to tag them. Practice tests use
`active` questions only; role assessments use `APPROVED` ones (Decision 15: new questions are
never active, so practice tests don't reveal the role-assessment pool).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

BACKEND = Path(__file__).resolve().parent.parent
SOURCE = BACKEND / "scripts" / "seed_data" / "question_bank"
CHECKS = BACKEND / "scripts" / "question_checks"
LEGACY_SEED = BACKEND / "alembic" / "seed" / "skills_and_questions_v1.json"
SEED = BACKEND / "alembic" / "seed" / "question_bank_v2.json"

DEMO_SKILLS = ("React", "FastAPI", "PostgreSQL", "Testing")
MIN_PER_DIFFICULTY_DEMO = 2  # §13.2: ≥ 6 approved per competency (2 easy, 2 medium, 2 hard)
MIN_PER_CORE_OTHER = 4  # §13.2: other skills ≥ 4 per core competency (warning: fallback exists)
NEAR_DUPLICATE = 0.9  # difflib ratio on normalised texts
POSITION_TOLERANCE = 0.07  # each answer position within 25 % ± 7 points per skill
MAX_SNIPPET_LINES = 25

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
BANNED_OPTIONS = re.compile(r"\b(all|none|both|neither) of (the )?(above|these)\b", re.IGNORECASE)
STATUSES = {"DRAFT", "APPROVED", "RETIRED"}
SOURCES = {"HUMAN", "CLAUDE_GENERATED"}
REVIEW_LEVELS = {"NONE", "SELF_VERIFIED", "HUMAN_APPROVED"}
CHECK_KINDS = {"execution", "manual"}
VERIFICATION_METHODS = {"execution", "independent_solve"}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def check_file(skill_slug: str, question_id: str) -> Path:
    return CHECKS / skill_slug / f"{question_id.replace('-', '_')}.py"


def load_sources() -> list[tuple[str, dict[str, Any]]]:
    return [
        (path.stem, yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(SOURCE.glob("*.yaml"))
    ]


def _competencies(doc: dict[str, Any], where: str, report: Report) -> dict[str, dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for c in doc.get("competencies") or []:
        at = f"{where} competency {c.get('code')!r}"
        code = c.get("code")
        if not isinstance(code, str) or not CODE_RE.match(code):
            report.error(at, "code must match ^[a-z][a-z0-9_]{2,40}$")
            continue
        if code in seen:
            report.error(at, "duplicate code")
        if not 3 <= len(c.get("name") or "") <= 60:
            report.error(at, "name must be 3–60 characters")
        if len(c.get("description") or "") > 300:
            report.error(at, "description longer than 300 characters")
        if not isinstance(c.get("is_core"), bool):
            report.error(at, "is_core must be true or false")
        keywords = c.get("keywords") or []
        if not 1 <= len(keywords) <= 40:
            report.error(at, "1–40 keywords")
        for k in keywords:
            if not isinstance(k, str) or not 2 <= len(k) <= 40 or k != k.lower():
                report.error(at, f"keyword {k!r} must be lowercase, 2–40 characters")
        if not isinstance(c.get("position"), int):
            report.error(at, "position must be an integer")
        seen[code] = c
    if not seen:
        report.error(where, "no competencies")
    return seen


def _question(  # noqa: C901 - one rule per branch, kept flat on purpose
    q: dict[str, Any],
    skill_slug: str,
    competencies: dict[str, dict[str, Any]],
    report: Report,
) -> None:
    qid = q.get("id")
    at = f"{skill_slug} {qid}"
    if not isinstance(qid, str) or not ID_RE.match(qid):
        report.error(at, "id must be a lowercase slug")
    status, source, level = q.get("status"), q.get("source"), q.get("review_level")
    if status not in STATUSES:
        report.error(at, f"status must be one of {sorted(STATUSES)}")
    if source not in SOURCES:
        report.error(at, f"source must be one of {sorted(SOURCES)}")
    if level not in REVIEW_LEVELS:
        report.error(at, f"review_level must be one of {sorted(REVIEW_LEVELS)}")
    competency = q.get("competency")
    if competency is not None and competency not in competencies:
        report.error(at, f"unknown competency {competency!r}")
    if q.get("difficulty") not in (1, 2, 3):
        report.error(at, "difficulty must be 1, 2 or 3")
    text = q.get("text")
    if not isinstance(text, str) or not 5 <= len(text) <= 1000:
        report.error(at, "text must be 5–1000 characters")
    snippet = q.get("code_snippet")
    if snippet is not None:
        if not isinstance(snippet, str) or len(snippet) > 1500:
            report.error(at, "code_snippet must be text of at most 1,500 characters")
        elif len(snippet.rstrip("\n").split("\n")) > MAX_SNIPPET_LINES:
            report.error(at, f"code_snippet longer than {MAX_SNIPPET_LINES} lines")
        elif "<" in snippet and re.search(r"<\s*script", snippet, re.IGNORECASE):
            report.error(at, "code_snippet must not contain a script tag")
    options = q.get("options")
    if not isinstance(options, list) or len(options) != 4:
        report.error(at, "exactly 4 options")
    else:
        if any(not isinstance(o, str) or not o.strip() for o in options):
            report.error(at, "options must be non-empty text")
        elif len({normalise(o) for o in options}) != 4:
            report.error(at, "options must be distinct")
        for o in options:
            if isinstance(o, str) and BANNED_OPTIONS.search(o):
                report.error(at, f"banned option wording: {o!r}")
    if q.get("correct_index") not in (0, 1, 2, 3):
        report.error(at, "correct_index must be 0–3")
    explanation = q.get("explanation")
    if explanation is not None and (not isinstance(explanation, str) or len(explanation) > 600):
        report.error(at, "explanation must be text of at most 600 characters")
    if not isinstance(q.get("active"), bool):
        report.error(at, "active must be true or false")
    legacy = "-legacy-" in (qid or "")
    if source == "CLAUDE_GENERATED" and q.get("active"):
        report.error(at, "new questions are never active (Decision 15)")
    if legacy and (source != "HUMAN" or not q.get("active")):
        report.error(at, "legacy questions stay HUMAN and active (practice pool)")
    check = q.get("check")
    if check is not None and check not in CHECK_KINDS:
        report.error(at, f"check must be one of {sorted(CHECK_KINDS)}")
    if check == "execution" and not check_file(skill_slug, qid or "").exists():
        report.error(at, f"execution check missing: {check_file(skill_slug, qid or '')}")
    if snippet is not None and check is None:
        report.error(at, "a code question needs `check: execution` or `check: manual`")
    if level == "HUMAN_APPROVED" and not q.get("reviewed_by_name"):
        report.error(at, "HUMAN_APPROVED needs reviewed_by_name")
    if level != "HUMAN_APPROVED" and q.get("reviewed_by_name"):
        report.error(at, "reviewed_by_name is only for HUMAN_APPROVED")
    reviewed_at = q.get("reviewed_at")
    if reviewed_at is not None:
        try:
            datetime.fromisoformat(str(reviewed_at))
        except ValueError:
            report.error(at, "reviewed_at must be an ISO 8601 timestamp")
    if level in ("SELF_VERIFIED", "HUMAN_APPROVED") and reviewed_at is None:
        report.error(at, f"{level} needs reviewed_at")
    verification = q.get("verification")
    if verification is not None:
        _verification(verification, check, at, report)
    weak = q.get("weak")
    if weak is not None and (not isinstance(weak, str) or not weak.strip()):
        report.error(at, "weak must be a reason")
    if status == "APPROVED":
        if weak:
            report.error(at, "a question marked weak stays out of role assessments")
        if competency is None:
            report.error(at, "APPROVED needs a competency")
        if level not in ("SELF_VERIFIED", "HUMAN_APPROVED"):
            report.error(at, "APPROVED needs review_level SELF_VERIFIED or HUMAN_APPROVED")
        if not explanation:
            report.error(at, "APPROVED needs an explanation")
        if level == "SELF_VERIFIED" and verification is None:
            report.error(at, "SELF_VERIFIED needs a verification record")
        if check == "execution" and not (verification or {}).get("checks_passed"):
            report.error(at, "APPROVED code question needs a passing execution check")


def _verification(v: Any, check: str | None, at: str, report: Report) -> None:
    if not isinstance(v, dict):
        report.error(at, "verification must be a mapping")
        return
    if v.get("method") not in VERIFICATION_METHODS:
        report.error(at, f"verification.method must be one of {sorted(VERIFICATION_METHODS)}")
    if check == "execution" and v.get("method") != "execution":
        report.error(at, "an execution-checked question records method: execution")
    if not isinstance(v.get("checks_passed"), bool):
        report.error(at, "verification.checks_passed must be true or false")
    if not isinstance(v.get("solver_agreement"), bool):
        report.error(at, "verification.solver_agreement must be true or false")
    try:
        datetime.fromisoformat(str(v.get("verified_at")))
    except ValueError:
        report.error(at, "verification.verified_at must be an ISO 8601 timestamp")


def _legacy_matches(name: str, questions: list[dict[str, Any]], report: Report) -> None:
    """Legacy questions must be exactly the 0004 rows (same text, options, answer, difficulty)."""
    v1 = json.loads(LEGACY_SEED.read_text(encoding="utf-8"))
    original = next((s["questions"] for s in v1["skills"] if s["name"] == name), None)
    if original is None:
        report.error(name, "skill is not in the original seed")
        return
    by_text = {q["text"]: q for q in original}
    legacy = [q for q in questions if "-legacy-" in q.get("id", "")]
    if len(legacy) != len(original):
        report.error(name, f"{len(legacy)} legacy questions, the original bank has {len(original)}")
    for q in legacy:
        o = by_text.get(q.get("text"))
        if o is None:
            report.error(f"{name} {q.get('id')}", "legacy text differs from migration 0004")
        elif (o["options"], o["answer"], o["difficulty"]) != (
            q.get("options"), q.get("correct_index"), q.get("difficulty"),
        ):  # fmt: skip
            report.error(f"{name} {q.get('id')}", "legacy options/answer/difficulty changed")


def _skill_rules(
    name: str, questions: list[dict[str, Any]], comps: dict[str, Any], report: Report
) -> None:
    approved = [q for q in questions if q.get("status") == "APPROVED"]
    # Near-duplicate texts (spec §13.3 rule 3), across every question of the skill.
    texts = [(q.get("id"), normalise(q.get("text") or "")) for q in questions]
    for i, (a_id, a) in enumerate(texts):
        for b_id, b in texts[i + 1 :]:
            if a == b:
                report.error(name, f"duplicate question texts: {a_id} / {b_id}")
            elif difflib.SequenceMatcher(None, a, b).ratio() >= NEAR_DUPLICATE:
                report.error(name, f"near-duplicate question texts: {a_id} / {b_id}")
    # Correct answers spread across A–D (approved questions of the skill).
    if len(approved) >= 20:
        positions = Counter(q["correct_index"] for q in approved)
        for p in range(4):
            share = positions.get(p, 0) / len(approved)
            if abs(share - 0.25) > POSITION_TOLERANCE:
                report.error(name, f"answer position {'ABCD'[p]} is {share:.0%} of approved")
    counts = Counter((q.get("competency"), q.get("difficulty")) for q in approved)
    for code, c in comps.items():
        per = [counts.get((code, d), 0) for d in (1, 2, 3)]
        if name in DEMO_SKILLS and min(per) < MIN_PER_DIFFICULTY_DEMO:
            report.error(
                name, f"{code}: approved easy/medium/hard {per}, needs ≥ {MIN_PER_DIFFICULTY_DEMO} each"
            )
        elif name not in DEMO_SKILLS and c.get("is_core") and sum(per) < MIN_PER_CORE_OTHER:
            report.warn(name, f"{code}: {sum(per)} approved, target {MIN_PER_CORE_OTHER} (fallback)")


def validate(sources: list[tuple[str, dict[str, Any]]]) -> Report:
    report = Report()
    ids: set[str] = set()
    names = set()
    for slug, doc in sources:
        name = doc.get("skill")
        names.add(name)
        comps = _competencies(doc, slug, report)
        questions = doc.get("questions") or []
        for q in questions:
            if q.get("id") in ids:
                report.error(f"{slug} {q.get('id')}", "duplicate id")
            ids.add(q.get("id"))
            _question(q, slug, comps, report)
        _legacy_matches(name, questions, report)
        _skill_rules(name, questions, comps, report)
    codes = Counter(c.get("code") for _, doc in sources for c in doc.get("competencies") or [])
    for code, n in codes.items():
        if n > 1:  # a blueprint mixes skills' competencies and keys them by code
            report.error("bank", f"competency code {code!r} is used by {n} skills")
    v1 = json.loads(LEGACY_SEED.read_text(encoding="utf-8"))
    if names != {s["name"] for s in v1["skills"]}:
        report.error("bank", "skills differ from the original eight")
    for path in CHECKS.glob("*/*.py"):
        if path.name.startswith("_"):
            continue
        qid = path.stem.replace("_", "-")
        if qid not in ids:
            report.error(str(path.relative_to(BACKEND)), "check file for an unknown question")
    return report


def seed_document(sources: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    keys = (
        "id", "competency", "difficulty", "text", "code_snippet", "options", "correct_index",
        "explanation", "status", "source", "active", "review_level", "reviewed_by_name",
        "reviewed_at", "verification",
    )  # fmt: skip
    skills = []
    for _, doc in sources:
        skills.append(
            {
                "name": doc["skill"],
                "competencies": [
                    {k: c[k] for k in ("code", "name", "description", "is_core", "keywords", "position")}
                    for c in doc["competencies"]
                ],
                "questions": [
                    {**{k: _plain(q.get(k)) for k in keys}, "legacy": "-legacy-" in q["id"]}
                    for q in doc["questions"]
                ],
            }
        )
    return {"version": 2, "skills": skills}


def _plain(value: Any) -> Any:
    """YAML may parse timestamps as datetimes; the seed stores ISO strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=1, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="validate; fail if the seed is stale")
    args = parser.parse_args(argv)
    sources = load_sources()
    report = validate(sources)
    for w in report.warnings:
        print(f"warning: {w}")
    for e in report.errors:
        print(f"error: {e}")
    if report.errors:
        print(f"question bank: {len(report.errors)} error(s)")
        return 1
    text = render(seed_document(sources))
    if args.check:
        if not SEED.exists() or SEED.read_text(encoding="utf-8") != text:
            print(f"question bank: {SEED.name} is stale; run scripts/build_question_bank.py")
            return 1
    else:
        SEED.write_text(text, encoding="utf-8")
    total = sum(len(d["questions"]) for _, d in sources)
    approved = sum(q.get("status") == "APPROVED" for _, d in sources for q in d["questions"])
    print(f"question bank: {total} questions, {approved} approved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
