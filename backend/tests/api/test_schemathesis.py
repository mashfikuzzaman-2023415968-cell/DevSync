"""Contract fuzzing with schemathesis (spec §16.1, §16.5 step 11).

Every operation in the OpenAPI document gets 200 generated requests; the run fails
on any 5xx, any status code the operation doesn't declare, and any response that
doesn't match its declared schema. The app is built in development mode (which
serves its OpenAPI document) against the test stack's Postgres and Redis.
"""

from __future__ import annotations

import os

import pytest
import redis
import schemathesis
from hypothesis import HealthCheck, settings

from app.core.config import Environment
from app.main import create_app
from tests.helpers import stack_available, stack_settings

pytestmark = pytest.mark.fuzz

if not stack_available():
    pytest.skip("contract fuzzing runs in the test stack", allow_module_level=True)

os.environ.setdefault("DEVSYNC_ENV", "test")
APP = create_app(
    stack_settings(DEVSYNC_ENV=Environment.DEVELOPMENT, ALLOWED_HOSTS="testserver,localhost")
)
schema = schemathesis.openapi.from_asgi("/api/v1/openapi.json", APP)
_REDIS = redis.Redis.from_url(os.environ["REDIS_URL"])


@schema.parametrize()
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_api_contract(case: schemathesis.Case) -> None:
    # Rate limiting is tested on its own; here every example must reach the contract.
    for key in _REDIS.scan_iter("rl:*"):
        _REDIS.delete(key)
    case.call_and_validate()
