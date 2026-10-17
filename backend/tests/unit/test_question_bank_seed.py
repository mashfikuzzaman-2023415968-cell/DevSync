"""The frozen skill and question seed (spec §17 Phase 3: 8 skills, ≥ 15 questions per skill)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SEED = Path(__file__).resolve().parents[2] / "alembic" / "seed" / "skills_and_questions_v1.json"
SPEC_SKILLS = {"React", "Node.js", "FastAPI", "PostgreSQL", "UI/UX", "Testing", "Flutter", "DevOps"}
DOMAINS = {"FRONTEND", "BACKEND", "DATABASE", "MOBILE", "DESIGN", "TESTING", "DEVOPS", "DATA"}


def load() -> list[dict[str, object]]:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    skills: list[dict[str, object]] = data["skills"]
    return skills


def test_the_eight_spec_skills_with_valid_domains() -> None:
    skills = load()
    assert {s["name"] for s in skills} == SPEC_SKILLS
    assert all(s["domain"] in DOMAINS for s in skills)


def test_at_least_fifteen_well_formed_questions_per_skill() -> None:
    for skill in load():
        questions = skill["questions"]
        assert isinstance(questions, list)
        assert len(questions) >= 15, skill["name"]
        texts = [q["text"] for q in questions]
        assert len(set(texts)) == len(texts), f"duplicate question in {skill['name']}"
        for q in questions:
            assert 5 <= len(q["text"]) <= 1000
            assert len(q["options"]) == 4
            assert len(set(q["options"])) == 4, q["text"]
            assert q["answer"] in (0, 1, 2, 3)
            assert q["difficulty"] in (1, 2, 3)


def test_answer_positions_are_balanced() -> None:
    """No position wins by default: guessing one letter shouldn't beat 25 % by much."""
    positions = Counter(q["answer"] for s in load() for q in s["questions"])  # type: ignore[attr-defined]
    total = sum(positions.values())
    assert all(abs(n / total - 0.25) < 0.05 for n in positions.values()), positions
