"""The newcomer reputation the filter uses follows the active `rep.*` settings (spec §6.2,
§9.1.3): `rep.newcomer_review` (β with no reviews), its fallback, and the Γ⁰ / weight keys."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.context import DbContext
from app.db.session import open_session
from app.models.reputation import ReputationSnapshot
from app.schemas.platform_settings import PlatformSettingsValues, RepSettings
from app.services import reputation_read
from tests.helpers import stack_available
from tests.jobs.test_bidding_deadline import make_user

pytestmark = pytest.mark.integration
D = Decimal


@pytest.fixture(autouse=True)
def _stack(migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")


async def _view(settings: PlatformSettingsValues) -> reputation_read.ReputationView:
    dev = await make_user("DEVELOPER")  # no snapshot: a computed newcomer
    async with open_session(DbContext.system(), job=True) as db:
        return await reputation_read.read_one(db, dev, settings)


# Phase 6 (D98): with `rep.newcomer_review` unset, β is the platform mean over engine-computed
# snapshots of developers with ≥ newcomer.threshold projects, else the fallback. The shared test
# database may hold such snapshots from other tests, so the default case checks against the mean
# computed independently here, and the fallback cases raise the threshold so that none qualifies.
NO_EXPERIENCED = {"newcomer": {"threshold": 20}}


async def _platform_mean() -> float | None:
    async with open_session(DbContext.system(), job=True) as db:
        mean = await db.scalar(
            select(func.avg(ReputationSnapshot.beta)).where(
                ReputationSnapshot.settings_version.is_not(None),
                ReputationSnapshot.completed_projects >= 3,
            )
        )
    return None if mean is None else float(mean)


@pytest.mark.asyncio
async def test_newcomer_review_sets_beta_and_moves_p() -> None:
    expected = await _platform_mean() or 0.6
    default = await _view(PlatformSettingsValues())
    assert default.beta == pytest.approx(expected, abs=0.0005)  # stored to 3 places
    assert default.p == pytest.approx(0.5 * expected + 0.25, abs=0.0005)
    no_mean = await _view(PlatformSettingsValues.model_validate(NO_EXPERIENCED))
    assert no_mean.beta == pytest.approx(0.6)  # fallback while no platform mean exists
    assert no_mean.p == pytest.approx(0.55)  # 0.5·0.6 + 0.25·0.5 + 0.25·0.5
    set_ = await _view(PlatformSettingsValues(rep=RepSettings(newcomer_review=D("0.9"))))
    assert set_.beta == pytest.approx(0.9)
    assert set_.p == pytest.approx(0.70)
    fallback = await _view(
        PlatformSettingsValues.model_validate(
            {**NO_EXPERIENCED, "rep": {"newcomer_review_fallback": "0.2"}}
        )
    )
    assert fallback.beta == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_gamma0_and_weights_follow_the_settings() -> None:
    # make_user has no verified phone/email and no profile: Γ⁰ = gamma0_base.
    default = await _view(PlatformSettingsValues())
    assert default.x == pytest.approx(0.40)
    custom = await _view(
        PlatformSettingsValues(rep=RepSettings(gamma0_base=D("0.30"), f_default=D("0.5")))
    )
    assert custom.x == pytest.approx(0.30)
    assert custom.c == pytest.approx(0.15)  # 0.5·ω(0) + 0.5·0.30
