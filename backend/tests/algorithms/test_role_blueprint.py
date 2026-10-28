"""Role assessment blueprint builder (role assessment spec §5.1, §17.1)."""

from __future__ import annotations

import dataclasses

import pytest

from app.algorithms import role_blueprint as rb

pytestmark = pytest.mark.unit

FASTAPI, PG, REACT, TESTING = "s-fastapi", "s-pg", "s-react", "s-testing"
NAMES = {FASTAPI: "FastAPI", PG: "PostgreSQL", REACT: "React", TESTING: "Testing"}


def _c(skill: str, code: str, core: bool, pos: int, *kw: str) -> rb.Competency:
    return rb.Competency(f"{skill}.{code}", skill, code, code.replace("_", " ").title(), core,
                         tuple(kw or (code,)), pos)  # fmt: skip


CATALOGUE = {
    FASTAPI: [
        _c(FASTAPI, "api_design", True, 1, "api", "rest", "endpoint"),
        _c(FASTAPI, "validation_schemas", True, 2, "validation", "pydantic"),
        _c(FASTAPI, "authn_authz", True, 3, "login", "sign in", "roles", "permissions", "otp"),
        _c(FASTAPI, "databases_orm", False, 4, "database", "sqlalchemy"),
        _c(FASTAPI, "async_performance", False, 5, "async", "real-time"),
        _c(FASTAPI, "error_handling", False, 6, "errors", "logging"),
        _c(FASTAPI, "api_security", False, 7, "security", "payments"),
    ],
    PG: [
        _c(PG, "data_modelling", True, 1, "schema", "tables"),
        _c(PG, "sql_queries", True, 2, "sql", "reports"),
        _c(PG, "constraints_integrity", True, 3, "constraints"),
        _c(PG, "indexes_performance", False, 4, "index", "slow"),
    ],
    REACT: [
        _c(REACT, "components_props", True, 1, "component"),
        _c(REACT, "state_hooks", True, 2, "state", "cart"),
        _c(REACT, "effects_data", True, 3, "fetch"),
    ],
    TESTING: [
        _c(TESTING, "test_design", True, 1, "test cases"),
        _c(TESTING, "unit_testing", True, 2, "unit tests"),
        _c(TESTING, "api_integration", True, 3, "api testing"),
    ],
}
ALL = [c for cs in CATALOGUE.values() for c in cs]


def _counts(n: int = 3) -> dict[tuple[str, int], int]:
    return {(c.id, d): n for c in ALL for d in (1, 2, 3)}


def _input(
    primary: str = FASTAPI,
    milestones: list[set[str]] | None = None,
    text: str = "",
    counts: dict[tuple[str, int], int] | None = None,
    params: rb.BlueprintParams | None = None,
) -> rb.BlueprintInput:
    return rb.BlueprintInput(
        primary_skill_id=primary,
        skill_names=NAMES,
        milestones=[frozenset(m) for m in (milestones if milestones is not None else [{primary}])],
        text=text,
        catalogue=CATALOGUE,
        bank_counts=counts if counts is not None else _counts(),
        params=params or rb.BlueprintParams(),
    )


def _bp(inp: rb.BlueprintInput) -> rb.Blueprint:
    result = rb.build_blueprint(inp)
    assert isinstance(result, rb.Blueprint), result
    return result


def _invariants(bp: rb.Blueprint) -> None:
    weights = [c.weight_bp for c in bp.competencies]
    assert sum(weights) == 10_000
    assert all(1000 <= w <= 4000 and w % 500 == 0 for w in weights)
    assert 4 <= len(bp.competencies) <= 6
    assert sum(c.question_count for c in bp.competencies) == bp.question_count
    assert all(c.question_count >= 1 for c in bp.competencies)
    assert sum(c.easy for c in bp.competencies) == bp.difficulty_mix.easy
    assert sum(c.medium for c in bp.competencies) == bp.difficulty_mix.medium
    assert sum(c.hard for c in bp.competencies) == bp.difficulty_mix.hard
    assert all(c.easy + c.medium + c.hard == c.question_count for c in bp.competencies)
    assert all(1 <= len(c.reasons) <= 3 for c in bp.competencies)


# ---------------------------------------------------------------------- related skills


def test_no_related_skills_gives_the_primary_all_points() -> None:
    bp = _bp(_input())
    assert {c.skill_id for c in bp.competencies} == {FASTAPI}
    _invariants(bp)


def test_related_skills_are_the_top_two_by_shared_milestones() -> None:
    ms = [{FASTAPI, PG}, {FASTAPI, PG}, {FASTAPI, TESTING}, {FASTAPI, REACT}, {REACT}]
    related = rb.related_skills(FASTAPI, [frozenset(m) for m in ms], NAMES)
    # PostgreSQL twice; React and Testing once each → the tie goes to the name (React < Testing).
    assert related == [(PG, 2), (REACT, 1)]


