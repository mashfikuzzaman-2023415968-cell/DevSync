"""Fractional card positions (D144): `app/algorithms/positions.py`. Pure.

Unit tests pin the edges (empty column, start, end, adjacent digits, invalid and unordered
neighbours, re-keying); property tests check the invariants the board relies on: a key between
any two different keys, string order equal to the order of insertion, keys that stay short, and
re-keying that keeps the order.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.algorithms.positions import (
    DIGITS,
    MAX_KEY_LENGTH,
    REKEY_LENGTH,
    InvalidKeyError,
    is_valid_key,
    key_between,
    needs_rekey,
    spread,
)

pytestmark = pytest.mark.unit

keys = st.text(alphabet=DIGITS, min_size=1, max_size=20).filter(lambda k: k[-1] != "0")


def test_first_key_of_an_empty_column_is_the_middle() -> None:
    assert key_between(None, None) == "V"


def test_start_and_end_of_a_column() -> None:
    assert key_between(None, "V") == "U"
    assert key_between("V", None) == "W"
    assert key_between("Vz", None) == "W"  # shorter is fine: "W" > "Vz"
    assert key_between("z", None) == "zV"
    assert key_between(None, "1") == "0z"
    assert key_between(None, "V1") == "V0z"


def test_a_thousand_prepends_stay_short() -> None:
    first: str | None = None
    for _ in range(1000):
        nxt = key_between(None, first)
        assert first is None or nxt < first
        first = nxt
    assert first is not None
    assert len(first) <= 20


def test_adjacent_digits_get_a_longer_key() -> None:
    k = key_between("A", "B")
    assert "A" < k < "B"
    assert k.startswith("A")


def test_a_prefix_neighbour_still_leaves_room() -> None:
    k = key_between("V", "V1")
    assert "V" < k < "V1"
    assert is_valid_key(k)


@pytest.mark.parametrize("bad", ["", "V0", "a-b", "é", "V" * (MAX_KEY_LENGTH + 1)])
def test_invalid_neighbours_are_refused(bad: str) -> None:
    with pytest.raises(InvalidKeyError):
        key_between(bad, None)
    with pytest.raises(InvalidKeyError):
        key_between(None, bad)


@pytest.mark.parametrize(("before", "after"), [("V", "V"), ("W", "V")])
def test_unordered_neighbours_are_refused(before: str, after: str) -> None:
    with pytest.raises(InvalidKeyError):
        key_between(before, after)


def test_rekey_threshold() -> None:
    assert not needs_rekey("V" * REKEY_LENGTH)
    assert needs_rekey("V" * (REKEY_LENGTH + 1))


@pytest.mark.parametrize("count", [0, 1, 2, 61, 62, 1000])
def test_spread_gives_short_increasing_valid_keys(count: int) -> None:
    out = spread(count)
    assert len(out) == count
    assert out == sorted(out)
    assert len(set(out)) == count
    assert all(is_valid_key(k) and len(k) <= 2 for k in out)


def test_spread_refuses_a_negative_count() -> None:
    with pytest.raises(ValueError, match="negative"):
        spread(-1)


def test_a_thousand_appends_stay_well_inside_the_column_limit() -> None:
    """1,000 tasks is the per-project cap (D143): appending them one by one never needs a
    re-key, and every key sorts after the previous one."""
    last: str | None = None
    for _ in range(1000):
        nxt = key_between(last, None)
        assert last is None or nxt > last
        last = nxt
    assert last is not None
    assert len(last) <= REKEY_LENGTH


@pytest.mark.property
@settings(max_examples=300, deadline=None)
@given(keys, keys)
def test_there_is_always_a_key_strictly_between(a: str, b: str) -> None:
    if a == b:
        return
    lo, hi = min(a, b), max(a, b)
    k = key_between(lo, hi)
    assert lo < k < hi
    assert is_valid_key(k)


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=200))
def test_random_inserts_keep_a_strict_total_order(slots: list[int]) -> None:
    """Insert each new card at a random place between its neighbours: the keys stay strictly
    increasing in board order, valid, and short."""
    board: list[str] = []
    for s in slots:
        i = s % (len(board) + 1)
        before = board[i - 1] if i > 0 else None
        after = board[i] if i < len(board) else None
        board.insert(i, key_between(before, after))
    assert board == sorted(board)
    assert len(set(board)) == len(board)
    assert all(is_valid_key(k) for k in board)


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=400))
def test_repeated_inserts_at_one_place_are_rekeyed_before_the_limit(n: int) -> None:
    """The worst case (always inserting right after the same card) grows keys by about one
    character per insert; the service re-keys the column when a key passes REKEY_LENGTH, and
    `spread` gives the same order back with short keys."""
    board = ["V", "W"]
    for _ in range(n):
        new = key_between(board[0], board[1])
        board.insert(1, new)
        if needs_rekey(new):
            board = spread(len(board))
    assert board == sorted(board)
    assert all(len(k) <= REKEY_LENGTH for k in board)
