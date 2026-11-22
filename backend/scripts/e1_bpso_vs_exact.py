"""Experiment E1: is binary PSO optimal on small instances? (spec §19, D112; simulated data.)

For each seeded random instance (8–18 candidates, teams of 3–6, presets balanced / quality /
budget in turn, both algorithm modes) it solves the problem exactly and with PSO and records the
gap. Writes one CSV row per instance and prints the summary; exits 1 when PSO is optimal in fewer
than 95 % of the instances or the mean gap exceeds 2 % (§17 Phase 7), so the gate can run a
smoke version (`--instances 20`).

    python scripts/e1_bpso_vs_exact.py --instances 300 --out ../runs/experiments/e1.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

from app.algorithms.bpso import PsoParams, run_bpso
from app.algorithms.exact_solver import solve_exact
from app.algorithms.filtering import Mode
from app.algorithms.formation_bench import random_instance

PRESETS = ("balanced", "quality", "budget")
MIN_OPTIMAL = 0.95
MAX_MEAN_GAP = 0.02
FIELDS = ("seed", "mode", "preset", "candidates", "team_size", "exact_fitness", "pso_fitness",
          "gap", "optimal", "pso_ms", "iterations")  # fmt: skip


def run(instances: int, out: Path | None) -> tuple[float, float, int]:
    rows = []
    for seed in range(instances):
        mode = Mode.DEVSYNC if seed % 2 == 0 else Mode.PCS_REPLICATION
        preset = PRESETS[seed % len(PRESETS)]
        p = random_instance(seed, preset=preset, mode=mode)
        exact = solve_exact(p)
        if not exact.available or exact.fitness == -math.inf:
            continue
        start = time.perf_counter()
        pso = run_bpso(p, PsoParams(), seed)
        ms = (time.perf_counter() - start) * 1000
        gap = (exact.fitness - pso.fitness) / abs(exact.fitness) if pso.feasible else 1.0
        rows.append({
            "seed": seed, "mode": mode.value, "preset": preset, "candidates": p.size,
            "team_size": p.team_size, "exact_fitness": f"{exact.fitness:.6f}",
            "pso_fitness": f"{pso.fitness:.6f}", "gap": f"{gap:.6f}",
            "optimal": int(gap <= 1e-9), "pso_ms": f"{ms:.1f}", "iterations": pso.iterations,
        })  # fmt: skip
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    if not rows:
        return 0.0, 1.0, 0
    optimal = sum(int(r["optimal"]) for r in rows) / len(rows)
    mean_gap = sum(float(r["gap"]) for r in rows) / len(rows)
    return optimal, mean_gap, len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E1: binary PSO vs the exact solver (simulated)")
    parser.add_argument("--instances", type=int, default=300)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.instances <= 10_000:
        parser.error("--instances must be between 1 and 10000")
    optimal, mean_gap, n = run(args.instances, args.out)
    print(f"E1 (simulated): {n} instances, PSO optimal in {optimal:.1%}, mean gap {mean_gap:.3%}")
    return 0 if n and optimal >= MIN_OPTIMAL and mean_gap <= MAX_MEAN_GAP else 1


if __name__ == "__main__":
    sys.exit(main())