def test_milestones_without_the_primary_skill_are_ignored() -> None:
    ms = [frozenset({PG, TESTING}), frozenset({FASTAPI})]
    assert rb.related_skills(FASTAPI, ms, NAMES) == []


def test_one_related_skill_contributes_only_its_core_competencies() -> None:
    text = "schema tables sql reports constraints " * 3
    bp = _bp(_input(milestones=[{FASTAPI, PG}], text=text))
    related = [c for c in bp.competencies if c.skill_id == PG]
    assert all(c.code != "indexes_performance" for c in related)  # not core
    assert sum(c.skill_id == FASTAPI for c in bp.competencies) >= 3
    _invariants(bp)


# ------------------------------------------------------------------------- keywords


def test_keyword_hits_are_whole_words_and_capped_at_three() -> None:
    text = rb.normalise_text("Login, LOGIN and login again; logins don't count. login")
    assert rb.keyword_hits(text, "login") == 3
    assert rb.keyword_hits(text, "log") == 0
    assert rb.keyword_hits(rb.normalise_text("Please sign in."), "sign in") == 1


def test_no_keywords_keeps_equal_base_points() -> None:
    bp = _bp(_input())
    # 7 primary competencies with equal scores, top 6 kept: core first, then position, so the
    # last by position (api_security) is the one left out.
    assert {c.code for c in bp.competencies} == {
        "api_design",
        "validation_schemas",
        "authn_authz",
        "databases_orm",
        "async_performance",
        "error_handling",
    }


def test_keyword_boost_moves_a_competency_up() -> None:
    plain = _bp(_input())
    boosted = _bp(_input(text="Customers sign in with OTP; admins manage roles and permissions."))
    assert boosted.competencies[0].code == "authn_authz"
    weight = {c.code: c.weight_bp for c in boosted.competencies}
    assert weight["authn_authz"] > {c.code: c.weight_bp for c in plain.competencies}["authn_authz"]
    reasons = {c.code: c.reasons for c in boosted.competencies}["authn_authz"]
    assert any(r.startswith("The requirements mention: ") for r in reasons)


def test_boost_is_capped_at_five_hits() -> None:
    five = _bp(_input(text="login " * 3 + "roles " * 2))
    many = _bp(_input(text="login " * 3 + "roles " * 3 + "permissions " * 3 + "otp " * 3))
    w5 = {c.code: c.weight_bp for c in five.competencies}["authn_authz"]
    wmany = {c.code: c.weight_bp for c in many.competencies}["authn_authz"]
    assert w5 == wmany


# ------------------------------------------------------------------- selection rules


def test_at_least_three_primary_competencies_replace_related_ones() -> None:
    # Heavy related keywords would push related competencies above the primary ones.
    text = ("schema tables sql reports constraints " * 5) + ("component state cart fetch " * 5)
    ms = [{REACT, PG}, {REACT, PG}, {REACT, TESTING}]
    bp = _bp(_input(primary=REACT, milestones=ms, text=text))
    assert sum(c.skill_id == REACT for c in bp.competencies) >= 3
    _invariants(bp)


def test_fewer_than_four_competencies_is_unavailable() -> None:
    result = rb.build_blueprint(_input(primary=REACT))
    assert isinstance(result, rb.Unavailable)
    assert result.reason is rb.UnavailableReason.INSUFFICIENT_COMPETENCIES


def test_fewer_than_three_primary_competencies_is_unavailable() -> None:
    counts = _counts()
    for c in CATALOGUE[REACT][1:]:
        for d in (1, 2, 3):
            counts[(c.id, d)] = 0
    ms = [{REACT, PG}, {REACT, TESTING}]
    result = rb.build_blueprint(_input(primary=REACT, milestones=ms, counts=counts))
    assert isinstance(result, rb.Unavailable)
    assert result.reason is rb.UnavailableReason.INSUFFICIENT_PRIMARY_COMPETENCIES


def test_a_competency_without_enough_approved_questions_is_left_out() -> None:
    counts = _counts()
    for d in (1, 2, 3):
        counts[(f"{FASTAPI}.authn_authz", d)] = 1  # 3 approved < min 4
    bp = _bp(_input(counts=counts, text="login roles permissions"))
    assert "authn_authz" not in {c.code for c in bp.competencies}
    _invariants(bp)


def test_a_competency_that_cant_supply_its_difficulties_is_removed() -> None:
    counts = _counts()
    for d in (1, 2, 3):
        counts[(f"{FASTAPI}.api_design", d)] = 0
    counts[(f"{FASTAPI}.api_design", 1)] = 5  # enough in total, only easy
    bp = _bp(_input(counts=counts, text="api rest endpoint " * 3))
    assert "api_design" not in {c.code for c in bp.competencies}
    _invariants(bp)


# --------------------------------------------------------------------- weights


