# Security review — Phase 0 (Foundations)

- **Date:** 2026-10-17
- **Reviewer:** Claude Code (Claude Opus 5.5), with Mashfikuzzaman Taeen
- **Scope:** everything added in Phase 0: `backend/app`, `backend/alembic`, `backend/scripts`,
  `infra/` (Nginx, Postgres roles, Semgrep), `docker-compose*.yml`, Dockerfiles, `frontend/`
  (config, tokens, placeholder), CI and pre-commit configuration.
- **Method:** the built-in `/security-review` command could not run because it diffs against
  `origin/HEAD` and the GitHub repository has no commits yet. The same review was therefore
  done manually over every file in scope, using the spec's §14 controls and the OWASP Top 10
  as the checklist. From Phase 1 on, the command runs normally against the `phase-0` tag.
- **Tester's human check (spec §14.22):** _pending (Sara Binte Shafayet)_

Unresolved high findings: 0

## Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | API image healthcheck called `http://127.0.0.1:8000` without an allowed `Host`, so TrustedHostMiddleware would answer 400 and the container would never become healthy (availability, and a temptation to weaken `ALLOWED_HOSTS`). | **Fixed:** the healthcheck sends `Host: api` (`backend/Dockerfile`). |
| 2 | Medium | Two concurrent settings saves could compute the same `max(version)+1`; the unique constraint would reject one with an unhandled DB error. | **Fixed:** `create_version` takes a transaction-level advisory lock (`app/services/platform_settings.py`). |
| 3 | Low | Unhandled exceptions were answered by Starlette's outer error middleware, without the request id or security headers. | **Fixed:** in-chain `UnhandledExceptionMiddleware`; tested in `tests/unit/test_errors.py`. |
| 4 | Low | Redis `--requirepass` appears in the container's process list and `docker inspect`. Only reachable on the internal `app` network; no host port. | Accepted for Phase 0; Phase 14 moves Redis production config to a mounted config file / Docker secret. |
| 5 | Low | The dev TLS key is written with mode 644 so the unprivileged Nginx (uid 101) can read it. Dev-only, self-signed, gitignored. | Accepted (development only; production uses Let's Encrypt via §20.2). |
| 6 | Low | GitHub Actions are pinned by major tag, not commit SHA. | **Fixed** (see 12). |
| 7 | High | `npm audit` found 3 critical / 6 high advisories in the spec-pinned frontend toolchain (Vitest 2, Vite 5, Tailwind 3 dependency chain). Dev/build tooling only, but the gate requires zero high/critical. | **Fixed:** upgraded to Vite 6.4.4, Vitest 4.1.12, Tailwind 4.3.3 (DECISIONS D15); `npm audit`: 0 vulnerabilities. |
| 8 | Info | The gate's Trivy step mounts the Docker socket read-only into the Trivy container on the **host** (gate tooling). No application container mounts the socket. | No action (complies with §14.12). |
| 10 | Medium | Nginx used the client-supplied `$host` in redirects and as the upstream `Host` (host-header injection; Semgrep `request-host-used`). | **Fixed:** explicit `server_name`, catch-all servers return 400, `$server_name` used (D16). |
| 11 | Medium | Nginx base image (`1.28.0-bookworm`) had 60+ fixable HIGH/CRITICAL Debian CVEs (OpenSSL, GnuTLS, Perl, expat). | **Fixed:** `1.30.4-trixie` + `apt-get upgrade` at build; Trivy clean (D18). |
| 12 | Low | GitHub Actions on mutable tags; Dependabot without cooldown (supply chain). | **Fixed:** actions pinned by SHA, 14-day cooldown (D16); supersedes finding 6. |
| 9 | Info | A client-supplied `X-Request-ID` is accepted only if it matches `^[A-Za-z0-9._-]{8,64}$`; Nginx always overwrites it with `$request_id`. | No action. |

## Controls verified (spec §14.13 row 0)

- Secure config validation refuses insecure production settings (each case unit-tested).
- Secrets only via environment; `.env` generated with 600 permissions and gitignored;
  gitleaks and the forbidden-pattern scanner block committed secrets.
- Logs are structured JSON with key- and value-based redaction (unit-tested).
- Errors never include stack traces, SQL or input values; every response carries a request id.
- Non-root containers with read-only root filesystems, `no-new-privileges`, all
  capabilities dropped; only Nginx publishes ports; the `sandbox` network is internal.
- Database roles: no superuser, no `BYPASSRLS`; app/worker have DML only and no
  UPDATE/DELETE/TRUNCATE on `audit_log` and `platform_settings` (integration-tested).
- `audit_log` is append-only (row + TRUNCATE triggers) and hash-chained in the database;
  tampering is detected by `audit_verify_chain()` (integration-tested).
- Nginx: TLS 1.2/1.3, HTTP→HTTPS 301, HSTS, exact CSP and security headers, `server_tokens
  off`, TRACE/unknown methods → 405, 1 MB body limit, all §15.3 timeouts, coarse rate limits,
  `/metrics` and `/api/v1/health/ready` unreachable from outside (edge-tested).
- Frontend build: no inline scripts/styles, no external URLs, assets never inlined as data:
  URIs, hidden source maps removed from the image (build test).
- Dependabot configured; Bandit, Semgrep, gitleaks, pip-audit, npm audit and Trivy run in
  the gate.
