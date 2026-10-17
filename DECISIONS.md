# Decisions

Every deviation, ambiguity resolution and dependency choice (spec §0.2 rule 14).
Format: date · decision · reason · alternatives considered.

## 2026-10-17 — Phase 0

**D1 · Lock files via `uv pip compile --generate-hashes`.** Same hashed requirements format as
pip-compile (spec §14.12); uv is installed and much faster. Locks are resolved with
`--exclude-newer` two weeks back so no brand-new release is pinned. *Alt:* pip-tools.

**D2 · Integration tests use the test-compose Postgres/Redis, not testcontainers.** The test
runner itself runs in a container, and mounting the Docker socket into containers is forbidden
(spec §14.12). The compose services are ephemeral (tmpfs) and use the real DB roles.
*Alt:* testcontainers on the host (needs host Python 3.12 and Docker socket access from tests).

**D3 · `make certs` falls back to openssl when mkcert is missing.** mkcert is not installed on
the team leader's laptop; a self-signed cert is enough for Phase 0. mkcert (trusted cert) is
required before Demo 1 for real-phone testing (§13.14, §17.0).

**D4 · Scanners run from pinned Docker images** (gitleaks, semgrep, trivy, Playwright), so no
host installs are needed and versions are identical on every laptop and in CI.

**D5 · Development uses 2 Gunicorn/Uvicorn workers.** `2×CPU+1` = 33 on a 16-core laptop with
7 GB RAM; production keeps the formula (`GUNICORN_WORKERS=0`).

**D6 · Shortlist size follows §9.2:** `K_s = max(3·count_s, 6)` per slot. §6.2's
"K = max(3·N, 20)" contradicts it; settings expose `filter.shortlist_factor` (3) and
`filter.shortlist_min` (6).

**D7 · Logout returns to `/`** (§13.4, §13.11 — two sections) instead of `/login` (§15.5).

**D8 · Settings keys and DB role added.** Keys the spec uses but §6.2 omits:
`rep.newcomer_review` (null = platform mean, fallback `rep.newcomer_review_fallback` 0.6),
`rep.gamma0_max` (0.60), `algorithm.mode`, `filter.newcomer_competency_check`,
`filter.shortlist_min`, `filter.relax_step`/`relax_max_steps` (0.05 / 3, §9.2),
`fitness.include_performance`, `fitness.use_skill_competency`, `exact.max_combinations`
(2,000,000), `bidding.max_extensions` (2), `trust.*` coefficients (§9.14). Role
`devsync_worker` (§14.15) is created in Phase 0 although §17 Phase 0 lists three roles.
`ratelimit.*` is added in Phase 1 with the rate-limit framework.

**D9 · Paper vs spec findings (open; for the supervisor / later phases).**
1. A3 quotes Eq. 17 as "1 otherwise"; the paper prints **−1**. −∞ remains the right choice
   because feasible fitness can be below −1 (Phase 7).
2. Algorithm 1 line 6 prints `argmin` for a ∈ {P, C}; almost certainly a typo. The spec's
   descending order for P/C will be recorded as resolution "A14" (Phase 5).
3. Algorithm 2 initialises positions `x ~ U(b_l, b_u)` and velocities
   `U(−|b_l,b_u|, |b_l,b_u|)`; the spec uses Bernoulli(N/k) positions and `U(b_l, b_u)`
   velocities. To be listed as an explicit resolution and tested (Phase 7).
4. Eq. 21's on-time condition is `t_i < T^d` (strict, deadline); the spec uses
   `actual_finish ≤ baseline EF` per milestone. To be confirmed (Phase 10, §23).
5. §9.12.1 row 3 computes the reward with c = bid × share (720,000) while the payout base
   is the split share (1,368,000). Both are kept as specified; flagged for the supervisor.
6. Farhan's seeded C = 0.7·0.55 + 0.3·0.60 = 0.565 exactly; the stage-1 seed check must use
   a tolerance (±0.005), not 2-decimal rounding (Phase 5).
7. E7 uses teams of 5–30, beyond the product's 2–10 limit: experiments call the pure
   algorithms directly (Phase 15).

