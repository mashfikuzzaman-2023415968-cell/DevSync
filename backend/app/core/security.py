"""Cryptographic building blocks (spec §14.4).

- Passwords: Argon2id (time_cost 3, memory 64 MiB, parallelism 2); parameters live in
  the hash, so changing them triggers a transparent rehash on the next login.
- Password policy: 10–128 characters, zxcvbn score ≥ 3, not in the bundled list of
  100k most common passwords. No composition rules; paste and managers allowed.
- Tokens: `secrets` only; stored as SHA-256 digests, compared in constant time.
- TOTP secrets: AES-256-GCM with a key derived from SECRET_KEY via HKDF, so a
  database dump alone does not reveal second factors.

Every function here is pure apart from reading the bundled password list once.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from zxcvbn import zxcvbn

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128
PASSWORD_MIN_SCORE = 3
MIN_PERSONAL_WORD = 3
OTP_DIGITS = 6
RECOVERY_CODE_COUNT = 10
_BREACHED_FILE = Path(__file__).resolve().parent / "data" / "breached-100k.txt.gz"
_GCM_NONCE_BYTES = 12

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2, hash_len=32)
# A real Argon2id hash used to spend the same time when the account does not exist,
# so login timing does not reveal whether an email is registered (§14.4).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalisation")


# --------------------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    """Argon2id hash with the configured parameters."""
    return _hasher.hash(password)


@dataclass(frozen=True)
class PasswordCheck:
    """Result of verifying a password against a stored hash."""

    ok: bool
    needs_rehash: bool = False


def verify_password(stored_hash: str | None, password: str) -> PasswordCheck:
    """Verify in roughly constant time; a missing hash still costs one Argon2 verify."""
    if stored_hash is None:
        with contextlib.suppress(VerificationError):
            _hasher.verify(_DUMMY_HASH, password)
        return PasswordCheck(ok=False)
    try:
        _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return PasswordCheck(ok=False)
    return PasswordCheck(ok=True, needs_rehash=_hasher.check_needs_rehash(stored_hash))


@lru_cache(maxsize=1)
def _breached_passwords() -> frozenset[str]:
    with gzip.open(_BREACHED_FILE, "rt", encoding="utf-8") as f:
        return frozenset(line.rstrip("\n") for line in f if line.strip())


def is_breached(password: str) -> bool:
    """True if the password (or its lower-case form) is in the bundled common list."""
    common = _breached_passwords()
    return password in common or password.lower() in common


def _expand_inputs(user_inputs: list[str] | None) -> list[str]:
    """Personal words for zxcvbn: each input, its email local part and its name/number pieces."""
    words: set[str] = set()
    for raw in user_inputs or []:
        if not raw:
            continue
        value = raw.lower()
        words.add(value)
        local = value.split("@", 1)[0]
        words.add(local)
        words.update(
            p for p in re.split(r"[^a-z0-9]+", local + " " + value) if len(p) >= MIN_PERSONAL_WORD
        )
    return sorted(words)


def password_problems(password: str, user_inputs: list[str] | None = None) -> list[str]:
    """Human-readable reasons the password is not acceptable (empty list = acceptable)."""
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"Use at least {PASSWORD_MIN_LENGTH} characters.")
    if len(password) > PASSWORD_MAX_LENGTH:
        problems.append(f"Use at most {PASSWORD_MAX_LENGTH} characters.")
        return problems  # don't feed huge input to zxcvbn
    if is_breached(password):
        problems.append("This password appears in lists of leaked passwords. Choose another.")
    elif (
        len(password) >= PASSWORD_MIN_LENGTH
        and int(zxcvbn(password, user_inputs=_expand_inputs(user_inputs))["score"])
        < PASSWORD_MIN_SCORE
    ):
        problems.append("This password is too easy to guess. Try a longer phrase.")
    return problems


# --------------------------------------------------------------------------- tokens


def generate_token(nbytes: int = 32) -> str:
    """URL-safe random token (256 bits by default)."""
    return secrets.token_urlsafe(nbytes)


def token_digest(token: str) -> bytes:
    """SHA-256 digest used to store tokens (sessions, email links)."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def hmac_sha256(key: bytes, message: str | bytes) -> bytes:
    """HMAC-SHA256 of a message."""
    data = message.encode("utf-8") if isinstance(message, str) else message
    return hmac.new(key, data, hashlib.sha256).digest()


def constant_time_equals(a: str | bytes, b: str | bytes) -> bool:
    """Timing-safe comparison for secrets of any type."""
    left = a.encode("utf-8") if isinstance(a, str) else a
    right = b.encode("utf-8") if isinstance(b, str) else b
    return hmac.compare_digest(left, right)


def generate_otp() -> str:
    """Six-digit one-time code from the OS CSPRNG."""
    return f"{secrets.randbelow(10**OTP_DIGITS):0{OTP_DIGITS}d}"


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Human-friendly single-use codes like `k7f2-9qxm-4d`."""
    alphabet = "23456789abcdefghjkmnpqrstuvwxyz"  # no 0/1/i/l/o to avoid misreading
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    """Lower-case and strip spaces so users can type codes loosely."""
    return code.strip().lower().replace(" ", "")


# --------------------------------------------------------------------------- keys & AEAD


def decode_secret_key(secret_key: str) -> bytes:
    """Raw bytes of SECRET_KEY (base64) — falls back to UTF-8 for development values."""
    try:
        raw = base64.b64decode(secret_key, validate=True)
    except ValueError:
        raw = b""
    if not raw:
        raw = secret_key.encode("utf-8")
    if not raw:
        raise ValueError("SECRET_KEY is empty")
    return raw


def derive_key(secret_key: str, purpose: str, length: int = 32) -> bytes:
    """Purpose-specific key via HKDF-SHA256 so one leaked key never unlocks another use."""
    return HKDF(
        algorithm=hashes.SHA256(), length=length, salt=None, info=f"devsync:{purpose}".encode()
    ).derive(decode_secret_key(secret_key))


def encrypt(key: bytes, plaintext: bytes, associated_data: bytes = b"") -> bytes:
    """AES-256-GCM; output is nonce ‖ ciphertext ‖ tag."""
    nonce = secrets.token_bytes(_GCM_NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, associated_data)


class DecryptionError(Exception):
    """Ciphertext was tampered with, truncated or encrypted under another key."""


def decrypt(key: bytes, blob: bytes, associated_data: bytes = b"") -> bytes:
    """Inverse of :func:`encrypt`; raises DecryptionError on any integrity failure."""
    if len(blob) <= _GCM_NONCE_BYTES:
        raise DecryptionError("ciphertext too short")
    nonce, ciphertext = blob[:_GCM_NONCE_BYTES], blob[_GCM_NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, associated_data)
    except InvalidTag as exc:
        raise DecryptionError("authentication failed") from exc
