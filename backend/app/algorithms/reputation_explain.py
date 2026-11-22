"""Plain-language "Why did this change?" sentences for reputation changes (spec §13.5 #16). PURE.

Turns one `TraceEntry` of `compute_snapshot()` into a sentence a developer can read: plain labels
(Expertise, Communication, …, never ω or Eq. 11; §13.10), scores as whole numbers 0–100 (§13.8),
and the concrete fact behind the change ("finished in 18 of 30 days"). When the change cap held
a parameter back, the sentence says so and names the uncapped value. A reason code this module
does not know is dropped (returns None) rather than echoed, as for bid reasons (D65).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.algorithms.reputation import TraceEntry

LABELS: Mapping[str, str] = {
    "omega": "Expertise",
    "x": "Communication",
    "xm": "Teamwork",
    "beta": "Quality",
    "mu": "Client diversity",
    "t": "Punctuality",
    "c": "Competency",
    "p": "Performance",
}

DOMAIN_WORDS: Mapping[str, str] = {
    "FRONTEND": "front-end",
    "BACKEND": "back-end",
    "DATABASE": "database",
    "MOBILE": "mobile",
    "DESIGN": "design",
    "TESTING": "testing",
    "DEVOPS": "DevOps",
    "DATA": "data",
}


def points(value: Decimal) -> int:
    """A 0–1 score as the whole number 0–100 the UI shows (half-up)."""
    return int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class ChangeExplanation:
    parameter: str
    label: str
    old: int  # 0–100
    new: int  # 0–100
    sentence: str


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _fact(entry: TraceEntry) -> str | None:
    """The concrete reason, without the "Label a → b:" prefix; None for an unknown code."""
    inp = entry.inputs
    code = entry.reason_code
    domain = DOMAIN_WORDS.get(inp.get("domain", ""), "this kind of")
    facts: dict[str, str | None] = {
        "NEW_DOMAIN": f"your first {domain} project",
        "SAME_DOMAIN": (
            f"another {domain} project ({_plural(int(inp.get('domains', '0')), 'domain')} "
            f"across {_plural(int(inp.get('projects', '0')), 'project')})"
        ),
        "COMMUNICATION": f"communication on this project was rated {_pts(inp, 'rating')}",
        "TEAMWORK": f"teammates and help with blockers rated this project {_pts(inp, 'rating')}",
        "REVIEWS": _review_fact(inp),
        "NO_REVIEWS": "no client rating for this project yet",
        "NEW_CLIENT": f"work for a new client ({_client_count(inp)})",
        "RETURNING_CLIENT": f"another project for a returning client ({_client_count(inp)})",
        "ON_TIME": f"finished in {inp.get('t_days')} of {inp.get('deadline_days')} days",
        "LATE": _late_fact(inp),
        "DERIVED": {
            "c": "follows from expertise and communication",
            "p": "follows from quality, client diversity and punctuality",
        }.get(entry.parameter),
    }
    return facts.get(code)


def _client_count(inputs: Mapping[str, str]) -> str:
    clients = _plural(int(inputs.get("clients", "0")), "client")
    return f"{clients} over {_plural(int(inputs.get('projects', '0')), 'project')}"


def _pts(inputs: Mapping[str, str], key: str) -> str:
    raw = inputs.get(key)
    return str(points(Decimal(raw))) if raw is not None else "—"


def _review_fact(inputs: Mapping[str, str]) -> str:
    parts = []
    if "internal" in inputs:
        parts.append(f"the client rated this project {_pts(inputs, 'internal')}")
    if "external" in inputs:
        parts.append(f"a verified outside review gave {_pts(inputs, 'external')}")
    return " and ".join(parts) if parts else "earlier client ratings"


def _late_fact(inputs: Mapping[str, str]) -> str:
    t_days, deadline = int(inputs.get("t_days", "0")), int(inputs.get("deadline_days", "0"))
    return f"finished {_plural(t_days - deadline, 'day')} after the {deadline}-day deadline"


def explain_change(entry: TraceEntry, cap: Decimal) -> ChangeExplanation | None:
    """One sentence for one parameter change, or None if the reason is unknown."""
    label = LABELS.get(entry.parameter)
    fact = _fact(entry)
    if label is None or fact is None:
        return None
    old, new = points(entry.old), points(entry.new)
    head = f"{label} stays {new}" if old == new else f"{label} {old} → {new}"
    sentence = f"{head}: {fact}."
    if entry.capped:
        sentence += (
            f" The change was limited to {points(cap)} points per project"
            f" (it would have been {points(entry.raw)})."
        )
    return ChangeExplanation(entry.parameter, label, old, new, sentence)
