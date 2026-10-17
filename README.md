# DevSync

**Plan the project, hire a fair team, monitor the work, learn from it.**

A web platform for collaborative software crowdsourcing: clients plan projects with the
Critical Path Method, DevSync forms fair teams with reputation-aware binary PSO, monitors the
work, pays through simulated milestone escrow and feeds outcomes back into reputation.
Implements and extends Akter et al. (2023), *Reputation aware optimal team formation for
collaborative software crowdsourcing in industry 5.0* (JKSUCIS 35(8) 101710).

CSE 3102 — Software Design and Development Project, Department of CSE, University of Dhaka.
Supervisor: Palash Roy. Team: Mashfikuzzaman Taeen (team leader), Salwa Baki (backend),
Raisa Tabassum (frontend), Sara Binte Shafayet (tester).

## Quick start
Requirements: Docker with Compose v2, Node 20, make, Python 3 (for the gate script).

```bash
make env      # .env with fresh random secrets (never commit it)
make certs    # dev TLS certificate (mkcert if installed, else self-signed)
make up       # https://localhost  (Mailpit: http://127.0.0.1:8025)
make migrate  # apply database migrations as devsync_migrator
make gate PHASE=0
```

## Documentation
- Build specification: [`DEVSYNC_BUILD_SPEC.md`](DEVSYNC_BUILD_SPEC.md) (authoritative)
- Progress and hand-offs: [`PROGRESS.md`](PROGRESS.md), [`docs/OWNERSHIP.md`](docs/OWNERSHIP.md)
- Decisions: [`DECISIONS.md`](DECISIONS.md) · Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Security: [`docs/SECURITY.md`](docs/SECURITY.md) · Testing: [`docs/TESTING.md`](docs/TESTING.md)
- Working rules for Claude Code: [`CLAUDE.md`](CLAUDE.md) · AI disclosure: [`docs/AI_ASSISTANCE.md`](docs/AI_ASSISTANCE.md)

Payments in DevSync are **simulated**; no real money moves.
