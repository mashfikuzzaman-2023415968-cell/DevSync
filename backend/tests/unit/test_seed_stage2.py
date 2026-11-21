"""Stage-2 demo seed data (spec §18.4, DECISIONS D93): deterministic persona histories with
readable, unique project names, and a golden fixture that keeps every ordering-system bidder
eligible and the §18.1 stories true."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from scripts import seed_demo

pytestmark = pytest.mark.unit

BIDDERS = ["arif", "nusrat", "tanvir", "farhan", "sadia", "rafi", "zahid", "imran", "shakib"]


def test_stage2_market_is_deterministic() -> None:
    a, b = seed_demo.stage2_market(), seed_demo.stage2_market()
    assert a == b
    assert {d.key for d in a.developers} == {*BIDDERS, "rafsan"}


def test_every_persona_is_a_seeded_developer() -> None:
    keys = {d.key for d in seed_demo.stage2_market().developers}
    assert keys <= set(seed_demo.EXPERIENCED) | set(seed_demo.NEWCOMERS)


def test_project_labels_are_unique_and_readable() -> None:
    used: set[str] = set()
    labels = [seed_demo._label("FRONTEND", used, n) for n in range(10)]
    assert len(set(labels)) == 10
    assert labels[0] == "Clinic booking site"
    assert labels[4] == "Clinic booking site (2)"
    assert all(0 < len(label) <= 120 for label in labels)


def test_golden_fixture_keeps_bidders_eligible_and_stories_true() -> None:
    golden = json.loads(seed_demo.GOLDEN_FILE.read_text(encoding="utf-8"))
    for key in BIDDERS:
        assert Decimal(golden[key]["p"]) >= Decimal("0.45"), key
        assert Decimal(golden[key]["c"]) >= Decimal("0.40"), key
    assert golden["imran"]["mu"] == "0.000"
    assert (golden["arif"]["completed_projects"], golden["arif"]["distinct_clients"]) == (8, 5)
    assert golden["zahid"]["completed_projects"] == 3  # not a newcomer (D93)
    assert golden["rafsan"]["completed_projects"] == 1
    assert min(golden, key=lambda k: golden[k]["t"]) == "shakib"
