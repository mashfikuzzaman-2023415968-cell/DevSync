"""Critical Path Method for finish-to-start milestone plans (spec §9.10). PURE.

No database, web framework, network or clock access; deterministic. The planner
(`services/projects.py`) builds `MilestoneInput`s from the project's milestones and
their finish-to-start dependencies and calls `compute_cpm`, which returns earliest
and latest start/finish day offsets, slack, the critical flag per milestone, the
project duration and **all** critical paths. A plan with a dependency cycle raises
`CpmCycleError` carrying the cycle (the service turns it into a 422 for the client).

Day offsets are integers measured from day 0 (the project start). `schedule_dates`
maps them to calendar dates given a start date; calendar arithmetic is pure, so it
lives here too. All times are durations in whole days (spec §7.3: `duration_days`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta

# DFS colours for cycle detection (module constants: unvisited, on-stack, finished).
_WHITE, _GREY, _BLACK = 0, 1, 2


@dataclass(frozen=True)
class MilestoneInput:
    """One milestone for CPM: its id, duration and finish-to-start predecessors.

    `name` is optional and used only to make cycle reports and critical paths
    readable; identity is always `id`.
    """

    id: str
    duration_days: int
    predecessors: tuple[str, ...] = ()
    name: str = ""


@dataclass(frozen=True)
class CpmNode:
    """Schedule of one milestone (day offsets from project start)."""

    es: int  # earliest start
    ef: int  # earliest finish
    ls: int  # latest start
    lf: int  # latest finish
    slack: int  # ls - es (== lf - ef); 0 means on the critical path
    critical: bool


@dataclass(frozen=True)
class CpmResult:
    """The computed schedule: per-milestone nodes, total duration, all critical paths."""

    duration: int
    nodes: dict[str, CpmNode]
    critical_paths: tuple[tuple[str, ...], ...]


class CpmError(ValueError):
    """Base class for CPM input problems."""


class CpmValidationError(CpmError):
    """Duplicate id, unknown predecessor, self-dependency or non-positive duration."""


class CpmCycleError(CpmError):
    """The dependency graph has a cycle. `cycle` lists the milestone ids in order."""

    def __init__(self, cycle: tuple[str, ...]) -> None:
        self.cycle = tuple(cycle)
        shown = " → ".join(cycle)  # a → b → … → a
        super().__init__(f"Milestones form a dependency cycle: {shown}")


def _validate(milestones: list[MilestoneInput]) -> None:
    """Reject duplicate ids, unknown or self predecessors, and durations < 1 (§7.3)."""
    ids = [m.id for m in milestones]
    seen: set[str] = set()
    for m in milestones:
        if m.id in seen:
            raise CpmValidationError(f"duplicate milestone id: {m.id}")
        seen.add(m.id)
    known = set(ids)
    for m in milestones:
        if m.duration_days < 1:
            raise CpmValidationError(f"milestone {m.id} has duration {m.duration_days} (< 1)")
        for p in m.predecessors:
            if p == m.id:
                raise CpmValidationError(f"milestone {m.id} depends on itself")
            if p not in known:
                raise CpmValidationError(f"milestone {m.id} has unknown predecessor {p}")
        if len(set(m.predecessors)) != len(m.predecessors):
            raise CpmValidationError(f"milestone {m.id} lists a predecessor twice")


def find_cycle(milestones: list[MilestoneInput]) -> tuple[str, ...] | None:
    """Return one dependency cycle as an ordered id list (closing on itself), else None.

    DFS with a recursion stack (spec §9.10 step 1). Used both by `compute_cpm` and
    directly by the service to report a cycle before a full computation.
    """
    preds = {m.id: tuple(m.predecessors) for m in milestones}
    colour = dict.fromkeys(preds, _WHITE)
    stack: list[str] = []

    def visit(node: str) -> tuple[str, ...] | None:
        colour[node] = _GREY
        stack.append(node)
        for nxt in preds.get(node, ()):  # edge predecessor -> successor, walked via preds
            if nxt not in colour:
                continue  # unknown ids are a validation concern, not a cycle
            if colour[nxt] == _GREY:
                start = stack.index(nxt)
                return (*stack[start:], nxt)  # close the loop: a → … → a
            if colour[nxt] == _WHITE:
                found = visit(nxt)
                if found is not None:
                    return found
        stack.pop()
        colour[node] = _BLACK
        return None

    for m in milestones:
        if colour[m.id] == _WHITE:
            found = visit(m.id)
            if found is not None:
                return found
    return None


def _topological_order(milestones: list[MilestoneInput]) -> list[str]:
    """Kahn's algorithm over predecessor edges; raises `CpmCycleError` if incomplete."""
    preds = {m.id: set(m.predecessors) for m in milestones}
    successors: dict[str, list[str]] = {m.id: [] for m in milestones}
    indegree = {m.id: len(preds[m.id]) for m in milestones}
    for m in milestones:
        for p in m.predecessors:
            successors[p].append(m.id)
    queue = deque(sorted(mid for mid, d in indegree.items() if d == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for s in successors[node]:
            indegree[s] -= 1
            if indegree[s] == 0:
                queue.append(s)
    if len(order) != len(milestones):
        cycle = find_cycle(milestones)
        raise CpmCycleError(cycle if cycle is not None else ())
    return order


def _critical_paths(
    milestones: list[MilestoneInput],
    nodes: dict[str, CpmNode],
) -> tuple[tuple[str, ...], ...]:
    """Every path through critical milestones where each edge is finish-to-start tight.

    An edge predecessor→successor is on a critical path when both are critical and the
    successor starts exactly when the predecessor finishes (`ef == es`). Paths run from
    critical milestones with no such incoming edge to those with no such outgoing edge.
    """
    crit = {m.id for m in milestones if nodes[m.id].critical}
    out_edges: dict[str, list[str]] = {mid: [] for mid in crit}
    has_incoming: set[str] = set()
    for m in milestones:
        if m.id not in crit:
            continue
        for p in m.predecessors:
            if p in crit and nodes[p].ef == nodes[m.id].es:
                out_edges[p].append(m.id)
                has_incoming.add(m.id)
    starts = sorted(mid for mid in crit if mid not in has_incoming)
    paths: list[tuple[str, ...]] = []

    def walk(node: str, acc: tuple[str, ...]) -> None:
        nexts = sorted(out_edges[node])
        if not nexts:
            paths.append(acc)
            return
        for nxt in nexts:
            walk(nxt, (*acc, nxt))

    for start in starts:
        walk(start, (start,))
    return tuple(paths)


def compute_cpm(milestones: list[MilestoneInput]) -> CpmResult:
    """Forward/backward CPM pass over finish-to-start milestones (spec §9.10 steps 1–3).

    Returns earliest/latest start/finish day offsets, slack and the critical flag per
    milestone, the project duration (max earliest finish) and all critical paths.
    Raises `CpmValidationError` for malformed input and `CpmCycleError` for a cycle.
    """
    _validate(milestones)
    if not milestones:
        return CpmResult(duration=0, nodes={}, critical_paths=())
    order = _topological_order(milestones)
    by_id = {m.id: m for m in milestones}

    # Forward pass: ES = max EF of predecessors (0 if none); EF = ES + duration.
    es: dict[str, int] = {}
    ef: dict[str, int] = {}
    for mid in order:
        m = by_id[mid]
        es[mid] = max((ef[p] for p in m.predecessors), default=0)
        ef[mid] = es[mid] + m.duration_days
    duration = max(ef.values())

    successors: dict[str, list[str]] = {m.id: [] for m in milestones}
    for m in milestones:
        for p in m.predecessors:
            successors[p].append(m.id)

    # Backward pass: LF = min LS of successors (project duration for terminal nodes);
    # LS = LF - duration; slack = LS - ES; critical when slack == 0.
    ls: dict[str, int] = {}
    lf: dict[str, int] = {}
    for mid in reversed(order):
        m = by_id[mid]
        lf[mid] = min((ls[s] for s in successors[mid]), default=duration)
        ls[mid] = lf[mid] - m.duration_days

    nodes = {
        mid: CpmNode(
            es=es[mid],
            ef=ef[mid],
            ls=ls[mid],
            lf=lf[mid],
            slack=ls[mid] - es[mid],
            critical=(ls[mid] - es[mid]) == 0,
        )
        for mid in order
    }
    return CpmResult(
        duration=duration,
        nodes=nodes,
        critical_paths=_critical_paths(milestones, nodes),
    )


def schedule_dates(result: CpmResult, start_date: date) -> dict[str, tuple[date, date]]:
    """Map each milestone's earliest start/finish day offsets to calendar dates (§9.10 step 4).

    Calendar (inclusive-exclusive) dates: a milestone with ES=e, EF=f runs from
    ``start_date + e`` up to ``start_date + f``. Pure date arithmetic, no clock.
    """
    return {
        mid: (start_date + timedelta(days=node.es), start_date + timedelta(days=node.ef))
        for mid, node in result.nodes.items()
    }
