"""Application rate limiting with Redis sliding windows (spec §14.8, §16.8).

Each scope (`login`, `registration`, …) has one or more rules from
`platform_settings.ratelimit`. A request is counted in a sorted set per
(scope, key, window) by an atomic Lua script; exceeding any rule returns 429
with `Retry-After`. Keys are hashed so emails/IPs are never stored in clear.

If Redis is unreachable: authentication scopes fail **closed** (503), everything
else fails **open** (logged), matching the chaos requirements of §16.8.
"""

from __future__ import annotations

import hashlib
import math
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import DomainError, ErrorCode
from app.core.logging import get_logger

log = get_logger(__name__)

FAIL_CLOSED_SCOPES = frozenset(
    {"login", "registration", "otp_send", "otp_verify", "password_reset", "email_resend", "totp"}
)

# KEYS[1] = zset key; ARGV = now_ms, window_ms, limit, member
# Removes expired entries, counts, and adds the request only if under the limit.
# Returns {allowed (1/0), retry_after_ms}.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now, ARGV[4])
  redis.call('PEXPIRE', key, window)
  return {1, 0}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retry = window
if oldest[2] then retry = tonumber(oldest[2]) + window - now end
return {0, retry}
"""


@dataclass(frozen=True)
class Rule:
    """At most `limit` hits per `window_seconds`."""

    limit: int
    window_seconds: int


class RateLimited(DomainError):  # noqa: N818 - reads as the condition, like HTTP 429
    """Too many requests; carries the wait time for `Retry-After`."""

    code = ErrorCode.RATE_LIMITED

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(
            f"Too many attempts. Try again in {self.retry_after} seconds.",
            extra={"retry_after": self.retry_after},
        )


class RateLimitUnavailable(DomainError):  # noqa: N818
    """Redis is down and this scope fails closed."""

    code = ErrorCode.DEPENDENCY_UNAVAILABLE


def _redis_key(scope: str, rule: Rule, key: str) -> str:
    """One counter per rule: two rules with the same window must not share a key."""
    return f"rl:{scope}:{rule.window_seconds}s:{rule.limit}:{key}"


def hash_key(*parts: str) -> str:
    """Stable, non-reversible key for (scope inputs) such as IP + email."""
    return hashlib.sha256("|".join(p.lower() for p in parts).encode()).hexdigest()[:32]


class RateLimiter:
    """Sliding-window limiter over Redis."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._script = redis.register_script(_SLIDING_WINDOW_LUA)

    async def hit(self, scope: str, key: str, rules: Iterable[Rule]) -> None:
        """Count one request; raise RateLimited if any rule is exceeded."""
        now_ms = int(time.time() * 1000)
        try:
            for rule in rules:
                window_ms = rule.window_seconds * 1000
                redis_key = _redis_key(scope, rule, key)
                allowed, retry_ms = await self._script(
                    keys=[redis_key],
                    args=[now_ms, window_ms, rule.limit, f"{now_ms}-{uuid.uuid4().hex[:8]}"],
                )
                if not int(allowed):
                    retry = math.ceil(int(retry_ms) / 1000)
                    log.warning("rate_limited", scope=scope, retry_after=retry)
                    raise RateLimited(retry)
        except RedisError as exc:
            if scope in FAIL_CLOSED_SCOPES:
                log.error(
                    "rate_limit_unavailable_fail_closed", scope=scope, error=type(exc).__name__
                )
                raise RateLimitUnavailable from exc
            log.warning("rate_limit_unavailable_fail_open", scope=scope, error=type(exc).__name__)

    async def reset(self, scope: str, key: str, rules: Iterable[Rule]) -> None:
        """Clear counters (e.g. after a successful login)."""
        try:
            await self.redis.delete(*[_redis_key(scope, r, key) for r in rules])
        except RedisError:
            log.warning("rate_limit_reset_failed", scope=scope)
