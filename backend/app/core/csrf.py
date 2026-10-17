"""CSRF protection: session-bound double-submit token + Origin check (spec §14.6).

`GET /auth/csrf` sets the readable cookie `__Host-ds_csrf` (Secure, SameSite=Strict)
to `nonce.signature`, where the signature is HMAC(session csrf_secret, nonce) for
signed-in users, or HMAC(key derived from SECRET_KEY, nonce) for anonymous forms
(register, login). Every unsafe request must send the same value in
`X-CSRF-Token` **and** come from `PUBLIC_ORIGIN` (Origin, or Referer as fallback).
GET/HEAD/OPTIONS never change state, so they are not checked.
"""

from __future__ import annotations

import base64
import secrets
from urllib.parse import urlparse

from app.core.security import constant_time_equals, hmac_sha256

CSRF_COOKIE = "__Host-ds_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Only state-changing methods are checked; anything else (TRACE…) reaches the router → 405.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_TOKEN_LENGTH = 200


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def issue_token(key: bytes) -> str:
    """New `nonce.signature` token bound to `key`."""
    nonce = _b64(secrets.token_bytes(18))
    return f"{nonce}.{_b64(hmac_sha256(key, nonce))}"


def token_is_valid(token: str, key: bytes) -> bool:
    """Signature check (constant time)."""
    if not token or len(token) > MAX_TOKEN_LENGTH or token.count(".") != 1:
        return False
    nonce, signature = token.split(".")
    return constant_time_equals(signature, _b64(hmac_sha256(key, nonce)))


def origin_allowed(origin: str | None, referer: str | None, public_origin: str) -> bool:
    """True when Origin (or, if absent, Referer) is exactly the public origin."""
    expected = urlparse(public_origin)
    candidate = origin if origin and origin != "null" else referer
    if not candidate:
        return False
    parsed = urlparse(candidate)
    return (parsed.scheme, parsed.netloc) == (expected.scheme, expected.netloc)


def request_is_valid(
    *,
    cookie_token: str | None,
    header_token: str | None,
    key: bytes,
    origin: str | None,
    referer: str | None,
    public_origin: str,
) -> bool:
    """Full check for one unsafe request."""
    if not cookie_token or not header_token:
        return False
    if not constant_time_equals(cookie_token, header_token):
        return False
    if not token_is_valid(header_token, key):
        return False
    return origin_allowed(origin, referer, public_origin)
