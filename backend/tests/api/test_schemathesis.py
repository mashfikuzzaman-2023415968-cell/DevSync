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
    # A page cursor is an opaque token only the server issues, so a generated one is (almost)
    # never valid: a 422 naming the cursor is the correct answer to it. Any other response to
    # such a request — and every request without a cursor — is validated in full.
    if isinstance(case.query, dict) and case.query.get("cursor") is not None:
        response = case.call()
        assert response.status_code < 500, response.text
        if response.status_code == 422 and "cursor" in response.json()["error"].get("fields", {}):
            return
        case.validate_response(response)
        return
    case.call_and_validate()