**D10 · `--text-subtle` (#64748B) is used only on `--surface`.** On `--bg` (#F7F8FA) it is
4.48:1, below WCAG AA (4.5:1); on white it is 4.76:1. Tokens are unchanged; the contrast test
enforces the usage rule. Dark-theme status colours were chosen as lightened variants with
≥ 4.5:1 on their soft backgrounds (spec §13.1 asks for this without listing values).

**D11 · Playwright lives in `frontend/e2e/`** instead of a root `e2e/` folder, so it shares
`frontend/node_modules` (one lock file). Root `e2e/README.md` points there.

**D12 · Audit log has a `seq` identity column** giving the hash chain a total order; the chain
(`prev_hash`, `hash`) is computed by a database trigger under an advisory lock, so the
application cannot forge it.

**D13 · Placeholder metrics/health under `/api/v1`.** Liveness and readiness live at
`/api/v1/health` and `/api/v1/health/ready`; Nginx returns 404 for the readiness and
`/metrics` paths from outside (spec §10.2 lists them as `/health…` relative to the API base).

**D14 · Design skills installed after review (§0.4).** `frontend-design` from
`anthropics/skills` @ `dbd4588f9e1033efb41dad4bef2f7947c8993d44` (Apache-2.0) and ten
`threejs-*` skills from `CloudAI-X/threejs-skills` @ `b1c623076c661fc9b03dac19292e825a5d106823`
(MIT). Markdown only; no runtime downloads, keys or security-setting changes. Conflicts noted
and overridden in `.claude/skills/README.md` (spec tokens win; no remote HDR/CDN assets).
Phase 0's frontend is a placeholder; `frontend-design` became available after the scaffold,
and it will be applied from Phase 1 screens onward (Phase 2 restyles everything).

**D15 · Frontend build toolchain upgraded beyond the spec's pins (approved by Taeen,
2026-10-17).** §3 names Vite 5 and Tailwind CSS 3, but `npm audit` reported 3 critical and
6 high advisories in that toolchain (Vitest 2 / tinypool RCE gadget, Vite 5 path traversal,
Tailwind 3's `braces`/`micromatch` chain, which has no patched release in the 3.x line), and
the gate must fail on high/critical (§16.5 step 7, §16.10). Chosen: **Vite 6.4.4, Vitest
4.1.12, @vitest/coverage-v8 4.1.12, Tailwind CSS 4.3.3 (+ @tailwindcss/vite)** — the
oldest patched versions that still run on Node 20 (Vite 7+/Vitest 5 need Node ≥ 20.19/22).
`npm audit`: 0 vulnerabilities. Tailwind 4 moves theme config from `tailwind.config.ts` into
CSS (`@theme` in `src/index.css`); the §13.1 tokens are unchanged. `playwright-core` is
pinned to 1.63.0 via `overrides` to match `@playwright/test` and the gate's Playwright image.
React stays 18. *Alternative rejected:* keep the pinned versions and allowlist the advisories
(weakens a security gate). *Note:* Node 20 reached end of life in April 2026; moving the team
to Node 22 LTS (and then Vite 8 / Vitest 5) is recommended before Demo 1. npm 9 hits an
arborist bug when resolving this tree; use `npx npm@10 install` when changing dependencies
(`npm ci` works with npm 9).

**D16 · Gate findings fixed on the first full run (2026-10-17).**
- Nginx serves an explicit `server_name` (`localhost` in development; production names are
  set at deployment, Phase 15). Catch-all default servers return 400 for any other `Host`,
  and redirects/proxying use `$server_name`, never the client-supplied `$host` (Semgrep
  `request-host-used`; host-header attacks, spec §14.3).
- GitHub Actions pinned by commit SHA; Dependabot `cooldown` of 14 days (Semgrep
  supply-chain rules; consistent with D1's "no brand-new releases").
- `Page[T]` uses `typing.Generic` instead of PEP 695 syntax because Semgrep 1.95 cannot parse
  the latter (the module would otherwise go unscanned).
- `check_forbidden.py` scans what git would commit (tracked + untracked, honouring
  `.gitignore`), so local `.env` and dev certificates are not false positives; gitleaks and
  the git hooks still guard commits.
- Trivy downloads its database from `ghcr.io` (Google's `mirror.gcr.io` was unreachable) and
  caches it in the `devsync-trivy-cache` volume.
- The test stack publishes no host ports (tests use the internal network). Note for `make
  up`: this laptop runs Apache on port 80; set `HTTP_PORT=8080` in `.env` or stop Apache.
- Backend image sets `PYTHONPATH=/app` so Alembic and scripts can import `app`; tool caches
  (ruff, mypy, hypothesis) go to tmpfs in the read-only test container.

**D17 · Docker on the team leader's laptop moved from the snap to Docker's apt packages.**
The Docker snap (rev 3618) was denied all DNS traffic by AppArmor on Ubuntu 25.04 / kernel
6.14, so images could not be pulled. Docker CE from download.docker.com (already installed)
is now the only engine. Teammates should use Docker's apt packages too (as CI does).

**D18 · Nginx base moved to the 1.30 stable line on Debian trixie; images apply security
updates at build.** `nginxinc/nginx-unprivileged:1.28.0-bookworm` carried 60+ fixable
HIGH/CRITICAL Debian CVEs (OpenSSL, GnuTLS, Perl, expat…) and bookworm tags are no longer
rebuilt. Now `1.30.4-trixie` (brotli compiled against 1.30.4 on `debian:trixie-slim`), and
both runtime images run `apt-get upgrade` during the build. Rebuild with `--pull` before
each demo so the upgrade layer is refreshed (`make deps-update`, Phase 14).
