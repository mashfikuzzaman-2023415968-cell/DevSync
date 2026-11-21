"""`make reputation-recalculate`: run `reputation.recalculate_all` now, in this process.

Recomputes every developer with a completed-project history from the active settings (spec §11;
the admin endpoint and button arrive with the Phase 12 console, DECISIONS D92). Runs inside the
worker container as SYSTEM, like the job; idempotent, and recorded in `jobs`.
"""

from __future__ import annotations

import json
import sys

from app.jobs import reputation_jobs


def main() -> int:
    summary = reputation_jobs.recalculate_all()
    print(f"reputation-recalculate: {json.dumps(summary, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
