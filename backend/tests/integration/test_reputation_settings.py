"""The newcomer reputation the filter uses follows the active `rep.*` settings (spec §6.2,
§9.1.3): `rep.newcomer_review` (β with no reviews), its fallback, and the Γ⁰ / weight keys."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.context import DbContext
from app.db.session import open_session
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


@pytest.mark.asyncio
async def test_newcomer_review_sets_beta_and_moves_p() -> None:
    default = await _view(PlatformSettingsValues())
    assert default.beta == pytest.approx(0.6)  # fallback while no platform mean exists
    assert default.p == pytest.approx(0.55)  # 0.5·0.6 + 0.25·0.5 + 0.25·0.5
    set_ = await _view(PlatformSettingsValues(rep=RepSettings(newcomer_review=D("0.9"))))
    assert set_.beta == pytest.approx(0.9)
    assert set_.p == pytest.approx(0.70)
    fallback = await _view(
        PlatformSettingsValues(rep=RepSettings(newcomer_review_fallback=D("0.2")))
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
