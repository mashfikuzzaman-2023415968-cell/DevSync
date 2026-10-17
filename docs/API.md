# API

The contract is `docs/api/openapi.json` (generated from code; the gate fails on drift).
Regenerate with `make openapi`. Conventions: spec §10.1; contract rules: §10.4.

## Phase 0 endpoints
| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/api/v1/health` | Liveness | Public |
| GET | `/api/v1/health/ready` | DB, Redis, queue readiness | Internal network only (Nginx returns 404) |
| GET | `/metrics` | Prometheus metrics | Internal network only |

Error envelope: `{"error": {"code", "message", "fields"?, "request_id"}}`.
