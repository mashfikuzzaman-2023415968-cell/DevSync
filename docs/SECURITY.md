# Security

Written from spec §14; grows every phase (§14.13). Each control links to its tests.

## Threat model (STRIDE summary)
See spec §14.2. Full table to be completed in Phase 14.

## Controls implemented (Phase 0)
| Control | Where | Tests |
|---|---|---|
| Production config validation (weak secret, console SMS, debug, http origin, Redis without password, `*` hosts, insecure cookies, CAPTCHA bypass) | `backend/app/core/config.py` | `tests/unit/test_config.py` |
| Log redaction of secrets | `backend/app/core/logging.py` | `tests/unit/test_logging.py` |
| Safe errors (no traces, request id) | `app/core/errors.py`, `app/core/middleware.py` | `tests/unit/test_errors.py` |
| Trusted hosts, 256 KB body limit, security headers, route timeout | `app/main.py`, `app/core/middleware.py` | `tests/api/test_app.py` |
| Append-only, hash-chained audit log; least-privilege grants | `alembic/versions/0001_foundation.py` | `tests/integration/test_foundation_db.py` |
| DB roles: migrator / app / worker / readonly, no superuser, no BYPASSRLS | `infra/postgres/init/01-roles.sh` | `tests/integration/test_foundation_db.py::test_app_role_has_no_ddl` |
| TLS 1.2+, HTTPS redirect, HSTS, exact CSP, headers, TRACE blocked, body limits, timeouts, internal endpoints hidden | `infra/nginx/` | `tests/edge/test_edge.py`, `frontend/e2e/smoke.spec.ts` |
| Hardened containers (non-root, read-only, no-new-privileges, cap_drop ALL) | `docker-compose*.yml`, Dockerfiles | gate step 18 |
| Forbidden patterns, layer rules, gitleaks, Bandit, Semgrep, pip-audit, npm audit, Trivy | `backend/scripts/`, `infra/semgrep/` | gate steps 5–7 |
| Dependency update policy | `.github/dependabot.yml` | — |

## Dependency update policy (§14.21)
Dependabot weekly (pip, npm, Docker, GitHub Actions). Critical vulnerabilities fixed within
48 hours, high within 7 days. `make lock` re-resolves Python locks; the gate fails on unfixed
high/critical findings.

## Residual risks (§14.14)
Simulated payments only; determined collusion with many real identities can evade rules;
self-hosted TLS certificates in development; Judge0 sandbox strength depends on Judge0;
SMS simulated in development; no third-party penetration test.
