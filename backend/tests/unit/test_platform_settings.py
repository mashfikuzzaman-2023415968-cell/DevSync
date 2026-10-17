"""Platform settings validation (spec §6.2, §9.1.2 constraints) and the v1 seed snapshot."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.core.errors import SettingsValidationError
from app.schemas.platform_settings import PlatformSettingsValues, default_settings_document
from app.services.platform_settings import validate_settings

pytestmark = pytest.mark.unit

SEED_DIR = Path(__file__).resolve().parents[2] / "alembic" / "seed"
SEED_V1 = SEED_DIR / "platform_settings_v1.json"
SEED = SEED_DIR / "platform_settings_v2.json"


def doc_with(path: str, value: Any) -> dict[str, Any]:
    doc = copy.deepcopy(default_settings_document())
    group, key = path.split(".")
    doc[group][key] = value  # type: ignore[index]
    return doc


def test_defaults_match_spec_table() -> None:
    s = PlatformSettingsValues()
    assert str(s.rep.alpha_comm) == "0.7"
    assert (str(s.rep.kappa_ext), str(s.rep.kappa_int)) == ("0.7", "0.7")
    assert (str(s.rep.alpha_x), str(s.rep.alpha_e)) == ("0.3", "0.3")
    assert (str(s.rep.w_internal), str(s.rep.w_external)) == ("0.8", "0.2")
    assert [str(x) for x in s.rep.g] == ["0.5", "0.25", "0.25"]
    assert s.newcomer.threshold == 3
    assert (str(s.filter.P0), str(s.filter.C0)) == ("0.45", "0.40")
    assert (s.pso.particles, s.pso.max_iter, s.pso.early_stop_iters) == (30, 200, 40)
    assert s.exact.max_candidates == 18
    assert (s.pay.platform_fee_bp, s.pay.bonus_pool_bp, str(s.pay.q_max)) == (500, 1000, "0.25")
    assert s.pay.auto_approve_days == 7
    assert s.algorithm.mode == "devsync"


def test_v1_snapshot_still_validates_with_new_defaults_filled_in() -> None:
    v1 = json.loads(SEED_V1.read_text(encoding="utf-8"))
    assert "ratelimit" not in v1
    assert validate_settings(v1).ratelimit.login[0].limit == 5


def test_seed_snapshot_equals_schema_defaults_and_validates() -> None:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    assert seed == default_settings_document()
    validate_settings(seed)


def test_defaults_serialize_decimals_as_strings() -> None:
    doc = default_settings_document()
    assert doc["pay"]["q_max"] == "0.25"  # type: ignore[index]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("rep.kappa_ext", "0.5"),  # κ must be > 0.5
        ("rep.kappa_int", "0.4"),
        ("rep.alpha_x", "0.5"),  # α_x must be < 0.5
        ("rep.alpha_e", "0.9"),
        ("rep.alpha_comm", "1.1"),
        ("rep.w_internal", "0.7"),  # w_y + w_x must equal 1
        ("rep.g", ["0.5", "0.3", "0.3"]),  # g sums to 1
        ("rep.g", ["1.2", "-0.1", "-0.1"]),
        ("rep.gamma0_base", "0.9"),  # above gamma0_max
        ("filter.P0", "1.5"),
        ("pso.particles", 51),  # bounded per §15.4
        ("pso.max_iter", 401),
        ("pso.bounds", ["1", "-1"]),
        ("exact.max_candidates", 25),
        ("pay.platform_fee_bp", 10_001),
        ("pay.q_max", "0"),
        ("trust.age_weight", "0.5"),  # trust weights sum to 1
        ("algorithm.mode", "matlab"),
        ("ratelimit.login", [{"limit": 0, "window_seconds": 60}]),
        ("ratelimit.sse_concurrent", 0),
    ],
)
def test_invalid_settings_are_rejected(path: str, value: Any) -> None:
    with pytest.raises(SettingsValidationError) as exc:
        validate_settings(doc_with(path, value))
    assert exc.value.fields


def test_unknown_keys_are_rejected() -> None:
    doc = default_settings_document()
    doc["rep"]["surprise"] = 1  # type: ignore[index]
    with pytest.raises(SettingsValidationError):
        validate_settings(doc)


@pytest.mark.parametrize(("path", "value"), [("rep.kappa_ext", "0.51"), ("rep.alpha_x", "0.49")])
def test_boundary_values_just_inside_are_accepted(path: str, value: str) -> None:
    validate_settings(doc_with(path, value))
