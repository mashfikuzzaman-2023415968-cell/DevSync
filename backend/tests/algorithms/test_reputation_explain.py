"""Plain-language reputation explanations: right numbers, right fact, cap note, no paper terms."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.algorithms import reputation as r
from app.algorithms.reputation_explain import explain_change, points

D = Decimal
pytestmark = pytest.mark.unit
CAP = D("0.15")

A = r.ProjectRecord("A", "FRONTEND", "c1", 20, 30, D("0.8"), D("0.7"), (D("0.75"), D(1)))
B = r.ProjectRecord("B", "BACKEND", "c1", 33, 30, D("0.6"), D("0.9"), (D("0.5"),), (D(1),))
EV = r.Evidence(3, frozenset({"FRONTEND"}))


def _sentences() -> dict[tuple[str, str], str]:
    res = r.compute_snapshot([A, B], evidence=EV)
    out = {}
    for e in res.trace:
        exp = explain_change(e, CAP)
        assert exp is not None
        out[(e.history_id, e.parameter)] = exp.sentence
    return out


def test_points_rounds_half_up() -> None:
    assert points(D("0.555")) == 56
    assert points(D("0.554")) == 55
    assert points(D(1)) == 100


def test_punctuality_sentences() -> None:
    """A: 20 of 30 days → T = 0.333 (50 → 33). B: 33 days, deadline 30 → 3 days late."""
    s = _sentences()
    assert s[("A", "t")] == "Punctuality 50 → 33: finished in 20 of 30 days."
    assert s[("B", "t")] == "Punctuality 33 → 17: finished 3 days after the 30-day deadline."


def test_capped_change_names_the_limit_and_raw_value() -> None:
    """X: 0.55 → raw 0.725, capped at 0.70."""
    assert _sentences()[("A", "x")] == (
        "Communication 55 → 70: communication on this project was rated 80. "
        "The change was limited to 15 points per project (it would have been 73)."
    )


def test_quality_mentions_client_and_outside_review() -> None:
    s = _sentences()
    assert "the client rated this project 93" in s[("A", "beta")]
    assert "a verified outside review gave 100" in s[("B", "beta")]


def test_domain_and_client_sentences() -> None:
    s = _sentences()
    assert s[("A", "omega")] == "Expertise stays 20: your first front-end project."
    assert s[("B", "omega")] == "Expertise 20 → 100: your first back-end project."
    assert s[("A", "mu")] == (
        "Client diversity stays 50: work for a new client (1 client over 1 project)."
    )
    assert s[("B", "mu")] == (
        "Client diversity 50 → 0: another project for a returning client "
        "(1 client over 2 projects)."
    )


def test_derived_and_no_review_sentences() -> None:
    s = _sentences()
    assert s[("A", "c")].endswith("follows from expertise and communication.")
    assert s[("A", "p")].endswith("follows from quality, client diversity and punctuality.")
    quiet = r.compute_snapshot([r.ProjectRecord("Q", "DATA", "c", 5, 10, D("0.5"), D("0.5"))])
    entry = next(e for e in quiet.trace if e.parameter == "beta")
    exp = explain_change(entry, CAP)
    assert exp is not None
    assert exp.sentence == "Quality stays 60: no client rating for this project yet."


def test_no_paper_symbols_in_user_sentences() -> None:
    """§13.10: plain words only — no Greek letters, equation numbers or C1–C4."""
    for sentence in _sentences().values():
        assert not re.search(r"[ωμβλεΓκα]|Eq\.|\bC[1-5]\b", sentence), sentence


def test_unknown_reason_or_parameter_is_dropped() -> None:
    entry = r.compute_snapshot([A]).trace[0]
    odd = r.TraceEntry(entry.history_id, entry.parameter, entry.old, entry.raw, entry.new,
                       "SOMETHING_NEW", {})  # fmt: skip
    assert explain_change(odd, CAP) is None
    other = r.TraceEntry("A", "nonsense", D(0), D(0), D(0), "DERIVED", {})
    assert explain_change(other, CAP) is None
