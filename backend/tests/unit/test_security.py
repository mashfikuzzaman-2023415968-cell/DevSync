"""Passwords, tokens, keys and AEAD (spec §14.4)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.security import (
    DecryptionError,
    constant_time_equals,
    decode_secret_key,
    decrypt,
    derive_key,
    encrypt,
    generate_otp,
    generate_recovery_codes,
    generate_token,
    hash_password,
    hmac_sha256,
    is_breached,
    normalize_recovery_code,
    password_problems,
    token_digest,
    verify_password,
)

pytestmark = pytest.mark.unit


def test_hash_is_argon2id_with_spec_parameters() -> None:
    h = hash_password("a long enough passphrase 9!")
    assert h.startswith("$argon2id$")
    assert "m=65536,t=3,p=2" in h


def test_verify_password_ok_wrong_and_missing_hash() -> None:
    h = hash_password("a long enough passphrase 9!")
    assert verify_password(h, "a long enough passphrase 9!").ok
    assert not verify_password(h, "wrong passphrase entirely").ok
    assert not verify_password(None, "anything at all").ok  # dummy hash path
    assert not verify_password("not-a-hash", "anything").ok


def test_rehash_flag_when_parameters_are_weaker() -> None:
    from argon2 import PasswordHasher  # noqa: PLC0415

    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("pass phrase 123!")
    result = verify_password(weak, "pass phrase 123!")
    assert result.ok
    assert result.needs_rehash


@pytest.mark.parametrize("password", ["password123", "qwertyuiop", "Password1234"])
def test_breached_passwords_are_detected(password: str) -> None:
    assert is_breached(password) or is_breached(password.lower())


def test_strong_unique_passphrase_is_not_breached() -> None:
    assert not is_breached("violet tram canyon 8812 orbit")


@pytest.mark.parametrize(
    ("password", "fragment"),
    [
        ("short1!", "at least 10"),
        ("x" * 129, "at most 128"),
        ("qwertyuiop", "leaked"),
        ("zzzzzzzzzzzzzzzq", "too easy"),
    ],
)
def test_password_policy_rejections(password: str, fragment: str) -> None:
    problems = password_problems(password)
    assert any(fragment in p for p in problems), problems


def test_password_policy_uses_user_inputs() -> None:
    assert password_problems("nadiarahman2026", ["nadiarahman2026@example.com", "Nadia Rahman"])


def test_good_password_passes_policy() -> None:
    assert password_problems("correct horse battery staple 42!") == []


def test_tokens_are_long_unique_and_digested() -> None:
    tokens = {generate_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 43 for t in tokens)
    t = next(iter(tokens))
    assert token_digest(t) == token_digest(t)
    assert len(token_digest(t)) == 32


@settings(max_examples=50)
@given(st.integers(min_value=8, max_value=64))
def test_token_length_property(nbytes: int) -> None:
    assert len(generate_token(nbytes)) >= nbytes


def test_otp_is_six_digits() -> None:
    codes = [generate_otp() for _ in range(500)]
    assert all(len(c) == 6 and c.isdigit() for c in codes)
    assert len(set(codes)) > 400


def test_recovery_codes_shape_and_normalization() -> None:
    codes = generate_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert all(len(c) == 12 and c.count("-") == 2 for c in codes)
    assert normalize_recovery_code("  ABCD-efgh-12 ") == "abcd-efgh-12"


def test_constant_time_equals_types() -> None:
    assert constant_time_equals("abc", "abc")
    assert constant_time_equals(b"abc", "abc")
    assert not constant_time_equals("abc", "abd")


def test_hmac_is_deterministic_and_keyed() -> None:
    assert hmac_sha256(b"k", "m") == hmac_sha256(b"k", b"m")
    assert hmac_sha256(b"k", "m") != hmac_sha256(b"k2", "m")


def test_secret_key_decoding_and_derivation() -> None:
    import base64  # noqa: PLC0415

    raw = base64.b64encode(b"x" * 64).decode()
    assert decode_secret_key(raw) == b"x" * 64
    assert decode_secret_key("plain-dev-key") == b"plain-dev-key"
    with pytest.raises(ValueError, match="empty"):
        decode_secret_key("")
    assert derive_key(raw, "totp") != derive_key(raw, "csrf")
    assert len(derive_key(raw, "totp")) == 32


def test_aead_round_trip_and_tamper_detection() -> None:
    key = derive_key("dev-key-for-tests", "totp")
    blob = encrypt(key, b"JBSWY3DPEHPK3PXP", b"user-1")
    assert decrypt(key, blob, b"user-1") == b"JBSWY3DPEHPK3PXP"
    with pytest.raises(DecryptionError):
        decrypt(key, blob, b"user-2")  # copied to another user's row
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(DecryptionError):
        decrypt(key, tampered, b"user-1")
    with pytest.raises(DecryptionError):
        decrypt(derive_key("other-key", "totp"), blob, b"user-1")
    with pytest.raises(DecryptionError, match="short"):
        decrypt(key, b"123", b"user-1")
