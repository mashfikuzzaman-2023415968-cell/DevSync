"""Money helpers: integer paisa storage, Decimal arithmetic (spec §0.2 rule 10, §9.12.1).

Why Decimal: fees, splits, rewards and penalties need fractions and exponentials,
and binary floating point cannot represent them exactly. All fractional work
runs in one fixed context (precision 28, ROUND_HALF_EVEN for intermediate
steps) and is converted to paisa exactly once with an explicitly named rounding
mode. Floats are never accepted.
"""

from __future__ import annotations

from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    Inexact,
    localcontext,
)

PAISA_PER_TAKA = 100
BASIS_POINTS = 10_000

MONEY_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN, traps=[])

ALLOWED_ROUNDING = frozenset({ROUND_FLOOR, ROUND_HALF_EVEN})


def to_decimal(value: int | str | Decimal) -> Decimal:
    """Convert an int, decimal string or Decimal to Decimal; floats are rejected."""
    if isinstance(value, bool) or not isinstance(value, int | str | Decimal):
        raise TypeError("Money values must be int, str or Decimal (never float)")
    with localcontext(MONEY_CONTEXT):
        result = Decimal(value)
    if not result.is_finite():
        raise ValueError("Money values must be finite")
    return result


def to_paisa(value: Decimal, rounding: str) -> int:
    """Convert a Decimal amount of paisa to an integer with an explicit rounding mode."""
    if rounding not in ALLOWED_ROUNDING:
        raise ValueError(f"Unsupported rounding mode: {rounding}")
    if not value.is_finite():
        raise ValueError("Cannot convert a non-finite value to paisa")
    with localcontext(MONEY_CONTEXT) as ctx:
        ctx.traps[Inexact] = False
        return int(value.to_integral_value(rounding=rounding))


def apply_basis_points(amount_paisa: int, bp: int) -> int:
    """`floor(amount × bp / 10000)` in exact integer arithmetic (used for fees and splits)."""
    if amount_paisa < 0:
        raise ValueError("amount_paisa must be non-negative")
    if not 0 <= bp <= BASIS_POINTS:
        raise ValueError("basis points must be within 0..10000")
    return (amount_paisa * bp) // BASIS_POINTS


def format_taka(amount_paisa: int) -> str:
    """Human display `৳12,500` (whole taka, Bangladeshi/Indian digit grouping)."""
    if amount_paisa < 0:
        return "-" + format_taka(-amount_paisa)
    taka = amount_paisa // PAISA_PER_TAKA
    digits = str(taka)
    if len(digits) > 3:  # noqa: PLR2004 - grouping rule: last 3 digits, then pairs
        head, tail = digits[:-3], digits[-3:]
        pairs: list[str] = []
        while len(head) > 2:  # noqa: PLR2004
            pairs.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pairs.insert(0, head)
        digits = ",".join([*pairs, tail])
    return f"৳{digits}"
