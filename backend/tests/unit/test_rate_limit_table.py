"""The default rate limits equal the §14.8 table, row by row (spec §14.8, §16.4).

The behaviour of each wired row (429 + Retry-After, per-key isolation, window reset) is tested
through the API in `tests/security/test_rate_limits.py`; this file pins the configured numbers,
including the rows whose endpoints arrive in later phases, so a default can't drift silently.
"""

from __future__ import annotations

import pytest

from app.schemas.platform_settings import RateLimitSettings

pytestmark = pytest.mark.unit

MINUTE, HOUR, DAY = 60, 3600, 86_400

# §14.8 row → (settings scope, [(limit, window_seconds), …]).
SPEC_TABLE: dict[str, tuple[str, list[tuple[int, int]]]] = {
    "Authenticated API (global) 120/min": ("api_authenticated", [(120, MINUTE)]),
    "Unauthenticated API (global) 60/min": ("api_anonymous", [(60, MINUTE)]),
    "Login 5/min and 20/hour": ("login", [(5, MINUTE), (20, HOUR)]),
    "Registration 5/hour": ("registration", [(5, HOUR)]),
    "OTP send 1/60 s, 5/hour": ("otp_send", [(1, MINUTE), (5, HOUR)]),
    "Password reset request 3/hour": ("password_reset", [(3, HOUR)]),
    "Email verification resend 3/hour": ("email_resend", [(3, HOUR)]),
    "Bid create/edit 20/hour": ("bid", [(20, HOUR)]),
    "Project create 10/day": ("project_create", [(10, DAY)]),
    "Formation runs 10/hour": ("formation_run", [(10, HOUR)]),
    "Skill test attempts start 10/hour": ("test_start", [(10, HOUR)]),
    "Coding submissions 10/hour": ("coding_submit", [(10, HOUR)]),
    "Coding submissions (practice) 30/hour": ("coding_practice", [(30, HOUR)]),
    "Comments / discussion posts 60/hour": ("comment", [(60, HOUR)]),
    "Reviews 30/hour": ("review", [(30, HOUR)]),
    "Disputes 5/day": ("dispute", [(5, DAY)]),
    "File uploads 20/hour": ("upload", [(20, HOUR)]),
    "GitHub manual sync 1/10 min": ("github_sync", [(1, 10 * MINUTE)]),
    "Data export 2/day": ("data_export", [(2, DAY)]),
    "Admin endpoints 300/min": ("admin", [(300, MINUTE)]),
}


@pytest.mark.parametrize(("row", "expected"), SPEC_TABLE.items(), ids=list(SPEC_TABLE))
def test_default_matches_the_spec_row(
    row: str, expected: tuple[str, list[tuple[int, int]]]
) -> None:
    scope, rules = expected
    configured = getattr(RateLimitSettings(), scope)
    assert [(r.limit, r.window_seconds) for r in configured] == rules, row


def test_sse_connections_are_capped_at_three() -> None:
    """SSE connections: 3 concurrent per user (a count, not a window)."""
    assert RateLimitSettings().sse_concurrent == 3


def test_otp_verify_has_its_own_hourly_cap() -> None:
    """Five attempts per code are enforced per code by the OTP service; the endpoint also has a
    per-user hourly cap so a stream of fresh codes can't be guessed at without bound."""
    rules = RateLimitSettings().otp_verify
    assert rules
    assert all(r.window_seconds == HOUR and r.limit >= 5 for r in rules)


@pytest.mark.parametrize("limit", [0, -1, 100_001])
def test_out_of_range_limits_are_refused(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        RateLimitSettings.model_validate({"bid": [{"limit": limit, "window_seconds": 60}]})


@pytest.mark.parametrize("window", [0, 7 * DAY + 1])
def test_out_of_range_windows_are_refused(window: int) -> None:
    with pytest.raises(ValueError, match="window_seconds"):
        RateLimitSettings.model_validate({"bid": [{"limit": 5, "window_seconds": window}]})
