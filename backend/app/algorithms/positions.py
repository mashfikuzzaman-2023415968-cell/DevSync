"""Fractional card positions for the Kanban board (D144). Pure: no DB, clock or randomness.

A key is a non-empty string over the 62 digits `0-9A-Za-z` (in that, ASCII, order) read as the
digits of a fraction in (0, 1): "V" is 31/62, "V8" is 31/62 + 8/62². Keys never end in "0", so
string order (byte order: the column uses `COLLATE "C"`) equals numeric order and there is always
another key strictly between two different keys. The server picks a key from the neighbours a
client names; when keys grow past `REKEY_LENGTH` the service re-keys the column with `spread`.
"""

from __future__ import annotations

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(DIGITS)
_INDEX = {c: i for i, c in enumerate(DIGITS)}
REKEY_LENGTH = 48  # the column allows 64; re-key long before
MAX_KEY_LENGTH = 64


class InvalidKeyError(ValueError):
    """A key that isn't a valid position (wrong alphabet, empty, trailing zero, out of order)."""


def is_valid_key(key: str) -> bool:
    return 0 < len(key) <= MAX_KEY_LENGTH and key[-1] != DIGITS[0] and all(c in _INDEX for c in key)


def _check(key: str) -> None:
    if not is_valid_key(key):
        raise InvalidKeyError(f"not a position key: {key!r}")


def _midpoint(a: str, b: str | None) -> str:
    """A key strictly between fractions `a` ("" means 0) and `b` (None means 1); `a < b`."""
    if b is not None:
        n = 0  # the shared prefix (a missing digit of `a` counts as "0")
        while n < len(b) and (a[n] if n < len(a) else DIGITS[0]) == b[n]:
            n += 1
        if n > 0:
            return b[:n] + _midpoint(a[n:], b[n:])
    low = _INDEX[a[0]] if a else 0
    high = _INDEX[b[0]] if b is not None else BASE
    if high - low > 1:
        return DIGITS[(low + high + 1) // 2]
    if b is not None and len(b) > 1:  # digits adjacent: b's first digit alone is between
        return b[0]
    return DIGITS[low] + _midpoint(a[1:], None)


def _after(a: str) -> str:
    """A short key just after `a` (the end of a column): bump the last digit that can grow,
    dropping what follows it. Repeated appends grow keys by one digit per ~31 cards."""
    for i in range(len(a) - 1, -1, -1):
        if a[i] != DIGITS[-1]:
            return a[:i] + DIGITS[_INDEX[a[i]] + 1]
    return a + DIGITS[BASE // 2]


def _before(b: str) -> str:
    """A key just before `b` (the start of a column): lower the last digit, or, when it is the
    smallest allowed ("1"), replace it with "0z". Grows by one digit per ~61 cards."""
    last = _INDEX[b[-1]]
    if last > 1:
        return b[:-1] + DIGITS[last - 1]
    return b[:-1] + DIGITS[0] + DIGITS[-1]


def key_between(before: str | None, after: str | None) -> str:
    """A new key that sorts after `before` and before `after` (either may be None: the start or
    the end of the column). Raises InvalidKeyError for invalid or unordered neighbours."""
    if before is not None:
        _check(before)
    if after is not None:
        _check(after)
    if after is None:
        return DIGITS[BASE // 2] if before is None else _after(before)
    if before is None:
        return _before(after)
    if not before < after:
        raise InvalidKeyError("the neighbours are not in order")
    return _midpoint(before, after)


def needs_rekey(key: str) -> bool:
    return len(key) > REKEY_LENGTH


def spread(count: int) -> list[str]:
    """`count` evenly spaced, short, increasing keys (re-keying a column keeps its order)."""
    if count < 0:
        raise ValueError("count must not be negative")
    if count == 0:
        return []
    width = 1
    while BASE**width <= count:
        width += 1
    slots = BASE**width
    keys: list[str] = []
    for i in range(1, count + 1):
        value = i * slots // (count + 1)
        digits = []
        for _ in range(width):
            value, d = divmod(value, BASE)
            digits.append(DIGITS[d])
        keys.append("".join(reversed(digits)).rstrip(DIGITS[0]))
    return keys
