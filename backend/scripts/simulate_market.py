"""`scripts/simulate_market.py`: write a simulated market as JSON (spec §18.3, docs/SIMULATOR.md).

Deterministic per seed: the same arguments always give byte-identical output. The output holds
the latent traits (ground truth), so it is for experiments only and never loaded into the app
database; the demo seed stores only the personas' §9.1.1 inputs (`seed_demo.py --stage 2`).

    python scripts/simulate_market.py --seed 2026 --developers 200 --out market.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.algorithms.simulator import SimParams, market_to_json, simulate_market

MAX_DEVELOPERS = 5000  # bounds memory and time (§15.4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DevSync market simulator (§18.3)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--developers", type=int, default=200)
    parser.add_argument("--clients", type=int, default=40)
    parser.add_argument("--newcomer-share", type=float, default=0.30)
    parser.add_argument("--out", type=Path, help="output file (default: standard output)")
    args = parser.parse_args(argv)
    if not 0 <= args.developers <= MAX_DEVELOPERS:
        parser.error(f"--developers must be between 0 and {MAX_DEVELOPERS}")
    try:
        market = simulate_market(
            SimParams(seed=args.seed, developers=args.developers, clients=args.clients,
                      newcomer_share=args.newcomer_share)
        )  # fmt: skip
    except ValueError as exc:
        parser.error(str(exc))
    text = market_to_json(market)
    if args.out is None:
        sys.stdout.write(text + "\n")
    else:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"simulate_market: {len(market.developers)} developers → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