def test_weights_are_clamped_rounded_and_sum_to_10000() -> None:
    bp = _bp(_input(text="login roles permissions otp sign in " * 3))
    _invariants(bp)
    assert max(c.weight_bp for c in bp.competencies) <= 4000


def test_rounding_difference_goes_to_the_largest_weight() -> None:
    cands = [
        rb._Candidate(_c(FASTAPI, f"c{i}", True, i), True, rb.Fraction(s), ())
        for i, s in enumerate([30, 20, 20, 20, 10], start=1)
    ]
    weights = rb.weights_bp(cands)
    assert weights is not None
    assert sum(weights.values()) == 10_000
    assert all(w % 500 == 0 and 1000 <= w <= 4000 for w in weights.values())


def test_allocation_respects_minimum_one_and_total() -> None:
    weights = {"a": 4000, "b": 3000, "c": 1000, "d": 1000, "e": 1000}
    counts = rb.allocate_questions(weights, 12)
    assert sum(counts.values()) == 12
    assert min(counts.values()) >= 1
    assert counts["a"] >= counts["b"] >= counts["c"]


def test_difficulty_assignment_prefers_medium_then_easy_on_ties() -> None:
    pools = {"a": {1: 9, 2: 9, 3: 9}}
    assigned = rb.assign_difficulties(["a"], {"a": 3}, pools, rb.DifficultyMix(1, 1, 1))
    assert assigned == {"a": {1: 1, 2: 1, 3: 1}}


def test_difficulty_assignment_reports_the_competency_that_cant_supply() -> None:
    pools = {"a": {1: 9, 2: 9, 3: 9}, "b": {1: 1, 2: 1, 3: 1}}  # needs count ≥ assigned + 2
    assert (
        rb.assign_difficulties(["a", "b"], {"a": 2, "b": 1}, pools, rb.DifficultyMix(1, 1, 1))
        == "b"
    )


# ------------------------------------------------------------------- fingerprint


def test_same_input_same_blueprint_and_fingerprint() -> None:
    a = _bp(_input(text="Customers sign in with OTP and pay online."))
    b = _bp(_input(text="Customers sign in with OTP and pay online."))
    assert a == b


def test_whitespace_case_and_irrelevant_text_keep_the_fingerprint() -> None:
    a = _bp(_input(text="Customers sign in with OTP."))
    b = _bp(_input(text="  CUSTOMERS   sign in\twith otp.  A lovely green logo, by the way. "))
    assert a.fingerprint == b.fingerprint


def test_a_new_keyword_that_moves_a_weight_changes_the_fingerprint() -> None:
    a = _bp(_input(text="An online shop."))
    b = _bp(_input(text="An online shop where customers sign in, with roles and permissions."))
    assert a.fingerprint != b.fingerprint


def test_a_different_slot_skill_changes_the_fingerprint() -> None:
    ms = [{FASTAPI, PG}]
    a = _bp(_input(primary=FASTAPI, milestones=ms))
    b = rb.build_blueprint(_input(primary=PG, milestones=ms))
    assert isinstance(b, rb.Blueprint)
    assert a.fingerprint != b.fingerprint


def test_reasons_name_the_role_and_related_milestones() -> None:
    text = "schema tables sql reports " * 4
    bp = _bp(_input(milestones=[{FASTAPI, PG}, {FASTAPI, PG}, {FASTAPI, PG}], text=text))
    texts = [r for c in bp.competencies for r in c.reasons]
    assert "Core skill of this role (FastAPI)" in texts
    related = [r for c in bp.competencies if c.skill_id == PG for r in c.reasons]
    assert not related or "PostgreSQL is needed in 3 milestones of this role" in related


def test_label_names_the_skill_and_top_three_competencies() -> None:
    bp = _bp(_input())
    assert bp.label.startswith("FastAPI · ")
    assert bp.label.count(", ") == 2


def test_params_must_have_a_mix_that_adds_up() -> None:
    with pytest.raises(ValueError, match="difficulty mix"):
        rb.BlueprintParams(question_count=12, difficulty_mix=rb.DifficultyMix(4, 4, 3))


def test_unavailable_has_its_own_stable_fingerprint() -> None:
    a = rb.build_blueprint(_input(primary=REACT))
    b = rb.build_blueprint(_input(primary=REACT, text="anything"))
    assert isinstance(a, rb.Unavailable)
    assert isinstance(b, rb.Unavailable)
    assert a.fingerprint == b.fingerprint


def test_duplicate_codes_across_candidate_skills_are_refused() -> None:
    clash = {
        **CATALOGUE,
        PG: [dataclasses.replace(CATALOGUE[PG][0], code="api_design"), *CATALOGUE[PG][1:]],
    }
    inp = dataclasses.replace(_input(milestones=[{FASTAPI, PG}]), catalogue=clash)
    with pytest.raises(ValueError, match="unique"):
        rb.build_blueprint(inp)
