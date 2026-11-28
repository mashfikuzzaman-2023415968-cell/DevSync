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

## 2026-10-17 — Phase 1

**D19 · Phase 1 dependencies and design choices.**
- Backend: `argon2-cffi`, `pyotp`, `zxcvbn`, `altcha` (spec-named) plus `cryptography`
  (AES-GCM + HKDF for TOTP secrets) and `email-validator` (pydantic `EmailStr`).
- Breached-password list: SecLists "100k most used passwords (NCSC)" (MIT) bundled as a
  gzipped plain list (272 KB) — the spec allows either the plain list or SHA-1 prefixes, and
  hashes don't compress (2.3 MB).
- CAPTCHA widget: an in-house ALTCHA v1 solver (`frontend/src/lib/captcha.ts`, Web Crypto)
  instead of the npm widget, whose injected styles and blob workers conflict with the strict
  CSP. The server uses the spec's `altcha` library; a unit test proves both agree.
- Pre-authentication lookups (login, session restore, consuming email tokens, registration)
  run through narrow SECURITY DEFINER functions owned by `devsync_migrator`; a
  `TO devsync_migrator USING (true)` policy lets them (and migrations) see rows under FORCE
  RLS. `is_system()` requires the `devsync_worker` role so web requests can't act as SYSTEM.
- Registration answers 202 uniformly and the browser then signs in with the same
  credentials (a session is never created for an existing account by registration).
- Password strength meter in the browser is a lightweight heuristic; zxcvbn (~400 KB gzip)
  would break the §13.7 route budget. The server's zxcvbn + breached-list check is the
  authority.
- Rate limits (§14.8) live in `platform_settings.ratelimit` (settings v2). The API layer may
  import `app.db` only to open the request's DB session (layer checker updated).

**D20 · React Router 7.18.4 instead of 6.x; one ESLint rule relaxed.** React Router 6 has
open-redirect (backslash in `<Link>`/`useNavigate`) and SSR-hydration advisories with no 6.x
fix; 7.18.4 supports React 18 and keeps the data-router API. `security/detect-object-injection`
is off: it only flags typed `Record` lookups with union keys (false positives in TypeScript);
real sinks stay covered by other ESLint rules and `check_forbidden.py`.

## 2026-10-17 — Phase 2

**D21 · No algorithm figures on the homepage until Phase 7 (decided with the student).**
Rule 0.2.6 says every homepage number comes from a real run of DevSync's filtering and PSO on
the sample project; those algorithms arrive in Phases 5–7. Until then the hero chip reads
"✓ Balanced team" and the fairness dial shows how many places are kept for newcomers (an
illustration of the rule, no named team, no cost-of-fairness %). Phase 7 adds
`scripts/build_homepage_example.py`, `src/content/homepage-example.json`, the % chip and the gate
freshness check. Other homepage values come only from the seed in spec §18.2/§18.4
(`src/content/sample.ts`, with a test that recomputes the CPM and C/P) or from `/public/stats`.

**D22 · Phase 2 dependencies and limits.** Spec-named: `framer-motion` 12.43 (mature line; 13
and 14 were 15 days old), shadcn-style components on `@radix-ui/react-*`,
`class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `cmdk`, `three` 0.186,
`@react-three/fiber` 8.18 + `@react-three/drei` 9.122 (the React 18 line); `get-nonce` (already
used by Radix, imported directly for D23); dev: `lighthouse` 13.5. No postprocessing package
(glow from emissive materials). New rate-limit scopes in settings v3: `public_stats` 60/min,
`client_errors` 10/min + 50/hour (the spec's §14.8 table has no rows for these endpoints).

**D23 · CSP: per-response style nonce for runtime `<style>` elements.** Radix's scroll lock
(`react-remove-scroll` → `react-style-singleton`) adds a `<style>` element when a dialog or
sheet opens, which `style-src 'self'` blocks. Following the spec's fallback (§14.3), Nginx puts
`$request_id` (128 random bits) into `style-src 'self' 'nonce-…'` and into `index.html` via
`sub_filter`; `index.html` is `no-store`; the app passes it to `get-nonce` and Framer's
`MotionConfig`. `script-src` stays `'self'` only; `'unsafe-inline'` is never used. Framer's
`popLayout` mode (which also injects styles) is not used. Zod 4 runs `jitless`, because its
`new Function` probe would otherwise trigger `script-src` violations.

**D24 · Still renders without image dependencies.** `/__stills` (development builds only) draws
the scene at fixed moments; `npm run render:stills` (`make stills`, pinned Playwright image)
saves `canvas.toDataURL("image/webp")` at 1x/2x in light and dark plus a 1200×630 social
preview PNG, and writes `stills-manifest.json` with a SHA-256 of the scene files and tokens,
which the gate recomputes.

**D25 · Slim `three` entry for the production bundle.** R3F v8 imports the whole THREE
namespace, which made the 3D chunk 242 KB gzip (budget 220). Vite aliases the bare `three`
import to `src/components/three/three-slim.ts`, which re-exports only what R3F, drei's `Html`
and `PerformanceMonitor` and our scene use (186 KB gzip). `three-slim.test.ts` scans those
libraries for every THREE member they reference, so a library update cannot silently break
production. drei's `Environment` is not used (it pulls HDR/EXR loaders); the two light panels
are rendered locally with `PMREMGenerator`.

**D26 · Homepage LCP and hero details.** The headline's words animate as inline spans (fade +
blur, 40 ms stagger) while the heading rises 8 px as one block (a per-word rise needs
inline-block spans, which Chrome would then report one by one as LCP candidates). When the
reveal finishes the heading becomes plain text, so the whole headline is the LCP element; the
poster is drawn on a 2D canvas (never an LCP candidate) and the 3D chunk is fetched only after
the reveal. The sticky navbar ignores restored scroll positions and anchor jumps when deciding
to hide. Measured with Lighthouse, the scene's start-up was the main cost, so it now builds a
32 px lighting environment and compiles its shaders asynchronously (with a 1.5 s fallback
for drivers that never report completion) before the first frame, and the per-frame loop
allocates nothing. On phone-sized screens the scene loads on the first scroll or touch (it
sits below the calls to action, and scrolling drives it); the poster shows until then. The
stats strip reserves its height, the first-screen Inter files are preloaded, and inactive
"How it works" steps use colour instead of opacity (AA contrast). Result: desktop 96–97,
mobile 94, CLS ≤ 0.008.

**D27 · E2E rate limits.** All E2E traffic comes from one container IP, so the real per-IP
limits (§14.8) would make independent tests throttle each other. The test-only router
(`DEVSYNC_ENV=test` only) gains `GET /__test__/ratelimits/reset` (a GET so it works while the
CSRF endpoint is throttled), the test environment alone exempts `/api/v1/__test__` from the
global limit (asserted by a test), Playwright resets before every test and between screens in
long loops, and runs one worker. Tests that check limits still build up their counts within
the test. Production limits are unchanged.

**D28 · The 60 fps check runs on the laptop's GPU.** Spec §13.12 asks for a steady 60 fps
"on the demo laptop, measured with the Playwright performance trace". The stock Playwright image
renders WebGL in software (SwiftShader, ~41 fps here), which measures the container, not the
laptop. Gate step 16 therefore builds `infra/playwright-gpu` (the pinned Playwright image plus
Mesa drivers) and passes one GPU in through `/dev/dri`, preferring Intel/AMD: NVIDIA's open NVK
driver stalled the GPU process intermittently. The test asserts the renderer is real hardware
(not SwiftShader/llvmpipe) and runs without trace recording, whose screenshots cost frames.
Measured: 60.0 fps, p95 frame 16.7 ms on the Intel UHD (Raptor Lake). A machine without a GPU
cannot pass this step.

## Phase 3 — profiles, files, skill tests

**D29 · New dependencies.** Backend: `python-magic` (+ `libmagic1` in the API image) and
`Pillow`, both named in spec §14.9; `python-multipart`, which FastAPI needs to parse the
multipart bodies of the upload endpoints (spec §10.2 names multipart uploads). Frontend:
`@dnd-kit/core`, `@dnd-kit/sortable` and `@dnd-kit/utilities` (spec-named for drag and drop),
used for portfolio reordering with pointer, touch and keyboard sensors. All releases are older
than 14 days and pinned exactly.

**D30 · Image "crop preview" without a cropping library.** The spec asks for an image preview
with crop/fit. Adding a cropper would be a new dependency and a second image pipeline in the
browser. Instead the dropzone previews the chosen file in exactly the frame it is shown in
(16:10, `object-fit: cover`), says so, and the server stores the full re-encoded image
(≤ 4096 px, no metadata). Developers see what clients will see; nothing is cropped away.

**D31 · Upload pipeline details (§14.9).** Accepted by signature only: PNG/JPEG/WebP for
portfolio images; PDF or image for certificates; PDF, UTF-8 plain text or image for external
review evidence. Size limits: images `MAX_UPLOAD_MB`, PDF 10 MB, text 1 MB. Polyglots are
refused: more than 16 bytes after an image's end marker, foreign signatures (ZIP, RAR, 7z,
PE, ELF) anywhere in the body, HTML/script/SVG markup; PDFs with JavaScript, actions, forms,
launch or embedded-file keys, including hex-escaped names (`/J#61vaScript`) and keys hidden in
Flate-compressed object streams (inflated under a 64 MB budget). Links (`/URI`) are allowed
because real certificates carry verification links. Images are decoded under a 40 MP budget
and re-encoded into a fresh image, so EXIF/GPS/ICC/comments never survive. Stored files are
mode 0640 in a 0750 directory owned by the API user (uid/gid 10001); Nginx joins group 10001
(`group_add`) to serve them from its `internal` location. The signed blob endpoint answers with
`X-Accel-Redirect`, `Content-Disposition: attachment` and `Cache-Control: private, no-store`;
Nginx adds `nosniff`, a sandbox CSP, CORP same-origin and no-referrer.

**D32 · Who may download a file.** `GET /files/{id}/download` is public in the API contract
because visitors of a public profile load its portfolio images. Authorization happens in the
`file_access` definer: owner, admins, SYSTEM, or — for portfolio images only — anyone who may
see the profile (visibility rules). Certificates and review evidence are owner/admin only.
Everything else is 404. The redirect target is a 5-minute HMAC-signed URL bound to the storage
key, type, name and expiry.

**D33 · Skill-test rules.** 10 random active questions per attempt from ≥ 15 per skill
(seeded shuffle; the seed is stored), 600 s on the server clock, answers rejected after the
deadline (409 `EXPIRED`), one open attempt at a time (409 `IN_PROGRESS` with its id), one
scored attempt per test per 30 days counted from the start of the previous attempt (409
`RETAKE_LOCKED` with `next_attempt_at`), no practice mode. An attempt left open past its
deadline is scored as it stands on the next read or by the `attempts.expire` job (every
minute). Scoring happens inside the database; responses report the score and the number
correct, never which answers were right. A parallel start is serialised with an advisory lock.

**D34 · Question bank v1 needs a human review.** The 128 questions (16 per skill) in
`alembic/seed/skills_and_questions_v1.json` were drafted by the AI assistant from
`scripts/build_question_bank.py` (answer positions balanced by a seeded shuffle, asserted by a
test). They are plausible but have not been checked by a subject expert; the hand-off asks a
team member to review them before the demo. Corrections go into a new seed version, not edits
to v1.

**D35 · Verification is admin-only, also in the database.** Owners may edit and delete their
certificates and external reviews, but a trigger (`guard_verification`) refuses any change to
`status`, `reviewed_by`, `reviewed_at` or `reason` unless the caller is an admin or SYSTEM, and
new rows must start PENDING. A second trigger makes a stored file's identity (owner, key, type,
size, hash, name) immutable. The taxonomy tables `skills` and `skill_tests` are RLS-exempt
(public catalogue) and read-only for the runtime roles.

**D36 · `is_system()` inside definer functions.** `is_system()` checks `current_user`, which
inside a SECURITY DEFINER function is the function's owner, so it is always false there. The
Phase 3 definers use `caller_is_system()`, which checks `session_user = 'devsync_worker'`
(the login role, unchanged by SET ROLE) together with the SYSTEM context. A test proves the web
role claiming SYSTEM still cannot score someone else's attempt, while the worker can.

**D37 · Coverage counts code run in greenlets.** SQLAlchemy's async layer runs the ORM in
greenlets; coverage.py missed lines after an `await` in services (profiles showed 63% though
every path was exercised). `concurrency = ["greenlet", "thread"]` fixes the measurement; no
threshold changed.

## 2026-10-19 — Phase 4 (planning; approved by Salwa Baki)

**D38 · Full project/milestone enums created up front.** Migration `0005` defines the complete
`project_status` (DRAFT, BIDDING, FORMING, TEAM_PENDING, IN_PROGRESS, ON_HOLD, REVIEW_WINDOW,
COMPLETED, CANCELLED) and `milestone_status` (PLANNED, FUNDED, ACTIVE, SUBMITTED, APPROVED,
CHANGES_REQUESTED, AUTO_APPROVED, PAID, DISPUTED, REFUNDED) enums from spec §8, even though
Phase 4 only drives DRAFT↔edit, DRAFT→BIDDING, BIDDING→BIDDING (extend) and →CANCELLED. *Reason:*
`ALTER TYPE … ADD VALUE` cannot run inside a transaction and would churn later migrations; the
service still rejects every not-yet-implemented transition via the transition table
(`InvalidStateTransition` → 409 `INVALID_STATE`). *Alt:* add enum values per phase.

**D39 · Simulated payment-method verification.** Spec §8's DRAFT→BIDDING guard needs "payment
method verified". Payments are simulated (spec §0.2 rule 17), so a client marks their method
verified through `POST /me/payment-method/verify` (CLIENT only, idempotent, sets
`users.payment_verified_at`); the wizard's publish step calls it. No real gateway. *Alts
considered:* admin-set only (adds friction to the demo) or seed-only (can't be shown live).
To be sanity-checked with Taeen since the hand-off flagged it; recorded so Phase 4 can proceed.

**D40 · CPM-over-deadline is an acknowledged warning, not a block.** When CPM duration >
`deadline_days`, DRAFT→BIDDING is still allowed if the client acknowledges
(`publish` body `acknowledge_schedule_risk: true`), matching spec §8 ("CPM duration ≤ deadline
**or client acknowledged warning**"). The wizard surfaces the warning in step 6. *Alt:* hard
block (contradicts §8).

**Demo-1 risk rule (confirmed with Salwa; §17.0, hand-off §6).** If Demo 1 is at risk, only skill
tests and recommended projects may move to Demo 2. The **CPM planner and sealed bidding with
Algorithm 1 filtering never move.**

**D41 · Flake fix in a Phase 3 test (`guards.test.tsx`), found re-running the Phase 3 gate on
Salwa's laptop.** The admin area is a separate lazy code-split chunk (§14.17); under coverage
instrumentation on a lower-spec machine (5.6 GB RAM) its dynamic import + `/admin/session` fetch
exceeded React Testing Library's `findBy` **default 1 s** timeout, so the full `vitest run
--coverage` failed one test (`loads the admin area…`) while it passed 3/3 in isolation. Fix:
pass `{ timeout: 10_000 }` to that one `findByRole` (well under the 20 s `testTimeout`); **the
assertion is unchanged** — not a weakened test, a race made robust across machines (spec §16.10,
"find the race; don't add blind retries"). Flagged to Taeen (Phases 0–3 owner). The gate's two
earlier failures this session were environment-only (Trivy cache SIGBUS after the Docker restart;
a stale tmpfs test-Postgres with out-of-date role passwords) and were cleared by re-pulling and
recreating the test stack — no code or security default changed.

**D42 · Flake fix in a Phase 2 E2E test (`home.spec.ts`), same cause as D41.** "the render loop
stops when the hero is off screen" assumed the 3D loop pauses within a fixed 600 ms after the hero
scrolls off-screen; on Salwa's slower laptop the IntersectionObserver pause took longer under CPU
load, so the frame count was still rising when sampled (1/40 E2E flaked). Fix: poll until the
frame count stops rising (the loop has actually paused), then assert it stays paused for 800 ms —
the behaviour under test (loop stops off-screen) is unchanged. Flagged to Taeen.

**D43 · Phase 4 review fixes (Taeen, with Claude Code, before Salwa's merge).** The Phase 4 gate
passed on Taeen's laptop as delivered, but a review against the spec and a new end-to-end test
of the Demo 1 path found these defects, now fixed on `phase-4`:
1. *The wizard could not save its first step.* `useUpdateProject` was bound to the placeholder
   id `"preview"`, so the first PATCH went to `/projects/preview` (422). The draft is now patched
   by its real id; after slot/milestone/dependency replaces (which bump the version) the wizard
   re-reads the version so the Budget step's `If-Match` is current.
2. *Publishing was impossible from the UI.* Publishing needs a verified payment method (D39),
   but nothing in the UI verified it. `GET /me` now returns `payment_verified`, and the Review
   step offers "Verify payment method" (simulated, one click); Publish stays disabled until then.
3. *A circular dependency could not be shown* (Demo 1 walkthrough): "Must finish after" offered
   only earlier milestones. It now offers every other milestone; a loop shows the alert and
   blocks Continue, and the server still rejects it.
4. *The plan page's dependency graph had no edges*: it called `GET /projects/{id}/dependencies`,
   which the spec doesn't define (405). `GET /projects/{id}/plan` now includes `edges`
   (spec §10: the plan is the read path); unused GET hooks for slots/milestones were removed.
5. Spec items that were missing: the unsaved-changes prompt on the wizard (screen 21) and typing
   the project title to cancel (§17 Phase 4).
6. Polish found by the new checks: touch targets ≥ 44 px on touch screens (segmented control,
   tag chips, remove buttons, toast close), the shared Select's runtime `<style>` now carries the
   CSP nonce (a latent Phase 2 bug first exercised here), "A · B" meta strings replaced, and the
   test fixture's §18.2 Frontend row corrected to the spec (ES 4, EF 13, LS 8, LF 17).
7. Tests added: `e2e/phase4.spec.ts` (the spec's Phase 4 E2E: §18.2 plan via the wizard,
   critical path and slack, loop rejected, payment verification, publish, cancel a draft, leave
   prompt; plus CSP/axe/layout on the wizard's milestones step and the plan page), visual
   baselines for My projects, Create project and the plan page, and unit/API assertions for
   each fix. *Lesson:* mocked frontend tests can't catch a wrong URL or a missing endpoint; the
   spec's E2E for each phase is not optional.

## 2026-10-20 — Phase 5 (marketplace, sealed bidding, Algorithm 1 filtering; Salwa with Claude Code)

**D44 · Fixed reputation snapshots in Phase 5.** Experienced developers get hand-set snapshot
values (`scripts/seed_data/stage1_reputation.json`, §18.4); only `newcomer_snapshot()` is computed.
The seed recomputes `C` (Eq. 4) and `P` (Eq. 12) from the stored sub-scores and asserts them so the
table can't drift. The single read path is `services/reputation_read.py`, so Phase 6 swaps computed
values in without touching filtering.

**D45 · Eligibility dry-run endpoint.** `POST /projects/{id}/bids/eligibility` (developer, not
persisted) returns per-constraint pass/fail + the would-be reason for the bid sheet's live preview.
Not in the §10 table; added for screen 11. *Confirmed by Salwa.*

**D46 · Shortlist size.** Per-slot `K_s = max(shortlist_factor·count_s, shortlist_min)` (default
3/6, §9.2) — the algorithm text, which is what the Phase 7 PSO consumes — rather than the §6.2
"max(3·N, 20)" phrasing. *Confirmed by Salwa.*

**D47 · Too-few-bids actions in Phase 5.** The banner's "lower standards" stores client P0/C0
overrides and "reduce team" edits slots while BIDDING; both reflect immediately in the eligibility
counts. Formation (Phase 7) consumes them. Extend/cancel reuse the Phase 4 endpoints.
*Correction (Taeen, 2026-10-22):* when the phase was first merged only extend/cancel existed (the
banner offered a link); the stored overrides, reduce team and raise budget arrived with the
follow-ups in D54, which is where their rules are recorded.

**D48 · "Seeded" reputation marker.** `reputation_read` returns `seeded = (settings_version is
None)`; the bid table and profile show the marker only outside production. Phase 6 sets
`settings_version` when it computes a snapshot, flipping the flag off.

**D49 · One ACTIVE bid per developer via a partial unique index.** A plain `UNIQUE(project,
developer)` (§7.4) conflicts with the `WITHDRAWN` state and re-bidding (the B2 churn check, §9.15),
so `bids` uses `UNIQUE(project_id, developer_id) WHERE status='ACTIVE'`: a withdrawn row is kept and
a fresh bid can be placed.

**D50 · Eligibility is computed in a SYSTEM session.** Algorithm 1 reads each bidder's skills,
skill evidence and reputation, which neither the project's client nor a plain web user may read
under RLS. The client-bids view and the bidding-deadline job evaluate eligibility in a SYSTEM
session; migration 0006 adds minimal, additive SYSTEM policies (read on bids/reservations/snapshots/
developer_skills/skill_evidence/developer_profiles/users; INSERT on skill_evidence; UPDATE on
projects for the BIDDING→FORMING transition). The Phase 3/4 owner policies are unchanged; RLS is
permissive, so these only widen the SYSTEM role. The caller is authorised as the project owner first
and only the eligibility verdict — never raw developer data — is returned.

**D51 · Security fixes may skip the 14-day dependency age rule (Taeen, Phase 5 gate).** The
first Phase 5 gate run found newly published vulnerabilities: Pillow 12.3.0 (8 CVEs, fixed in
13.0.0, released 2026-10-16) and certifi 2026.7.22 (fixed in 2026.10.19). Spec §14.21 requires
critical fixes within 48 hours and high within 7 days, which outranks our 14-day supply-chain
precaution (D1). Only these two packages were upgraded (`uv pip compile --upgrade-package`; every
other pin unchanged). Pillow 13 is a major version: the upload pipeline's tests (100% coverage,
EXIF/GPS stripping, bomb guard, polyglots) pass unchanged. *Rule from now on:* a package may be
newer than 14 days only to fix a published vulnerability, recorded here with the CVE source. *2026-10-22:* `opentelemetry-api` 1.45.0 → 1.45.1 (CVE-2026-114603, published
that day; found by the gate's pip-audit) under the same exception, only that package re-resolved
(`uv pip compile … --upgrade-package opentelemetry-api==1.45.1`). *2026-10-24:* `filelock` 4.0.8 → 4.2.1
(dev/test only, via schemathesis; CVE-2026-112907, CVE-2026-112913, CVE-2026-112940, found by the
gate's pip-audit; 4.2.1 released 2026-10-17) under the same exception, only that package
re-resolved.

**D52 · Phase 5 gate fixes (Taeen, before review fixes).**
1. `/projects/{project_id}` (GET/PATCH/DELETE) uses Starlette's `uuid` path convertor, so the
   spec's static paths `/projects/search` and `/projects/recommended` are never shadowed (an
   unsupported method on them now answers 405, not a CSRF 403). The OpenAPI paths are unchanged.
2. Query contracts declare what the server enforces: page cursors `min_length=1, max_length=200`;
   `/public/projects` bounds `q` (≤ 200) and `limit` (1–100) like the signed-in search; `sort` is
   an enum (`newest | budget | deadline`).
3. Contract fuzzing: a fuzzed page cursor (an opaque server-issued token the fuzzer can't
   produce) may get a 422 that names `cursor`; any other response to such a request, and every
   request without a cursor, is validated in full (no check is switched off).
4. The partial unique index `one_active_bid_per_developer` keeps its constant `text()` predicate
   with a reviewed `forbidden-ok` marker (DDL, no input); the advancement sort key keeps prices
   as integer paisa (no `float`, spec §0.2 rule 10); one line formatted.

**D53 · First cross-browser E2E run (Phase 5 is the first demo phase: chromium, firefox, webkit,
mobile).** Chromium passed everything; the other engines exposed issues never tested before.
*App fixes:* touch targets on Find Projects (title links, recommended buttons) and My Bids
("View project"); the Find Projects search field is "Search projects" (it shared the accessible
name "Search" with the header's command-palette button); sign-out now clears the session only
after the navigation home has finished (slower engines still lost the D43 race and landed on
/login). *Test fixes (behaviour by design, now tested per viewport instead of desktop-only):*
phones load the 3D scene on the first interaction (D26), use the bottom tab bar + "More" sheet
instead of the sidebar, and put the homepage header links in the menu sheet; `mainNav()` and the
header checks choose by viewport width (never an instantaneous visibility check). *3D on
non-reference engines:* in the test container Firefox has no WebGL and WebKit only software
WebGL, so the hero correctly shows its poster (or never finishes compiling). Chromium remains the
reference engine and must reach the live scene; on the others the test verifies the poster
fallback and skips only the live-scene part, with the reason in the report (real devices use the
GPU; the 60 fps check runs on the laptop GPU, D28). On phones the LCP element may be the hero's
lead paragraph rather than the headline (both hero text, never the canvas); desktops still
require the headline. *Also found by this run:* (1) after registering, the automatic sign-in sent no CAPTCHA,
so a person on a shared IP with ≥ 3 recent failed sign-ins (an office or campus NAT; in the E2E
container, another browser's throttling test) got "complete the verification check" although
the account existed — the follow-up sign-in now solves the check and retries when the server
answers `captcha_required`, like the login page (unit-tested, incl. no retry on other errors).
(2) Sign-out ends with a full page load of "/" (`location.replace`), not an in-app
navigation. React Router reports a navigation done before React commits it, so clearing the
signed-in data afterwards let the page being left (its guard) send WebKit users to /login; a
fresh load also drops every cached piece of the person's data. It happens even when the
sign-out request fails, so a stale session is never left on screen. (3) The plain hero headline has a space before each `<br>`, so its accessible name is
"project. Hire…" in every engine (WebKit/Firefox joined the sentences). (4) `GET /auth/csrf` echoes the
token in an `X-CSRF-Token` header: in WebKit `document.cookie` can show a cookie set by a `fetch`
response only a moment later, so the next POST sometimes went out with an empty header
(`csrf_rejected` in the gate's API log). The client prefers the echoed token and shares one
fetch between concurrent callers; the server check (cookie = header, signature, Origin) is
unchanged. (5) The clients-only profile E2E waits for every card to finish loading before
clicking the visibility radio (a card arriving mid-click moved the radio and the click was lost;
the trace showed no PATCH), and asserts the radio is checked before waiting for "Saved".
That alone was not enough: the app scrolls smoothly (`scroll-behavior: smooth`, kept for users
and the homepage anchors), so in Firefox and WebKit the scroll Playwright starts to bring an
element into view was still animating when it clicked, and the click landed where the element
used to be (profile radio, footer links; traces show "not stable" / "outside of the viewport"
right before the click). The shared fixture (e2e/test.ts) turns scroll animation off on every
test page (inline `scroll-behavior: auto`, re-applied after parsing because WebKit has no
<html> yet and Firefox replaces it); nothing asserts on scroll motion. The homepage link tests
also request reduced motion: in the container WebKit renders WebGL in software and the 3D
shader compile blocked the page for ~8 s, swallowing clicks; the 3D hero has its own tests.
Follow-up for the user (not done, changes §13.12 fallbacks): also show the poster when WebGL
would render in software (`failIfMajorPerformanceCaveat`), which would move the live-scene
E2E check to the GPU project. 48/48 repeated runs on three engines. (7) Search input: schemathesis
sent `q=\x00…` to `GET /public/projects` and got a 500 (PostgreSQL rejects NUL in text).
`services/marketplace.search` now cleans `q` and each skill name like profile one-line fields
(control characters removed, NFC, trimmed, empties dropped) and allows at most 20 skill filters
(422 `skills: too_many`). (6) gitleaks scans the working tree
(`--no-git`), so after any failed E2E run the next gate failed step 5 on Playwright traces in
`frontend/test-results/` (115 `generic-api-key` hits, all session cookies of the throwaway test
stack). That folder and `frontend/playwright-report/` are gitignored generated output, so they
join the allowlist next to `frontend/dist/`, `frontend/coverage/` and `runs/`; tracked files are
scanned exactly as before.

**D54 · Phase 5 follow-ups (Taeen, 2026-10-22, after an external review of Phase 5).**
*Bidding closes by time.* Placing, editing, withdrawing and previewing a bid also require
`now < bidding_deadline` (409 `INVALID_STATE`), so a late deadline job can't let late bids in;
search, the public list and recommendations hide projects past their deadline, and project cards
carry a server-computed `open_for_bids`. Extending after the deadline counts from now.
*Bids reference only the bidder's own portfolio items* (422 otherwise, duplicates refused).
*Too-few-bids actions (§9.19).* `POST /projects/{id}/bidding-terms/preview` re-runs Algorithm 1
under proposed terms without saving; `PATCH /projects/{id}/bidding-terms` applies them. Rules:
standards per project (`projects.min_performance/min_competency`, NULL = platform default) within
[default − relax_max_steps·relax_step, default] — P 30–45, C 25–40 by default — so a client
can't switch the filter off (automatic relaxation still runs on top, as §9.2 says); the budget
only goes up; slot counts only go down (≥ 1 per slot, ≥ 2 per team); at least one value must
change; If-Match; audited with before/after; every active bidder is notified (SYSTEM session,
like D50); when bidding already closed and the team is now covered the project moves to FORMING
at once. Once bids exist these actions plus extend/cancel are the only ways to change budget,
standards or team (the project is otherwise not editable after publishing, §8). Cancelling a
bidding project notifies the bidders; the deadline job's too-few notification names the
shortfall per slot. *A shortfall left alone* (the spec says what to offer, not when to stop): one
reminder 7 days after bidding closed, and the project closes on its own after 14 days
(CANCELLED, free before a team forms; client and bidders told; audited as SYSTEM). The Bids page
shows that date in the too-few banner from the start, so it is never a surprise.
*Replication mode relaxes like the paper.* [PCS] Algorithm 1 lines 3–5 re-initialize P0/C0 only
when S' is empty, so `pcs_replication` relaxes only while no bid qualifies (devsync keeps
relaxing while any slot is short); the 0.05 step stays the documented default (A-list).
*Explanations.* `explain_bid()` (pure) returns every Algorithm 1 check with required and actual
values in precedence order; the client's bids view shows it per bid ("How the filter decided"),
plus the thresholds used after relaxation, the cheapest eligible team against the budget after
fee (`cheapest_team_cost()`, pure, verified by brute force in property tests), hours a week,
teamwork, proposal, contribution, portfolio titles and the newcomer evidence ("React test 85%").
Eligibility is evaluated **live** when the client opens the view (reputation as of now, shown as
"Eligibility checked …"); Phase 7 formation snapshots the candidate set it uses. The developer's
dry-run preview never ranks against other bids (no NOT_SHORTLISTED; tested).
*Performance.* Bidder data (skills, evidence, hours, reservations) is read in batches: a project
with 200 bids is evaluated with a fixed number of queries (≤ 25) in < 2 s (`tests/perf`).
*Search.* Keyset pagination on (sort key, id) for every sort (a cursor names its sort; another
sort's cursor is 422); text search also matches the slots' skill names.
*Recommendations (§9.16).* A project is recommended when it needs one of the developer's skills
with a deadline ≥ their typical days for that skill (median of their past bids; any deadline
without history) and its period fits their free hours; ranked by matching skills then newest;
cached 5 minutes per developer (fails open) and forgotten when they bid or withdraw.
*Sign-in with reserved domains.* Login and forgot-password look an address up with a syntax-only
`LookupEmail` (lower-cased; emails are citext): strict `EmailStr` refused `.local`, which locked
the seeded demo accounts (`@devsync.local`, §18.4) out of the login form. Registration keeps
`EmailStr`. `make demo-preflight` now signs in as the demo client.
*Homepage hero on software WebGL.* The poster is shown when WebGL would run without a GPU
(`failIfMajorPerformanceCaveat` or a software renderer name such as SwiftShader/llvmpipe): a
software shader compile froze the page for seconds. In the gate's step 13 Chromium renders WebGL
with SwiftShader, so its hero (correctly) shows the poster there; the live-scene tests are tagged
`@gpu` and run on `chromium-gpu` with the real GPU in step 16 next to the frame-rate check (the
gate now quotes Playwright arguments with `shlex.join`). The headline must be the LCP element on Chromium (the
engine Lighthouse uses); WebKit's LCP can name the hero's lead paragraph once the headline is
swapped in after its reveal, so other engines accept either hero text block (never the canvas).
The gate keeps a failed E2E pass's screenshots and traces in `runs/gates/e2e-failures/`. WebKit in the container renders
WebGL in software but reports "Apple GPU", so its hero starts the live scene and the compile once
froze a page past a full test run's timeout; on WebKit the `@gpu` tests therefore start with
reduced motion (poster, headline and LCP still checked), Chromium (software WebGL detected) and
Firefox (no WebGL) fall back on their own, and the live scene is checked on `chromium-gpu`.
*No upstream keepalive in nginx.* Gunicorn recycles each worker after ~1,000 requests; a POST sent
on a kept-alive connection the exiting worker had just closed came back as a 502 (nginx rightly
won't retry a POST). nginx now opens a fresh local connection per API request.
*E2E fixtures.* Test-only routes (DEVSYNC_ENV=test only) close a project's bidding, give a
developer a skill with test evidence and set a reputation snapshot, for the newcomer, relaxation
and closed-bidding walkthroughs. The bid sheet also takes hours a week, expected contribution and
up to three of the developer's own portfolio items (§13.5 #11).
*Known limitations (documented, not changed):* TOO_SLOW compares a bid with the whole-project
deadline, not the milestones the slot works on (the paper's simplification; future work);
availability is checked at bidding and must be re-checked when invitations are accepted (Phase 8);
the SYSTEM sessions of D50 stay limited to the listed read policies and are used only after the
caller is confirmed as the project's owner.


**D55 · Reopening a draft in the create-project wizard (Taeen, 2026-10-23, found in manual testing).**
The wizard saved every step to a DRAFT (§13.5 #21 "Draft autosaves") but kept the draft id only in
memory, so leaving and coming back started an empty wizard, and My projects offered a draft only
"View plan" and "Cancel". Now the address carries the draft and the step
(`/client/projects/new?draft=<id>&step=N`); a reload, the browser's back button or "Continue
editing" in My projects reopens it at that step (never past the first step that still needs input),
and a plain visit to `/client/projects/new` starts a new project. The wizard loads the draft from a
new read, `GET /projects/{id}/draft` (project + slots + milestones with shares and skills +
dependencies), under `project.write`: only the owning client (others, admins included, get 404 or
403), only while the project is a DRAFT (409 otherwise). The sidebar now marks only the most
specific matching item, so "Create project" no longer also lights up "My projects".

**D56 · Fixes from the Phase 0–5 logic audit (Taeen, 2026-10-24).**
A read-through of every non-visual flow (accounts, projects, bidding, profiles, client caching)
found these, each now covered by a test that failed before the fix:
*Sessions.* Signing out (one device or all), a password reset or an ended session now also
replace the CSRF cookie with an anonymous one, and the client fetches a fresh token and retries
once after `CSRF_FAILED` — a stale token blocked every later sign-in until the browser closed.
Routine rotation happens once per token (a Redis lock), the old token's 30 s grace entry no longer
asks to rotate again and is never extended, and ending a session deletes every token it had in
grace (`sesstok:<session>`), so "sign out of every device" and password changes end them all. The
device list hides sessions past their idle timeout.
*Projects.* A bidding close time must be in the future when saved and at publish; publish also
needs a budget and slot counts equal to the team size (422s, not database 500s); a malformed plan
preview is a 422. The deadline job notifies once per closing (read or not) and again after an
extension; cancellations and terms changes notify every bidder each time. A draft reopened on
Review re-runs the schedule check. The plan's Finish date is the last working day.
*Bidding.* Bids can be edited (the API existed; the UI didn't call it). Recommendations refresh
after a bid, edit or withdrawal. A racing second bid is a 409. No "minimums relaxed" without bids.
The dry run says "may be filtered out" for minimums that relaxation can still lift.
*Profiles and tests.* Autosave compares values as the server stores them (it saved forever after
editing hours or leaving a trailing space), saves a pending edit when the page is left, and adopts
changes made elsewhere. The test countdown uses the clock offset measured when the attempt arrived
(a cached attempt showed the time spent away as extra time). Public profiles show each skill's best
verified score, as bidding uses it (migration 0008). Review dates compare Dhaka calendar dates.
*Client.* A sign-in drops every cached query of the previous user; a failed `/me` shows an error
with retry instead of the sign-in page.

**D57 · Fixes from the second logic audit (Taeen, 2026-10-24).**
*Public projects.* `/projects` was still the Phase 2 placeholder (always "no projects"); it now
lists `GET /public/projects` with search and "Load more", and `/p/:id` shows one project (public
columns only) with "Sign in to bid" returning to the bid sheet.
*Jobs.* The email job claims a batch (lease + attempt counted) and commits before SMTP, then
records each result on its own — no transaction stays open across SMTP, so a slow server can't
get the same emails resent every run and the retry limit always applies. The deadline job handles
one project per transaction, row locked and re-checked (SKIP LOCKED); every project write locks
the row too, so a cancel or extension can't be overwritten. Moving to FORMING bumps the version.
The reminder's date is in Dhaka time.
*Validation.* Messages lose Pydantic's "Value error, " prefix. PATCH /projects refuses null for
required fields and a close time without a time zone (422, not 500). Phones: "+880"+"01…" and
"01…" mean +8801…, and Bangladeshi numbers must be mobiles (both sides). The wizard and bid sheet
check every number with the server's limits and show the server's field errors next to the
field; text limits count code points after NFC like the server; URL and GitHub rules equal the
server's regexes; ratings have at most 2 decimals; password minimums ignore end spaces; reset and
change password show the server's reason. Share totals keep one decimal.
*Today's changes.* Browser back/forward into a draft reopens it; a bid edit drops deleted
portfolio items; a request losing the rotation lock doesn't refresh the old token.

**D58 · Reputation summary on developer profiles (Taeen, 2026-10-24; spec §13.5 #7/#9, §17 Phase 5).**
`GET /developers/{id}` and `GET /public/developers/{id}` add `reputation = {competency,
performance, is_newcomer, seeded}` (C/P as 3-place decimal strings on 0–1). It is read through
`reputation_read.read_stored()` in the caller's own session, only after the profile itself proved
visible — no SYSTEM session (D50's stay limited to project owners). Reputation snapshots are
readable only when signed in (migration 0006), so anonymous visitors get `reputation: null` and
the page invites them to sign in, rather than a misleading "newcomer". A developer with no stored
snapshot gets null C/P ("Building a record") and `is_newcomer: true`; the on-the-fly newcomer
prior used by filtering is not shown, as it would need other users' private data. `seeded`
(D48) is forced false when `DEVSYNC_ENV=production`.

**D59 · Project details and the role / hours filters (Taeen, 2026-10-24; spec §10, §13.5 #11–12, FR-MKT-2/4).**
`GET /public/projects/{id}` adds the description, start date, the milestones (name, duration,
state) and a CPM schedule with edges. The schedule is computed from the milestones and
dependencies (readable for published projects), not from `plan_baselines` (owner/admin only, and
it stores no edges), and is empty until a baseline exists. The client's organisation, else
display name, is returned to signed-in callers only (guests get null). It is read in a SYSTEM
session limited to those two columns, after the caller's own session has found the project (D50
precedent). Never any bid data. `/projects/search` adds `role` (a slot skill name, matched
case-insensitively, ≤80 chars; combines with `skills`, which still means "any of these") and
`hours` (1–168, the hours a week the developer can commit). A project is kept when that
commitment fits next to their confirmed reservations over the project's period (start date, else
today, plus deadline days) within their profile hours (20 without a profile row): the §9.17 check
of `algorithms/availability.py` that recommendations use. More than the profile's hours returns
an empty page. The hours filter runs after each SQL page and reads at most 5 pages to fill one;
the cursor continues after the last project examined, so a page can be short with a next cursor
(the UI offers "Search further"). The developer's role list puts their own skills first and warns
when a role would be filtered out, rather than hiding the other roles.

**D60 · Fee, bonus pool and budget shares in the planning screens (Taeen, 2026-10-24; spec §6.2, §13.5 #21–22).**
The plan preview returns `platform_fee_bp` and `bonus_pool_bp` from `pay.*`, and each CPM node
carries an optional `share_bp` (preview, plan, dependency replace). The wizard's Budget step
takes the bonus pool as a switch plus a percentage (0–50 %, one decimal, suggested from
`pay.bonus_pool_bp`) and stores `round_half_up(budget × pct / 100)` paisa. A "Where the money goes"
box shows the fee (rounded so the team share is rounded down, like `services/bids.py`), in integer
paisa (`lib/money.ts`, BigInt). The Review step shows the plan (Gantt or table) and blocks
publishing on a cycle or shares ≠ 100 % (the server already refused both). The Gantt gains a
Months zoom (auto for plans over 180 days); the dependency graph opens a milestone panel.

**D61 · Demo 1 stack, texts, passwords and walkthrough (Taeen, 2026-10-24; spec §18, D3, D5).**
`make demo-up` = base + prod + `docker-compose.demo.yml`: production settings and validation,
2 API replicas × 2 Gunicorn workers (laptop memory and the Postgres connection limit, D5),
2 workers, the scheduler and Mailpit. It shares the `devsync` project, so `make demo-reset` wipes
development data; demo one-off containers run with `--no-deps`. `make up` is unchanged. Texts on
the demo stack use `SMS_PROVIDER=mailpit`: each arrives in Mailpit as an email to
`<digits>@sms.devsync.local`. Production validation allows this only with `SMTP_HOST=mailpit` and
the sender checks again, so one-time codes cannot reach a real relay; `console` stays
development-only. Demo passwords are random per account on every seed, written once to
`runs/demos/accounts-N.txt` (gitignored, 0600); `DEMO_PASSWORD` (12+ chars) sets one for
rehearsals, and `make demo-check` generates its own and passes it by name only. A test-only route
`GET /__test__/attempts/{id}/answer-key` (DEVSYNC_ENV=test only, like the whole test router) lets
the walkthrough pass a timed test through the UI. `make demo-preflight` verifies the edge
certificate against the system store plus the mkcert root: FAIL when mkcert is installed and the
certificate is untrusted, WARN (self-signed, D3) when it isn't.

**D62 · Hardening before Demo 1 (Taeen, 2026-10-26; spec §14.12, §14.17, §14.18, §10.1).**
*(a) Mailpit in production.* Startup refuses Mailpit (`SMTP_HOST=mailpit` or
`SMS_PROVIDER=mailpit`) under `DEVSYNC_ENV=production` unless `DEMO_STACK=1`, which only
`docker-compose.demo.yml` sets and which is honoured only when `PUBLIC_ORIGIN` is localhost,
127.0.0.1 or ::1 — so a copied variable cannot turn on mail capture on a real deployment, and
production must name a real relay. D61's offline demo is unchanged.
*(b)* Startup also refuses auto-reload and debug switches (`--reload*`, `--debug`,
`UVICORN_RELOAD`, `GUNICORN_CMD_ARGS --reload`, debug/trace log levels) and any `/__test__` or
`test_seed` route outside `DEVSYNC_ENV=test`; the worker and scheduler run the same validation.
*(c) `ADMIN_ALLOWED_CIDRS`* is enforced twice: Nginx renders it into a `geo` block at container
start (a bad entry stops Nginx) and the API checks the address it trusts (`X-Forwarded-For` only
from `TRUSTED_PROXY_IPS`, right-most entry). Admin API requests from other networks get the
ordinary JSON 404 with identical headers, before any session or database work. The `/admin` SPA
route is served like any other SPA path, because a different answer would confirm the area
exists. Both lists are validated at startup in every environment; malformed entries, `*` and
networks with host bits set are refused.
*(d) noindex.* Admin pages and all API responses carry `X-Robots-Tag: noindex, nofollow`;
robots.txt no longer names `/admin`.
*(e) Access log.* One structured line per request: method, route template, status, `duration_ms`,
`request_id` and a keyed 16-hex hash of the user id. Raw paths, query strings, headers and bodies
are never logged.
*(f)* API paths with a trailing slash get a relative 308 to the canonical path (query kept);
suspicious paths are never redirected and Starlette's absolute 307 slash redirect is off.
*(g)* Base images are pinned by digest to the versions already in use, each at least 14 days old
(D51); the builds still run `apt-get upgrade`, so security fixes still apply.
*(h)* mypy strict now covers every `app.services.auth` module.

**D63 · Abuse-control caps are constants, not settings (Taeen, 2026-10-26; spec §14.8).**
§14.8 names "maximum open bids per developer (30)" and "maximum active projects per client (20)"
but §6.2 has no key for either, so they live as `services/bids.MAX_OPEN_BIDS` and
`services/projects.MAX_ACTIVE_PROJECTS` rather than inventing settings keys. Both are counted
inside the writing transaction under a per-user advisory lock (`app/db/locks.py`), so two
requests at once cannot both pass; exceeding either is 409 `LIMIT_REACHED` with the number in the
message. "Active" projects are BIDDING, FORMING, TEAM_PENDING, IN_PROGRESS, ON_HOLD and
REVIEW_WINDOW; drafts are bounded by the 10/day create limit instead. Withdrawn and ineligible
bids do not count as open.

**D64 · Bids carry a recorded verdict once bidding closes (Taeen, 2026-10-26; spec §8).**
While bidding is open, eligibility is only ever evaluated live (the client's view, the
developer's dry run). When the deadline job closes bidding — or a terms change re-evaluates
afterwards — Algorithm 1's verdict is written onto the standing bids: filtered out → `INELIGIBLE`
with the reason code, otherwise `ACTIVE`, with `evaluated_at`. Shortlist rank is never recorded
on a bid (it would leak other sealed bids). Extending bidding sets every INELIGIBLE bid back to
ACTIVE, clears its reasons and tells the bidder, so the bid can be improved. Because an
INELIGIBLE bid can become ACTIVE again, the partial unique index becomes
`one_standing_bid_per_developer` over `status IN ('ACTIVE','INELIGIBLE')` (migration 0009);
WITHDRAWN rows are still kept (D49).

**D65 · Developers see reasons in plain language, clients see the trace (Taeen, 2026-10-26; spec §13.5 #12).**
The bidder's `BidOut.reasons` maps each stored Algorithm 1 code to a sentence plus a hint; a code
the server doesn't recognise is dropped rather than echoed. The client keeps the per-check trace
of D54. The bid detail page `/dev/bids/:id` shows the bid, its project, the status timeline,
those reasons and — while bidding is open — the same dry run the bid sheet uses, never a ranking
against other bids. Another user's bid is 404 from the server.

**D66 · Optimistic concurrency and paging (Taeen, 2026-10-26; spec §10.1).**
Bids, whole-set plan replaces (`slots`, `milestones`, `dependencies`) and both profile PATCHes
take `If-Match`; a mismatch is 409 `VERSION_CONFLICT` (the spec's code, not 412) and nothing is
written, the row being locked for the check-and-write. A replace's body is a list, so the new
version comes back in an `X-Version` header that the wizard chains into the next save instead of
re-reading the project. Profiles get their own `version` column (migration 0010); a profile never
saved reports version 0, so the first save sends `If-Match: 0`, and the row is created with
`ON CONFLICT DO NOTHING` + `FOR UPDATE` so two first saves race safely. The client serialises
autosaves and, on a 409, re-reads and offers "Reload" rather than overwriting another tab.
`GET /me/bids` and `GET /projects` are cursor pages (`{items, next_cursor}`, keyset on
`(created_at, id)`, limit ≤ 100); a cursor minted for another list is 422. Both lists offer
"Load more", and the client dashboard reads one page of 100 and shows its counts as lower bounds
("3+") when older projects exist.

**D67 · New-bid notices and the daily digest (Taeen, 2026-10-26; spec §11, §12).**
`bids.new_notices` runs hourly and writes one in-app notice per project covering the bids placed
since that project's last notice; the notice's own `created_at` is the watermark and bids newer
than one minute wait for the next run, so a bid still committing is never skipped.
`bids.daily_digest` runs at 08:00 Asia/Dhaka and emails each client a summary of the previous
Dhaka calendar day; the outbox payload carries that date, so a retry or a second scheduler cannot
send it twice. The bidding-deadline job emails "bidding closed" and "too few bids" (with the
per-slot shortfall) in the same transaction as the in-app notice, and tells each newly-ineligible
bidder once per closing. Suspended or deleted accounts receive nothing.

**D68 · CAPTCHA difficulty and the remaining literals come from settings (Taeen, 2026-10-26; spec §6.2, §14.16).**
`captcha.max_number` (settings v4, default 50 000, bounded 1 000–1 000 000 so a mistake can
neither switch the check off nor freeze slow phones) replaces the hard-coded ALTCHA difficulty;
`DEVSYNC_ENV=test` still forces the minimal difficulty. CAPTCHA now also guards the OTP send and
the email-verification resend (§14.16). `bidding.min_bids_factor` drives Algorithm 1's "enough
bids" test — `required_bids(places, factor) = max(places, ceil(factor × places))` in `Decimal`, so
1.1 × 10 is exactly 11 — for `too_few`, the shortfall and the relaxation loop. The newcomer
starting values take `rep.f_default`, `rep.g`, `rep.gamma0_*` and `rep.neutral` from the active
settings through a pure `NewcomerParams`, so `algorithms/` stays pure; the demo seed uses the
same values instead of its own copies.

**D69 · Request bodies, job runs, review edits and nav prefetch (Taeen, 2026-10-26; spec §10.1, §7.8, §11, §10.2, §13.7).**
*(a)* `JsonBodyMiddleware` is the single place enforcing "JSON only": a non-empty body on
`/api/v1` that is not `application/json` (UTF-8) is 415; multipart is accepted only on POSTs to
the upload endpoints. Nesting deeper than 20 levels is 422, decided by a linear byte scan
**before** parsing, so a deep body never reaches the recursive parser; `NaN`/`Infinity` are 422.
Requests to a path or method no route serves pass through untouched, so unknown routes stay 404
and unsupported methods 405.
*(b)* Two new 401 codes, `SESSION_EXPIRED` and `ACCOUNT_SUSPENDED`, are returned only when the
request carried a session cookie that no longer signs anyone in; anonymous requests keep the
uniform `UNAUTHENTICATED`, and a DELETED account reads as expired so deletion isn't disclosed.
Login refuses a suspended account only after the correct password (no enumeration). The client
drops cached data and goes to `/login?return_to=…&reason=…`, rendering only the two known
reasons; any 503 opens `/maintenance`, whose "Try again" reloads the validated `return_to`.
*(c)* `jobs.run_recorded()` writes a RUNNING row before a §11 job and SUCCEEDED/FAILED after it,
each in its own SYSTEM transaction; `error_code` stores the exception's class name only, never
its message. A crash leaves a RUNNING row that `lifecycle.expire` closes as FAILED/`ABANDONED`
after an hour and prunes after 7 days (system runs only). Migration 0010 adds the missing
SYSTEM-only DELETE policy and an index on `(type, created_at)`. The Phase 0 `ping` heartbeat is
deliberately not recorded: it is not a §11 job and must work without the database.
*(d)* `PATCH /me/external-reviews/{id}` changes `source`, `rating`+`scale` and `project_date`
while the review is PENDING; a verified or rejected one is 409 `INVALID_STATE` with
`allowed_actions: ["delete"]`. The evidence file never changes here.
*(e)* `app/prefetch.ts` holds a null-prototype table of built nav destinations → the module the
router imports, used on hover, focus and touch; each chunk is fetched at most once and a failed
prefetch is forgotten. A test fails if a built destination is missing from the table.

**D70 · The gate confirms the fuzz suite instead of running it twice (Taeen, 2026-10-26; spec §16.5).**
The schemathesis tests carry the `fuzz` marker, which the backend-tests step did not deselect,
so the gate ran its most expensive suite twice. The backend-tests step now deselects it and the
API-contract step runs it once, with its full example budget. Backend coverage without the fuzz
tests is 95.8 % against a floor of 85 %, so nothing is lost by leaving them out of that run. Two
alternatives were rejected: halving the authenticated example budget (20 → 10) to pay for the
second run, which would weaken a test threshold to fit the gate's time budget; and confirming the
first run from its JUnit report, which meant parsing XML in the gate (semgrep's
`use-defused-xml-parse`, and a parser we would rather not add a dependency for).

**D71 · Role assessment replaces generic tests as newcomer evidence (Taeen, 2026-10-28; role assessment spec §3 decisions 1–16).**
`ROLE_ASSESSMENT_BUILD_SPEC.md` wins over the build spec for this feature only. Its sixteen
decisions are adopted as written:
1. Newcomers bid on a role assessment's result; the generic skill tests become **practice**
   (still on profiles, labelled practice).
2. Blueprints are per project slot, rule-based, deterministic and versioned
   (`BLUEPRINT_ALGO_VERSION = 1`), frozen at publish.
3. A pass counts for any slot with the same fingerprint for 180 days.
4. One scored attempt per fingerprint per 30 days, and one open attempt of any kind.
5. Pass ⇔ overall ≥ 60 % and every competency weighing ≥ 20 % scores ≥ 40 %.
6. Difficulty weights are 2/3/4.
7. Navigation is one-way, with one 15-minute timer for 12 questions.
8. Focus mode with the two-leave rule.
9. Terminated attempts count toward the retake limit.
10. A slot whose assessment can't be served falls back to the practice test of its skill.
11. Bids from newcomers without a valid pass are rejected at creation (409
    `ROLE_ASSESSMENT_REQUIRED`), and the evidence is linked to the bid.
12. No LLM at runtime.
13. Bid drafts are kept in `sessionStorage` through an allowlisted helper.
14. The bank is self-verified before Demo 1 and human-reviewed after it (behind
    `assessment.require_human_review`).
15. New questions are never practice questions.
16. Times are stored in UTC and shown in Asia/Dhaka.

**D72 · How the role assessment fits the existing code (Taeen, 2026-10-28; role assessment spec §4–§10, plan `docs/plans/role-assessment.md`).**
- **Migration and grace.** The migration is `0011_role_assessment`; the spec's `0007` example
  was taken.
- **Bind parameters.** Function DDL runs on the raw driver cursor, because SQLAlchemy and psycopg
  would read array slices and plpgsql `%` as parameters.
- **Enum change.** `evidence_source` gains `ROLE_ASSESSMENT` in its own transaction. This is the
  first enum change in the repo, and the downgrade rebuilds the type.
- **Grace period.** The 5 s grace after the deadline applies to role attempts only; practice
  tests keep their own rule.
- **Practice functions and open attempts.** The four practice-test functions now refuse role
  attempts. Without that, `attempt_questions` would have served a role attempt's questions all at
  once and bypassed one-way navigation. Practice starts also take the per-developer lock and
  refuse while any attempt is open (decision 4).
- **Question `slug` column.** Questions gain a `slug` column, the stable YAML id. Migration 0011
  finds the 128 original questions by text and tags them.
- **Duplicate competency codes.** Competency codes are unique across skills, because a blueprint
  mixes skills' competencies and keys them by code. UI/UX `accessibility` became
  `accessible_design` and Node.js `error_handling` became `node_errors`; the names shown are
  unchanged.
- **Bank thresholds.** A competency whose bank has fewer than `min_approved_per_competency`
  approved questions is left out before selection, so a better-stocked one can take its place.
  One that can't supply its difficulties is removed and the weights are redone without
  backfilling (§5.1 step 9).
- **Retired tokens.** The window token is stored hashed. The last ten retired hashes are kept so
  an old window gets `ATTEMPT_MOVED` and a forged token gets `ATTEMPT_TOKEN_INVALID`. The token is
  compared in constant time in Python and again in SQL.
- **Idempotent start.** A repeated `Idempotency-Key` on start resumes the attempt with a fresh
  token. The idempotency record holds only the attempt id, so the token is never stored in plain
  text.
- **Blueprints for older projects.** Projects published before this feature get their slot
  blueprints on first need, in a SYSTEM session, with the same result publishing would have
  given.
- **Voided evidence.** A bid whose linked evidence was voided uses a later valid pass for the same
  blueprint if one exists, so a retake restores the bid. Otherwise it is ineligible with "Role
  assessment voided by an admin".
- **Unverified accounts.** The `assessment.take` policy lets a PENDING developer through, so the
  status endpoint can answer `BLOCKED / ACCOUNT_NOT_VERIFIED` (§8.1) instead of a bare 403.
  Starting needs an ACTIVE account (403 `ACCOUNT_NOT_VERIFIED`).

**D73 · The demo stack gets its own database; the answer key is an operator tool (Taeen, 2026-10-28; role assessment spec §14.1).**
- **Separate demo database.** The answer-key tool must refuse any database whose name doesn't end
  in `_demo`, but the demo stack used `devsync`. The demo overlay therefore runs `devsync_demo` on
  its own volume (`pgdata_demo`), with the name parameterised in compose (`DEVSYNC_DB_NAME`).
  Development and demo data no longer share a database, and the first `make demo-up` after this
  starts empty (it migrates and seeds anyway).
- **How the answer key runs.** `make demo-answer-key USER=…` runs `scripts/demo_answer_key.py` on
  the host. It uses only the standard library, has no HTTP route and isn't imported by the app.
  It reads through the Postgres container as the migrator and passes the password by name, so it
  never appears in a command line. It refuses without `DEVSYNC_DEMO_TOOLS=1`, against a
  non-`_demo` database and inside a container.
- **E2E answer key.** The Playwright container has no database access and no Python, so the E2E
  suite can't spawn the script. On the TEST stack it uses the test-only route
  `/__test__/assessment-attempts/{id}/answer-key`, mounted only when `DEVSYNC_ENV=test`
  (`assert_no_test_routes`). That route calls the same answer-key query the seed helpers use.
- **Seeded attempts are real.** Seeded and test-fixture role results are real attempts, taken
  through the definer functions in the developer's own session (`services/testing/role_attempts`).

**D74 · Question bank verification for Demo 1 (Taeen, 2026-10-28; role assessment spec §13.3).**
- **Writing and checking.** Claude Code wrote the bank: 370 questions over 8 skills, 128 of them
  the original ones, now tagged and explained. 99 code questions have execution checks (Python,
  Node with the app's React 18, PostgreSQL 16) proving the marked option right and each
  distractor wrong.
- **Blind second solve.** Every question was solved again by a separate reviewer that saw only the
  question and options. 354 passed every check and are `APPROVED / SELF_VERIFIED`.
  - One question (`postgresql-sql-queries-03`) stays a draft. Its execution check shows the key is
    right, but the blind reviewer chose another option, and the spec requires agreement.
  - Seven weak original questions stay practice-only. So do seven originals whose labelled
    difficulty was two levels off, because their difficulty can't change while 0004's rows are
    matched as they are.
- **Report and team review.** Results are in `docs/question-review/verification-report.md`. The
  team's human review follows after Demo 1, through `docs/question-review/{skill}.md` and
  `scripts/question_review.py approve`. After it, `assessment.require_human_review` is switched
  on.
- **Lint policy.** The execution checks follow the tests' lint policy (`pyproject.toml`
  per-file rules), since they are test code.

**D75 · Gate fixes found while closing the role assessment branch (Taeen, 2026-10-29).**
- **A documented 413 counts as rejecting invalid data in the fuzz suite.** `POST /client-errors`
  refuses an oversized body before parsing it (as it should), so a body that is both invalid and
  too large gets 413, not 422. Schemathesis's negative-data check doesn't list 413, and failed
  the first time the derandomised fuzzer drew such a body. Only that one check is skipped, and
  only for a 413 response; the status must still be documented, and every other check (no 5xx,
  response schema, headers) applies. Same shape as the existing fuzzed-cursor exception.
- **Profile text is held to its documented maxLength before it is cleaned.** `Line120`,
  `Title`, `SourceName` and `Text2000` stripped control characters first and measured after, so
  a value padded with control characters past the limit was accepted (201) although the schema
  says it is refused (found by the fuzz suite on `POST /me/portfolio`). The raw input is now
  checked first (`string_too_long`, 422); cleaning is unchanged.
- **`make demo-reset` keeps the question bank.** The bank's `reviewed_by_user` foreign key (0011)
  put it in the `TRUNCATE users … CASCADE`, so every demo reset emptied it and the demo seed then
  failed with BLUEPRINT_UNAVAILABLE (the test stack never runs the reset, so the gate didn't see
  it). The reset now holds the bank's rows in memory and puts them back without the reviewer link
  (the migrator may not create temporary tables). A test fails if another table gains a foreign
  key to `users` without being classified as user data or preserved. The demo database's bank,
  already emptied once, was refilled from the test database's migration-seeded rows by skill name
  and competency code.
- **Smooth scrolling is off on every test page**, including pages a test opens in a context of
  its own (`noSmoothScroll` in `e2e/test.ts`, extending D53).
- **Answer cards stack in a flex column** (`Choice.tsx`): in a one-column grid WebKit kept a row
  at its old height after a resize made the text wrap, so a long option spilled out of its card.
- **`dnspython` 2.9.0** for CVE-2026-114605 (transitive, via `email-validator`; only that
  package re-resolved).

**D76 · Developer SMS inbox for demos and development (Taeen, 2026-11-08; not in the original
plan, added on request so a presenter can show the phone-code step without a phone).**
- **What:** `/sandbox/sms` (page) over `GET|DELETE /api/v1/dev-sandbox/sms`. Every text sent
  through `deliver_sms` is also kept in a Redis list (newest 100, six-hour expiry) when
  `Settings.sms_sandbox_enabled`. The page shows the newest code, copy buttons, a number filter,
  live refresh and a link to Mailpit. Email already has Mailpit, so nothing new for email.
- **Where it exists:** development, the test environment, and the offline demo stack
  (`DEVSYNC_ENV=production` **and** `DEMO_STACK=1`, which production validation allows only with
  a localhost origin). In a real deployment the routes are not mounted, nothing is recorded, the
  page says the inbox is off, and `create_app` refuses to start if the router is mounted there.
- **No sign-in:** the first code is read before an account exists. The routes are left out of
  OpenAPI (so the contract check, the fuzzers and the authz matrix never see them) and are
  exempt from the global per-IP limit like the test router, because the page polls every 3 s and
  shares an IP with the demo browser (anonymous limit 60/min). The exemption exists only where
  the routes do.
- **Known limit:** the base compose file publishes Nginx on all interfaces, and the demo stack
  inherits that (only Mailpit is bound to 127.0.0.1). A host-name check (`ALLOWED_HOSTS`) blocks
  casual access by IP, but someone on the same network who forges the `Host` header could read
  demo codes. Demo accounts hold fake data. To close it, bind the demo's ports to 127.0.0.1 in
  `docker-compose.demo.yml`; not done here because it changes how the demo stack is reached.
- **Tests:** unit (code extraction incl. non-ASCII digits, the switch, the guard, capping,
  filtering, a failing Redis never blocks a real send), API (sign-up → inbox → the code verifies
  the account, filter, clear, bad query values), app wiring (absent in production, present on the
  demo stack, exemptions only where mounted), page tests (14) and a four-browser E2E
  (`e2e/sms-sandbox.spec.ts`: axe, CSP, no sideways scroll, the shown code verifies the account).

**D77 · A fuller demo marketplace: a second client and five more open projects (Taeen, 2026-11-08; spec §18.4).**
- **Why:** the stage-1 seed had one client and two open projects, so Find Projects, its filters
  and a guest's public list looked empty.
- **What:** `seed_demo.py` adds Farzana (Studio Nokshi, payment verified) and five BIDDING projects
  (Boutique online store, Clinic appointment portal, Delivery rider tracking, School results
  dashboard, Restaurant website refresh) across all eight skills, each with slots, a valid plan
  (shares sum to 100 %, CPM duration within the deadline) and role-assessment links. They carry no
  bids, so the documented "Online ordering system" numbers (12 bids, 10 eligible) are unchanged.
- **Not added:** completed, in-progress or disputed projects. Those lifecycle states are built in
  Phases 9 to 12 and stage 2 loads them; showing them now would show features that do not exist.
  Guests can browse open projects and public developer profiles only.

**D78 · Quick sign-in tab in the developer sandbox (Taeen, 2026-11-09; extends D76).**
- **Why:** a demo switches between about a dozen seeded people; typing a password each time costs
  minutes. `/sandbox/sms?tab=signin` lists them and signs in with one click.
- **How:** `GET /api/v1/dev-sandbox/accounts` and `POST /api/v1/dev-sandbox/sign-in` sit in the
  same router as the SMS inbox, so they exist only where `sms_sandbox_enabled` (development, test,
  the offline demo stack), are left out of OpenAPI and are refused by `assert_no_sandbox_routes`
  anywhere else. The sign-in starts a normal session through `login.start_session`
  (`services/auth/demo_signin.py`) and is audited as `auth.demo_signin`.
- **Narrow on purpose:** only addresses ending `@devsync.local` (registration cannot create one),
  never an administrator (they keep their TOTP step), never a suspended or deleted account, and
  everything else is a plain 401. The POST still needs the CSRF token and Origin like any other.
- **Known limit (same as D76):** it needs no sign-in, so on a machine whose demo port is reachable
  from a network, someone there could open a demo account (fake data) with a forged `Host`.
  Binding the demo ports to 127.0.0.1 would close it; not done.
- **Tests:** 15 API tests (list, sign-in for both roles, case-insensitive email, admin refused,
  non-demo address refused, malformed and unknown addresses, bad bodies, CSRF, session works) and
  7 page tests (order, one click, refusal, admin note, off, empty, tab switching).


**D79 · Two dependency security fixes (Taeen, 2026-11-19; D51 exception).** The gate's pip-audit
(step 7) found `dnspython` 2.9.0 (CVE-2026-128089, fixed in 2.9.2) and `opentelemetry-api` 1.45.1
(CVE-2026-126360, fixed in 1.45.2). Both were upgraded with
`uv pip compile requirements.in --python-version 3.12 --generate-hashes -o requirements.lock
--upgrade-package dnspython==2.9.2 --upgrade-package opentelemetry-api==1.45.2`; the diff touches
only those two pins and their hashes. Under D51 a package may be newer than 14 days to fix a
published vulnerability. The application code and tests are unchanged.

**D80 · Flake fix in an E2E test: "signing out of every device" (Taeen, 2026-11-19; same kind as D41, D42).**
In a full gate run, the Firefox run of `auth.spec.ts` "signing out of every device ends the other
browser's session" timed out: the screenshot showed the Settings page loaded and the confirmation
dialog not open, so the first click on "Sign out of every device" was lost while the machine was
loaded (the test passed 12 of 12 alone, and 232 of 232 in the earlier full run). The app was not
at fault. The test now clicks again until the dialog is visible (`expect(...).toPass`), then
confirms as before. Nothing was relaxed: the dialog must still open, and the other browser must
still be signed out. Checked 9 of 9 on Chromium, Firefox and WebKit.

**D81 · A NUL character in request text is a 422, not a 500 (Taeen, 2026-11-19; found by the gate's fuzzing).**
Step 11 (Schemathesis, signed in as a client) sent `POST /projects` with the title `"0000\u0000"`.
PostgreSQL cannot store a NUL character in text, so the insert failed and the API answered 500
(`unhandled_exception`). Earlier gate runs did not generate that string, so it was a latent bug.
Two first attempts were wrong and are recorded so they are not repeated: refusing NUL in
`JsonBodyMiddleware` broke `test_control_characters_are_removed_from_text` (profile text is meant to
be cleaned, not refused), and stripping NUL from every field in `StrictRequest` turned the login
email `x\0@y.z` into the valid-looking `x@y.z` (`test_sign_in_still_rejects_malformed_emails`);
silently altering an identifier is the wrong behaviour. The fix is a field validator on
`StrictRequest` (`app/schemas/common.py`) that runs *after* each field's own rules and refuses a
NUL that is still there with a 422 naming the field. Fields that clean their text keep cleaning it,
and an email still fails as malformed, exactly as before. Tests: 16 unit cases (strings, lists,
tuples, dicts, nested models, a field that cleans its own text) and an API test on `POST /projects`.

**D82 · Request fields refuse the wrong JSON type instead of coercing it (Taeen, 2026-11-20; found by the gate's fuzzing).**
Step 11 sent `POST /projects` with `"budget_paisa": false` and `"start_date": 0`; the API answered
201, taking `false` as a budget of 0 and `0` as 1970-01-01 (pydantic's lax mode). The OpenAPI file
says integer and date, so the API accepted input that breaks its own contract.
`StrictRequest` (`app/schemas/common.py`) now has a *before* validator on every field
(`wrong_json_type`): a true/false value is refused where the field is not boolean, and a number is
refused where the field is a date or a date-time (including pydantic's `AwareDatetime`). Everything
else is left to the field's own rules; a field that allows several types, or an unusual annotation,
is not touched. Tests: 48 unit cases in `tests/unit/test_schemas_common.py` (refused, still
accepted, and the helper itself) and an API test on `POST /projects`.
*Same run, second failure, not changed:* `POST /me/external-reviews` (a multipart upload form) was
reported as accepting a "null" `source` and a numeric `file`. In a form every value is text, so
the fuzzer's null arrives as the string "None", which is a valid source name. The case passed
twice when that operation was run on its own, so it is a rare quirk of the fuzzer and not a
change in behaviour; no test was relaxed. If it comes back in a full run, it will be looked at
again before any exception is considered.

## 2026-11-21 — Phase 6 (reputation engine and market simulator; Raisa with Claude Code)

**D83 · Node 22 LTS for the frontend toolchain (backlog P6-0; follows D15).** Node 20 reached end
of life in April 2026. The Nginx build stage now uses `node:22.23.4-bookworm-slim`, pinned by
digest (`sha256:5ec23b7c…`, last rebuilt 2026-11-05, so it meets the 14-day rule; 22.23.5 was
10 days old). CI uses `node-version: "22"`, `package.json` requires `>=22`, and
`frontend/.nvmrc` says 22. The toolchain versions are unchanged (Vite 6.4, Vitest 4.1, D15); the
move to Vite 8 / Vitest 5 is a separate follow-up, not part of Phase 6. Verified on Node
22.23.5 (laptop) and 22.23.4 (image): `npx vitest run` 501 passed, `npm run build` passed, the
rebuilt test stack's `home.spec.ts` on Chromium 10 passed. README, ARCHITECTURE and SECURITY
no longer mention Node 20.

**D84 · Phase 6 reputation inputs come from a history table, simulated for now.**
`reputation_history` (migration 0012) holds one row per completed project per developer with
exactly the §9.1.1 inputs (domain, client, t, T^d, Γ^n, Γ_m^n, internal and external rating
slots, completion time) and `source` SIMULATED or PLATFORM. The market simulator writes
SIMULATED rows now; Phase 11's `reputation.update_project` will write PLATFORM rows from real
reviews and evidence into the same table, so the engine doesn't change. Only SYSTEM writes it.
Simulated values are labelled "Simulated history" everywhere they show (§0.2 rule 6): the
snapshot carries a `simulated` flag so other users' views can say so too, although the history
itself is private. *Alt:* run the engine straight from simulator JSON (no table) — rejected,
Phase 11 would need a second pipeline.

**D85 · Reputation arithmetic.** Every equation runs in `Decimal` on exact 4-place inputs; only
stored outputs are rounded, half-up to 3 places (`numeric(4,3)`), as Phase 5's
`newcomer_snapshot()` did. Explanations show values ×100 as whole numbers.

**D86 · The change cap applies per project, in order.** For X, X_m and β, each project's value
is clamped to ±`rep.max_change_per_project` around the value after the previous project; the first
project is clamped around the newcomer starting values (Γ⁰, Γ_m⁰, the newcomer β). ω, μ and T are
never capped. The log keeps both the raw and the capped value.

**D87 · Projects without external reviews are skipped in Eq. 8.** ε is an EWMA over the projects
that have verified external reviews, in order; with none at all, β = λ (A8).

**D88 · ω with one project.** For N < 2, ω is the newcomer ω⁰ from skill evidence (§9.1.3 says
"with exactly one completed project and no evidence, ω = 0", which this gives); from N ≥ 2,
Eq. 1 over the project domains, and evidence no longer counts.

**D89 · `pcs_replication` in reputation.** Off: the change cap, the §9.1.3 starting values, trust
weighting and per-skill competency. Replication starts from the paper's "set to zero" (Γ⁰ =
Γ_m⁰ = 0), and the values the paper leaves undefined — ω and μ below two projects, β with no
reviews — are 0. Kept: the A2 clip. These replication resolutions are added to the §23 list for
the supervisor.

**D90 · Reviewer trust, formula only, in Phase 6.** `algorithms/trust.py` implements the §9.14
trust formula and the trust-weighted mean; the simulator uses them for peer ratings. The rules
that raise flags, the consistency check, trimming and the `reviewer_trust` table come with
reviews in Phase 11, as does attack injection in the simulator.

**D91 · The ambiguity tests are written with the code they test.** Phase 6 has `test_A1`, `A2`,
`A4`, `A5`, `A6`, `A8` and `A9` (reputation). A3, A7, A10 and A13 belong to Phase 7's fitness and
BPSO, A11 to Phase 10's payment policy and A12 to Phase 15's experiments; `docs/PAPER_ALIGNMENT.md`
lists all thirteen with their phase. These spec-named tests carry a per-line `noqa: N802`
(ruff's lowercase rule) citing §9.0; the rule itself is unchanged.

**D92 · Admin recalculation moves to Phase 12.** The `reputation.recalculate_all` job (30 min, no
retries) and `make reputation-recalculate` exist now (the stage-2 seed uses the engine).
`POST /admin/reputation/recalculate` and the admin page need `GET /jobs/{id}` (Phase 7) and the
admin console, so they come with Phase 12; the admin nav marker is now `phase: 12`. The
"Reputation updated" notification belongs with `reputation.update_project` in Phase 11.

**D93 · Stage-2 personas.** `seed_data/stage2_personas.json` fixes traits and history shape for
the named developers (simulator seed 2026) so the §18.1 stories hold with computed values. Zahid
keeps 3 projects (as the stage-1 seed, not §18.1's "2": with 2 he would be a newcomer and the
documented 10-eligible result would break). Imran's persona works in testing **and** DevOps: under
the real Eq. 1 a single-domain specialist has ω ≈ 0 and C ≈ 0.3·X < C₀ = 0.40, which would filter
his bid out; §18.1 only says his projects were for one client. Rafsan gets one project, so the page
can show "1 of 3 projects done". The seed asserts the computed values against
`tests/fixtures/stage2_reputation_golden.json` (`--write-golden` after a reviewed change) and the 10
eligible bids. Stage 1 keeps its fixed values, so Demo 1 is unchanged.

**D94 · Γ⁰ counts a verified certificate (bug fix).** §9.1.3 lists four verified items; Phase 5's
`_verified_items` counted phone, email and profile only, although its docstring named the
certificate. `reputation_inputs.verified_items` now counts an admin-verified certificate (a
pending one doesn't); tested.

**D95 · Phase 6 dependencies.** `numpy==2.5.4` (spec-named, §3; released 2026-10-10, ≥ 14 days;
2.5.5 was 6 days old), only that package added to the lock. No Recharts: the radar and trend
charts are custom SVG like `Gantt.tsx` (CSP-proven), each with "View as table".

**D96 · E5 as a test.** On simulator seed 2026 (200 developers; 141 with ≥ 3 projects), Spearman ρ
between computed P and latent quality (0.6·skill + 0.4·reliability) must be ≥ 0.5, and between
computed C and latent breadth + communication (0.7·primary domains/3 + 0.3·communication) ≥ 0.5.
Measured: 0.797 and 0.759; seeds 1, 7, 99, 123 give 0.75–0.83 and 0.68–0.78. A first latent target
for C (every domain with skill ≥ 0.6, including ones never worked in) gave only 0.38–0.56; ω can
only observe the domains of completed projects, so the latent counterpart was corrected — no
reputation setting changed. The simulator's late-finish model was also made to depend more on
reliability (late share 0.7 % → 3.9 %) before any threshold was set.

**D97 · Per-skill competency (§9.1.7) interpretation.** "ω computed over projects in skill s's
domain" read literally is Simpson's diversity of a single domain, always 0. DevSync uses the
developer's expertise in that domain: the share of their projects in it, n_i^l / N_i, with a floor
of 0.2 (one domain of ω⁰) for a newcomer with passing evidence there. Display and the optional
`fitness.use_skill_competency` only (off by default). Added to the supervisor list.

**D98 · The newcomer β is the platform mean of computed reputations.** With `rep.newcomer_review`
unset (D8), β with no reviews is the mean β of developers with ≥ `newcomer.threshold` projects
over **engine-computed** snapshots only (hand-set stage-1 values are not engine output, so stage 1
keeps the 0.6 fallback and Demo 1 is unchanged; stage 2 gets 0.664). `recalculate_all` computes it
from the histories alone (a first pass from the fallback), so the result never depends on what was
stored before. Phase 5's `tests/integration/test_reputation_settings.py` asserted 0.6 "while no
platform mean exists"; in the shared test database that now depends on test order, so the test
computes the expected mean independently and checks the fallback with a threshold no snapshot
reaches — every assertion stays exact.

**D99 · SYSTEM writes to reputation tables need the worker's login role.** The new tables' SYSTEM
clauses use `is_system()` (it also checks `current_user = devsync_worker`), and migration 0012
tightens 0006's `reputation_snapshots` write policy the same way: before, a web connection with
`app.role = SYSTEM` would have passed it (no code path does that; the database shouldn't rely on
it). Tested: the web role claiming SYSTEM can write neither a snapshot nor a history row.

**D100 · Test maintenance in Phase 6.** `src/app/prefetch.test.ts` used `/dev/reputation` as its
example of an unbuilt placeholder; the page now exists, so the example is `/dev/earnings`
(Phase 10) — the check is unchanged. `test_demo_reset.py` classifies the three new user-scoped
tables. The responsive matrix and the visual baselines ran every stateful
screen inside **one** test per theme and width (300 s and 180 s budgets); with the 14th screen
(the Reputation page) the shared budget ran out on this laptop, so the run stopped on whichever
screen happened to be last. Each stateful screen now has its own test (120 s responsive, 90 s
visual) with exactly the same checks and the same screenshot names, so every existing baseline
is unchanged and a slow screen fails on its own and by name. No check, threshold or baseline was
relaxed; the test count only grew.

**D101 · Reputation API shape.** `GET /developers/{id}/reputation` is a public value for active
accounts and follows the profile's visibility (404 when hidden, unknown or not a developer). A
newcomer without a stored snapshot sees their own starting values with where they come from
(`newcomer`); everyone else sees nulls for them, as computing them would need that developer's
private data (D58). `GET /me/reputation/history` is the developer's own, newest project first,
cursor-paged, each project with its latest log entries and a plain sentence per change; when a
change was capped the sentence says so. Neither endpoint writes; write methods are 405.

**D102 · Search budget filters are bounded.** The Phase 6 gate's contract fuzzing (step 11, run
on 2026-11-22) sent `budget_min=370372298551098867712` to `GET /projects/search`; the value
passed `ge=0`, overflowed PostgreSQL's BIGINT and became a 500. `budget_min` and `budget_max`
now also have `le=10_000_000_000`, the same cap as a project's budget, so anything larger is a
422 naming the field. Tests: `test_search_budget_out_of_range_is_a_422_never_a_500` and
`test_search_budget_at_the_cap_is_accepted` (`tests/security/test_bids.py`). These were the only
integer query parameters without an upper bound. Nothing was relaxed.

## Phase 7 (team formation; Raisa with Claude Code)

**D103 · Audit chain: a row is numbered after it takes the chain lock (bug fix, found by the
Phase 6 gate).** The first Phase 6 gate run (WSL laptop, heavy load) failed Phase 1's check that
`audit_verify_chain()` finds no break: rows 5703 and 5705 both pointed back to 5704. `seq` is an
identity column, so a row was numbered when its INSERT started, **before** `audit_log_chain()`
took the chain's advisory lock; a writer descheduled between the two could chain after a row with
a higher number, forking the chain, and verification reported tampering that never happened (in
production `/admin/audit/verify` would raise a false alarm). Migration `0013_audit_chain_order`
redefines the trigger to draw `seq` from the column's sequence **after** the lock, so numbering
order and chain order are the same by construction (the identity default still draws first, which
leaves gaps; verification needs order, not contiguity). Rows already written keep their hashes
(append-only). Test: `tests/integration/test_audit_chain_concurrency.py` holds the lock from
another connection while an insert waits and checks the waiting row is numbered after a value
drawn meanwhile — it fails on the old trigger (`6648 > 6649`) and passes on the new one — plus a
30-writer stress check of the chain. Phase 0 code; written on the Phase 6 branch after it went
to the gate (as D102 there, on Raisa's local branch only) and carried into Phase 7 as its first
change, as approved with the Phase 7 plan.

**D104 · CSP and axe checks run one test per screen (extends D100).** `csp.spec.ts` and
`a11y.spec.ts` checked all of a role's signed-in screens inside one test (Playwright's default
60 s), and the stateful axe check all 14 stateful screens inside 240 s; with the Phase 6 screens a
slow machine ran out of budget and the failure named whichever screen happened to be last. Each
screen now has its own test with exactly the same checks (CSP violations, console errors,
off-origin requests; serious/critical axe rules in both colour schemes). The gate selects by tag,
not by count, so only the test count grows. Written on the Phase 6 branch and carried into
Phase 7 with the plan.

**D105 · Formation arithmetic.** PSO and fitness run in NumPy/Python floats (float64), as the spec
allows for the algorithms; money is always integer paisa (prices, budgets, counterfactual prices
rounded down to ৳100). Every score that is stored or shown is rounded half-up to 3 places
(fitness to 4 when stored, 2 on screen per §13.8). Ties between equal-fitness teams break by the
candidate index, so a run is reproducible from its snapshot, parameters and seed.

**D111 · Two paper findings resolved (D9 items 1 and 3).** (1) A3: an infeasible team scores −∞;
[PCS] prints −1, but a feasible team can score below −1 (with all weight on time and t̄ = 1 for
two members, F = −2), so −1 would rank an invalid team above a real one
(`test_A3_infeasible_fitness`). (2) Initialisation: positions Bernoulli(N/k), velocities
U(b_l, b_u); the paper draws positions from U(b_l, b_u) — not a 0/1 vector — and velocities from
U(−|b|, |b|) (`test_initialisation_resolution`: over 3,000 particles the share of ones is
N/k ± 0.01 and every velocity lies in [b_l, b_u)).

**D112 · PSO optimality and E1.** §17's bar — PSO optimal in ≥ 95 % of 200 small instances with a
mean gap ≤ 2 % — is a unit test (`test_pso_is_optimal_on_small_instances`) on the seeded generator
`app/algorithms/formation_bench.py`. `scripts/e1_bpso_vs_exact.py` runs §19's E1 (300 instances,
8–18 candidates, teams of 3–6, three presets, both modes) and writes one CSV row per instance;
it exits 1 below the bar, so the gate runs it with `--instances 20`. Measured on 2026-11-22
(simulated data): 298 solvable instances, PSO optimal in 98.3 %, mean gap 0.042 %.

**D114 · Feasibility in each mode.** `devsync`: exactly N members, each slot exactly its count,
distinct developers, Σ price ≤ the budget after fee (A10), every skill the plan needs held by a
member, and at least `min_newcomers` newcomers. `pcs_replication`: only the paper's Eq. 13
(Σ x = N) and distinct developers — [PCS] has no slots, team budget, coverage or newcomer minimum;
they are DevSync extensions. With `fitness.include_performance` (A7, off by default) the extra
weight C5 equals C1 before the five weights are normalised.

**D115 · Presets are Balanced plus emphasis on one term.** The spec names the presets (Quality→P,
Balanced→C, Fast→t, Budget→c for Algorithm 1) but not their weights. A first choice (Budget =
0.2/0.15/0.15/0.5) sometimes picked a *dearer* team than Quality: Eq. 18 divides each price by the
whole budget after fee, which compresses price differences to about 0.1 a member while time
differences span about 0.8. Weights alone can't make "Budget never costs more than Quality" a
guarantee (even 0.12/0.08/0.07/0.73 left 1 counter-example in 200), and Eq. 18 is not changed.
So each preset is Balanced (0.35/0.25/0.20/0.20) plus 1.0 on its own term, normalised: Quality
0.675/0.125/0.1/0.1, Fast 0.175/0.125/0.6/0.1, Budget 0.175/0.125/0.1/0.6. By an exchange argument
each preset's best team is then never worse than Balanced's on its own term — Budget never dearer,
Quality never less competent, Fast never slower — tested on every instance without exception. The
spec's Budget-vs-Quality comparison is a strong tendency (measured: Budget no dearer in 189 of 200
random instances, Quality at least as competent in 195; asserted as lower bounds) and is checked
exactly on the seeded project in the service tests.

**D107 · Generic jobs API and live progress over SSE.** `GET /jobs/{id}` and
`GET /jobs/{id}/events` serve any job with a requester: its requester or an admin; anyone else,
system jobs and unknown ids get 404 (service check and the `jobs_select` RLS policy). Workers append
small events to a capped Redis list `job:{id}:events` (500 events, 1 h TTL; only the keys `type`,
`status`, `progress`, `iteration`, `best_fitness` and `run_id` are accepted, so no candidate data
can be streamed). The stream sends the current state, then each event with its index as `id`
(`Last-Event-ID` resumes), a heartbeat comment every 20 s, and ends on a final status or after
30 min; at each heartbeat the job row is re-read so a worker that died without a final event still
ends the stream. It holds no database connection while open. Cross-site use is refused (403
`CSRF_FAILED`) when `Origin` is present and not the public origin, or when `Sec-Fetch-Site` is
present and not `same-origin`/`none`: browsers omit `Origin` on same-origin EventSource GETs, so
requiring it would break the feature, while the session cookie is SameSite. A user's fourth
concurrent stream is 429 (`sse:concurrent:{user}`, a slot expires after 31 min if a web worker
dies). The route timeout spares exactly the SSE paths (`SSE_PATHS`), and Nginx has a dedicated
location for them (`proxy-sse.conf`: `proxy_buffering off`, no compression, `X-Accel-Buffering:
no`, read timeout 60 s).

**D106 · How a formation run starts.** Only the project's client starts a run, and only while the
project is FORMING (the bidding-deadline job moves it there; a BIDDING project whose deadline has
just passed gets 409 "try again shortly" rather than a second copy of the close logic). The body
takes a preset (Quality→P, Balanced→C, Fast→t, Budget→c for Algorithm 1's advancement; D115
weights), optional weights C1–C4 (0–1, normalised server-side, all-zero refused), the fairness dial
`min_newcomers` 0–2 (default 1 when a newcomer is shortlisted, else 0) and optional minimum
standards within the D54 floor. Any other field — `seed`, `status`, `result`,
`candidate_snapshot`, … — is 422. Algorithm 1 is re-run through `bids.evaluate` in a SYSTEM
session (D50: the client can't read bidders' skills) and its per-slot shortlist, with the slot
counts, budget after fee, deadline, required and critical-path skills, is frozen as the run's
candidate snapshot next to the parameters (weights, dial, PSO/exact settings, mode) and a
server-generated 31-bit seed. One run at a time per project (a QUEUED/RUNNING run older than 5 min
belongs to a dead worker and no longer blocks), 10 starts an hour per client
(`ratelimit.formation_run`, refused requests count, like bids), and an Idempotency-Key replays the
first 202. Services queue jobs by name through `core/task_queue.py` (an allow-list with each
job's §11 timeout and retries), because the layering forbids services importing `app.jobs`.

**D108 · Invitations are recorded, not sent, in Phase 7.** Confirm (FORMING → TEAM_PENDING) marks
the team's bids SELECTED and every other ACTIVE bid NOT_SELECTED (INELIGIBLE ones stay), creates
the team, its members (INVITED), one invitation row each with `sent_at`/`expires_at` NULL (a check
constraint keeps them NULL together) and TENTATIVE availability reservations over the project
period (§9.17). Phase 8 sends the invitations and starts their 48 h clock, so nobody is invited to
something they can't answer yet. Phase 7 tells the client "Team formation finished" and each
non-selected bidder "Your bid was not selected" (link to the bid, where the explanation is shown);
"You were selected" arrives with Phase 8's invitation. A confirmed run's "why not selected" rows
are written by `formation.explanations` (idempotent per bid and run): a full analysis (gap,
counterfactual price, main gap) for up to 50 bids within a 90 s budget, a reason code for the rest
(NOT_SELECTED, NOT_SHORTLISTED or the Algorithm 1 reason under the run's standards).

**D109 · Saved runs and reproduction.** Every run is kept (deleting is refused by a trigger and the
grants) and listed for the client at `GET /projects/{id}/formation-runs`, newest first, up to 50
(not in the §10 table; it backs "earlier runs" and Recalculate). A run's inputs can't change after
insert, even for SYSTEM (trigger). Re-running the frozen snapshot, parameters and seed gives the
same team and fitness (`run_formation` is pure; tested in the API test through the admin verify
job, which records `admin_verification.reproduced` on the run).

**D110 · Admin pieces and nav markers.** Built now as API only: `POST /formation-runs/{id}/verify`
(admin with step-up, queues `formation.verify`, 202) and `GET /admin/formation-runs` (cursor
page). The admin page moves to Phase 12 (admin nav "Team formation runs" → 12) and the client's
"Teams" page to Phase 8 (nav marker → 8), where a confirmed team becomes something to manage.

**D113 · Homepage fairness figures from a real run.** `backend/scripts/formation_check.py` (the
Phase 7 gate check) runs the stage-2 "Online ordering system" (Balanced, seed 20261207) with the
dial at 0, 1 and 2 and writes `frontend/src/content/homepage-example.json` (`--homepage PATH`):
newcomers in the team and the cost of fairness per setting, no names. The hero chip reads "Fair
team, X cost of fairness" (dial 1) and the fairness spotlight shows each setting's figure; the
gate compares the committed file with a fresh run, so it can't go stale. One script instead of
the planned `build_homepage_example.py`: the same run feeds both the gate fixture and the page.
Measured on the seed: dial 0 → no newcomer, 0 %; dial 1 → 1 newcomer, 16.2 %; dial 2 → 2
newcomers, 38.7 % (the team scores are small sums of positive and negative terms, so relative
costs read large; they are shown as computed). The stills are unaffected (they render no chip).

**D116 · The stage-2 seed leaves the ordering project FORMING.** Spec §18.4 says stage 2 holds
"everything in stage 1", where the ordering project is BIDDING, but Demo 2 runs team formation on
it. After asserting the 10 eligible bids, stage 2 closes that project's bidding through the real
deadline job (verdicts on the bids, notices, BIDDING → FORMING). Expected result with the dial at
1 (`tests/fixtures/formation_expected_team.json`): Mehjabin Chowdhury (newcomer), Nusrat Jahan,
Sadia Islam, Tanvir Ahmed — fitness 0.8287, exact-verified optimal. E2E tests, which build their
own projects, reach FORMING through the test-only `start-forming` route (the test stack runs no
scheduler) and execute queued runs through `formation-runs/{id}/execute` (no worker); both exist
only when `DEVSYNC_ENV=test`. The run code lives in `services/formation_runner.py` so that route
and the RQ entry points in `jobs/formation_jobs.py` share it.

**D117 · Phase 7 gate fixes on the native Linux laptop (2026-11-23).** Four problems the WSL
laptop could not show, none of them in the formation logic: (1) the partial unique index
`one_active_lead_per_team` uses `text()` for a constant DDL predicate and now carries the
`# forbidden-ok:` reason, like `one_standing_bid_per_developer`; (2) `app/core/task_queue.py`
and `app/services/formation_runner.py` had no test of their own, so they got
`tests/unit/test_task_queue.py` and `tests/unit/test_formation_runner.py` (46 tests: listed tasks
only, real job functions, queues the worker listens on, the problem rebuilt from the frozen
snapshot, refused bad snapshots and params, rounding of NaN/inf/−0, downsampling, a real small
run, same seed → same result, newcomer minimum, infeasible budget, early stop) rather than
allowlist entries; (3) the Nginx image was rebuilt with `--no-cache --pull` for the
`krb5 1.21.3-5+deb13u2` fixes Trivy reported; (4) `test_concurrent_writers_keep_one_unbroken_chain`
failed every time here: asyncpg's client-side SCRAM is a Python loop (~180 ms CPU per connect on
this laptop), so 30 connects started together ran past the 3 s connect timeout. The test now opens
its connections five at a time, holds all 30 writers at a barrier on bare connections (no
transaction, so the idle-in-transaction limit doesn't apply) and releases them together, which
guarantees the overlap; it also checks that all 30 rows were written. The writer count, the
chain assertions and the app's connect timeout are unchanged. Production pools its connections,
so it doesn't open 30 at once. (5) `check_paper_alignment.py` was extended to Eq. 13–19 but its
unit test still built an Eq. 1–12 repository, so it crashed on the missing `bpso.py`; the fixture
now covers all 19 equations, three tests cover the formation rules (a function in `bpso.py` or
`fitness.py`, not elsewhere), and a missing formation module is reported as a problem instead of
an exception. (6) Once the laptop ran at full speed, the new Phase 7 E2E flows
(seven users signed in one after another) ran faster than Nginx's `auth` zone allows (5 r/s,
burst 10; the test reset can't clear the edge) and failed with a 429 at sign-in, or with a
misleading 403 `CSRF_FAILED` because `csrfHeaders` ignored a 429 on `/auth/csrf`. The E2E helpers
now send auth requests through `throughAuthZone`, which waits and retries only the edge's HTML
429 (at most 10 tries, 1 s apart) and returns the app's own JSON 429s unchanged, and
`csrfHeaders` fails with a clear error when it gets no token. Nginx's limits are unchanged. (7) The GPU-only homepage test
`scrolling snaps the constellation into a team with the chip` still expected "✓ Balanced team";
since D113 the chip shows the real run's cost of fairness at dial 1. It now expects
"✓ Fair team, <cost> cost of fairness", with the cost read from the same generated
`src/content/homepage-example.json` the page uses and formatted as `fairnessCost` formats it
(16.2 % today), so it can't drift from the figures. (The Playwright runner loads plain Node ESM,
which won't import that JSON without an import attribute, so the test reads the file.)

## Phase 8 (invitations, team lead, team repair; Raisa with Claude Code)

Decisions D118–D136 were made by Raisa with Taeen (team leader) before the plan
(`phase-08-start-prompt.md` Step 5, decisions 1–19, in that order); D137–D139 resolve points the
prompt left open.

**D118 · Milestones at project start.** §8 says first milestones activate at project start but
also `FUNDED → ACTIVE`; escrow (`FUNDED`) arrives in Phase 10. At start, every milestone with no
predecessors moves `PLANNED → ACTIVE` with `actual_start` = the start date. The rule lives in one
guard, `milestone_may_activate()` in the project state table, whose docstring says Phase 10
tightens it to require `FUNDED`. Later milestones stay `PLANNED`; activating them on predecessor
completion is Phase 9/10 work.

**D119 · What "Start project" does (one transaction).** Guard: every slot count is filled by
`ACTIVE` members and a client-confirmed lead exists (409 `INVALID_STATE` with `allowed_actions`
otherwise). Start date := max(planned `start_date`, today in Asia/Dhaka); CPM dates derive from it
and the active members' reservations move to the same window. Because moving the window can create
an overlap, §9.17 availability is re-checked for every `ACTIVE` member over the new period; if
anyone would be overbooked the start is refused (409), the member is named, and the client is told
what to do (wait for that member to free hours, or use leave/repair) — nothing is half-applied.
Then: project `IN_PROGRESS`; team `ACTIVE`; D118 for milestones; the current baseline (v1, written
at publish) gets `approved_by_lead = true` (§7.3 needs both approvals once a team exists); audit;
"Project started" to the team and the client; "You are team lead" to the lead (in-app + email).
Workspace content (tasks, threads, check-ins) is Phase 9, so §17's "create workspace defaults"
creates no placeholder rows. The client starts it explicitly ("Start project", enabled only when
the guard holds): the client makes the final choice (§1.6).

**D120 · A minimal workspace shell (screen 33 before the workspace).** `/w/:projectId/team`: the
workspace header and §13.4 tab bar, the Team tab real, the others "arrives in Phase 9"
(`ComingSoonPage`). Only the project's client and its members (404 for anyone else); admins don't
use this route (admin UI is its own bundle, §14.17; the admin project view is Phase 12) but can read
the team API. Phase 9 fills the shell. Developers reach it from the dashboard card of a started
project; `/dev/projects` stays Phase 9.

**D121 · Removal after inactivity.** Phase 8 builds the client's removal request (reason 20–500)
and the admin approve/reject API under `/admin/…` (step-up TOTP, 404 for non-admins, audited);
approval makes the member `REMOVED` with the same follow-ups as leaving. A request needs a basis:
a linked dispute (Phase 12) or the member inactive ≥ 10 days, checked by one function,
`member_inactive_days(member)`, which in Phase 8 returns "no signal yet" — so inactivity requests
are refused (409, "the activity signal arrives in Phase 9"). Tests swap that function for a stub
(dependency override or monkeypatch); there is no production bypass. Phase 9 replaces its body.

**D122 · Notifications page now, live stream later.** Phases 6–7 write in-app notifications that
no screen shows. Phase 8 builds `GET /notifications` (cursor page), `POST /notifications/{id}/read`,
`POST /notifications/read-all`, `GET /notifications/unread-count`, the Notifications page (screen
18: grouped by day, unread dot, mark all read) and the bell's unread badge (refreshed on focus and
every 60 s while visible). Phase 9 adds the SSE stream and preferences. The nav marker drops.
`link_path` stays validated by `core/redirects.py` (§14.6).

**D123 · Invitations confirmed under Phase 7 are still unsent.** Confirm now sends invitations
immediately. `lifecycle.expire` also sends any unsent invitation of a `TEAM_PENDING` team
(idempotent: only `sent_at IS NULL`), starting the 48 h clock when it sends. No data migration.

**D124 · Availability re-check on accept (D54).** If Σ CONFIRMED reservations on other projects
overlapping the period + this commitment > the profile's `hours_per_week`, accept is refused with
409 `UNAVAILABLE`, saying how many hours are free and suggesting raising the weekly hours or leaving
another project. The invitation stays open until it expires; the client sees "can't accept: fully
booked". TENTATIVE reservations (including the member's own for this project) never count (§9.17).

**D125 · At most 10 pending invitations per developer (§14.8).** Enforced where candidates are
chosen: a developer with 10 sent, unanswered invitations is excluded from new formation runs' and
repairs' candidate sets, with `TOO_MANY_PENDING_INVITATIONS` in the explanation ("You had 10
invitations waiting for an answer, the most allowed at once; answer them to be considered"). A race
that still hits the limit at confirm or choose is refused with 409 and the client is told to
recalculate; the client is never left half-confirmed.

**D126 · Reopen a slot for 48 h.** `project_slots.reopened_until timestamptz NULL` and
`reopen_count smallint` (≤ 2 per slot, mirroring the two bidding extensions, §9.19). Allowed only
from a repair proposal with no candidates, while `TEAM_PENDING` or `IN_PROGRESS`. While open,
developers bid for that slot only through the normal endpoint and Algorithm 1 eligibility under the
confirmed run's standards; the project appears in search with "1 open place" (no bid data).
`lifecycle.expire` closes the window, queues `formation.repair` and notifies the client.

**D127 · Raise the budget.** Only from a repair proposal whose reason is `REMAINING_BUDGET_TOO_LOW`,
while `TEAM_PENDING` or `IN_PROGRESS`. New budget ≥ current + shortfall, ≤ 10,000,000,000 paisa;
`budget_paisa` changes, C (budget after fee, A10) is recomputed, `version` bumps (`If-Match`), audit
with old and new values, the repair is recomputed. Dependency: Phase 10 computes escrow from the
then-current budget.

**D128 · Repair uses current data, frozen per proposal.** Candidates are evaluated with current
reputation, eligibility (Algorithm 1 under the confirmed run's standards) and availability, read in
a SYSTEM session (D50). `repair_proposals` stores its own `candidate_snapshot`, `params`, `seed`
and `settings_version` (immutable once written, trigger, the D109 principle). One open proposal per
departed member: a recomputation supersedes the old one (`SUPERSEDED`). Statuses `COMPUTING`,
`READY`, `NO_CANDIDATES`, `CHOSEN`, `SUPERSEDED`, `CANCELLED`. The repair job's `jobs.requested_by`
is the project's client whoever triggered it, so the client's Team screen can follow it (D107
answers 404 to anyone else). Choosing a replacement moves its bid `NOT_SELECTED → SELECTED`: added to
the §8 bid transitions here. The developer, earlier told "not selected", gets "You were selected as
a replacement"; the bid detail shows the sequence and marks the old "why not selected" superseded.

**D129 · Which milestones a departure affects.** Before start: every milestone whose skills include
the departed member's slot skill. After start: the same, limited to milestones not yet done. If no
milestone lists that skill, the impact is budget-only, and the screen says so.

**D130 · Who sees a team.** `is_team_member()` (0015) counts only `INVITED`, `ACTIVE`, `COMPLETED`
members. A developer who declined, expired, left or was removed sees only their own `team_members`
row and invitation. Prices and days are sealed among members: developers never see other members'
`price_paisa` or `days_needed`, only the client and admins do — enforced by role-specific response
models (`TeamMemberForClient` vs `TeamMemberForMember`, the §14.5 pattern). RLS tests for both.

**D131 · Lead recommendation inputs (§1.6 rule 1), a pure function in `algorithms/`.** Values come
through `services/reputation_read.py` (stored snapshot, or the §9.1.3 newcomer values computed on
the fly), so newcomers rank on the same footing. `ACTIVE` members by X_m, then `completed_projects`,
then C, then the earlier `invitations.responded_at`, then `developer_id`. Members who declined the
lead role on this project (`team_members.lead_declined_at`) are skipped. The reason reads "Highest
teamwork capacity: 86; led 2 past teams" (completed teams where they were the active lead; the clause
is omitted at 0, i.e. everyone until Phase 11). Values shown 0–100 (§13.8).

**D132 · The lead role, once chosen.** The client can choose a lead once every slot has an `ACTIVE`
member; it takes effect immediately. If a non-lead member leaves before start, the lead stays and the
start waits for the repair. The chosen developer may decline the role before or after start; the
project then has no lead until the client confirms the next recommendation (an `IN_PROGRESS`
project may briefly have none; it can't start without one). Lead-change requests: one open per
member per project, at most 3 per member per project per week, reasons 20–500. Approving one makes
the current lead a normal member and shows the client the next recommendation (excluding the
outgoing lead; a named `ACTIVE` `suggested_member_id` is pre-selected); the client confirms.
Rejecting needs a reason the requester sees. Leave and removal reasons: 20–500. Caps with no §6.2
setting are named constants (`MAX_PENDING_INVITATIONS = 10`, `MAX_LEAD_CHANGE_REQUESTS_PER_WEEK =
3`), like `MAX_OPEN_BIDS`.

**D133 · `formation.repair` in tests.** The test stack has no worker or scheduler (D116), so
test-only routes run a queued repair now, run `lifecycle.expire` now, and set an invitation's
`expires_at`. They exist only when `DEVSYNC_ENV=test` (`assert_no_test_routes`).

**D134 · Endpoints §10.2 doesn't list** (contract in `docs/API.md` and OpenAPI): `POST
/projects/{id}/start`, `POST /projects/{id}/budget`, `GET /me/invitations`, `GET /me/teams`, `POST
/lead-change-requests/{id}/withdraw`, `POST /team-members/{id}/removal-requests`, `GET
/notifications/unread-count`, `GET /admin/removal-requests`, `POST
/admin/removal-requests/{id}/approve|reject`. §10.2's names are kept for the routes it lists. `GET
/projects/{id}/team` is role-shaped and carries everything the Team screen needs: members,
invitations, the lead recommendation and reason, lead-change requests (all for the client, own for a
member), removal requests (client only), the latest repair proposal's status (details from `GET
/projects/{id}/repair`, client only).

**D135 · Cancellation.** `TEAM_PENDING` stays free to cancel (§8): team `CANCELLED`, open
invitations closed, every reservation `RELEASED`, members and the client notified, audit.
`IN_PROGRESS` is not cancellable in Phase 8 (outside `CANCELLABLE`): §8's refund/freeze/dispute
rules need Phases 10 and 12; the 409 says so and a test pins it.

**D136 · Account changes during a team.** Admin suspension and self-deletion are not built yet
(admin users and data export/deletion are Phase 12, `docs/BACKLOG.md`); today only sign-in checks
the `SUSPENDED`/`DELETED` statuses. A suspended developer can't sign in, so their invitations
expire and repair follows. The rule for Phase 12's deletion, recorded now and built then: refuse
deletion while `ACTIVE` in an `IN_PROGRESS` project; a pending invitation is treated as declined
(repair follows); an `ACTIVE` member of a `TEAM_PENDING` team is treated as having left.

**D137 · One bid per developer per project on a reopened slot.** Decision 9 assumes a
`UNIQUE(project, developer)`, but `one_standing_bid_per_developer` covers only `ACTIVE` and
`INELIGIBLE` bids, so a developer whose bid is `NOT_SELECTED`, `DECLINED` or `EXPIRED` could bid
again. The bid service refuses a reopened-slot bid from anyone with a non-`WITHDRAWN` bid on the
project (a withdrawn bid may still be replaced, D49). No schema change.

**D138 · Repair impact arithmetic (§9.9).** "The candidate's days applied to the departed member's
unfinished milestones": each affected milestone's (D129) duration is scaled by candidate days ÷
departed member's days, rounded up, at least 1. Before start CPM is recomputed (`cpm.compute_cpm`);
after start the §9.10 forecast (`forecast.forecast`). Delay = new finish − the baseline duration;
budget delta = the team's price with the candidate − C (A10). Worked example in `docs/ALGORITHMS.md`
and a hand-computed test.

**D139 · The stage-2 golden file lives with the seed data.** `make demo-up STAGE=2` failed in the
production-style image (`FileNotFoundError: /app/tests/fixtures/stage2_reputation_golden.json`):
that image ships `app/`, `alembic/` and `scripts/` but not `tests/`. Broken since Phase 6, unseen
because the gate seeds in the tests container. The file moved to
`backend/scripts/seed_data/stage2_reputation_golden.json`, next to `stage2_personas.json`; content
unchanged.

**D140 · The team view reads in a stable order: role, then name (Phase 8 gate, step 15).** The
new `client-team-repair` and `workspace-team` baselines failed on the gate laptop: same content,
rows in another order. Confirm creates every member in one transaction, so `created_at` ties and
`_members` fell back to the random member id; open slots were listed by random slot id, so the
"Start the project" blockers shuffled too. The test setup accepts invitations in the listed order,
and the lead recommendation breaks equal scores by the earlier acceptance (D131), so even the
recommended lead changed between runs. `get_team` now sorts members by slot label, then developer
name (case-folded), then id, and the blockers by slot label (the Phase 7 formation cards use the
same order). `_members` keeps creation order for the locking paths. Test:
`test_the_team_reads_in_a_stable_order_role_then_name`; the 12 baselines were re-created and pass
twice in a row on fresh data.

## Phase 9 (workspace and monitoring; Sara with Claude Code)

Decisions D141–D159 were made by Sara Binte Shafayet (tester, owner of Phases 9–11) with Taeen
(team leader) before the plan (`phase-09-start-prompt.md` Step 5, decisions 1–19, in that order).
D160 onward are open points Claude Code resolved while studying, by Sara's instruction for this
phase ("decide, record, report"; it overrides CLAUDE.md's "ask, don't guess" for Phase 9 only).

**D141 · Phase 9's scope edges.** Built now: workspace tabs Overview (29), Tasks (30), Timeline
(31), Check-ins (34), Files (35), Discussion (36), Evidence (38, the activity part), Risks (39), and
the existing Team tab (33) gains "contribution so far"; developer My projects (13); the progress
parts of both dashboards (9, 20); baseline vs forecast on the plan page (22); the notification
stream (18) and preferences (19). A **read-only Milestones tab** is built now (§17 Phase 9's E2E
opens "Milestones", while screen 32 belongs to Phase 10): status, share, planned and forecast
dates, progress from tasks, revision count; Phase 10 adds submission, review, escrow and the
auto-approval countdown to the same tab. Later: Payments (37) "arrives in Phase 10"; Reviews and
Post-mortem Phase 11; Disputes tab Phase 12; Evidence's GitHub part Phase 13 (the tab says so);
the admin's read-only project view Phase 12 (screen 45). Task evidence is Phase 9 (§17 lists
"evidence attachments"), so `docs/BACKLOG.md` FR-DEL-1 moves from Phase 10. Plan change requests
(FR-PROJ-5, `/plan-changes`) are not in §17 Phase 9: deferred to after Demo 2 (backlog row says so
with this decision); FR-PROJ-6 (baseline vs forecast) is built. Phase 13's `github_stats` table,
`POST /projects/{id}/github/sync` and the sync button are not created now. Phase 9's DAST is the
ZAP **baseline**; the OpenAPI-driven API scan (§16.1) comes with full DAST in Phases 14–15.

**D142 · Who may see and change the workspace.** Migration 0016 adds the §14.15 helpers
`is_project_member(project)` (an `ACTIVE` member; `COMPLETED` also counts for reading, so Phase 11
can show finished projects) and `is_participant(project)` (the project's client or a member),
`STABLE`, `search_path` pinned. Read: participants; members who are `INVITED`, `DECLINED`,
`EXPIRED`, `LEFT` or `REMOVED` get 404, like D130. Write: `ACTIVE` members within §2.2; the client
may comment, post in discussion and upload files and nothing else — task create, assign, move,
evidence and check-ins are 403 for the client, and the UI shows no drag handles or task actions
(§1.6). §17 Phase 9 says the client's tabs are read-only "except comments/discussion", while §2.2
also lets the client "Upload project files (own project)": the permission matrix is the more
specific rule, so the client may upload. Writes need the project `IN_PROGRESS` (409
`INVALID_STATE` otherwise); a `TEAM_PENDING` project shows only the Team tab. `GET
/projects/{id}/plan` (client or admin today, `_load_for_read`) is readable by members too (§10.2
"Client, members, admin"; the Timeline needs it); the client-only paths keep their own loader.
Admins read the dashboard, risks, activity and plan through the API (§2.2 "read-only"); comments,
discussion and files for admins come with Phase 12's dispute context, so those routes are 403 for
admins until then. Admins never use `/w/...` (D120).

**D143 · Tasks.** The lead creates and assigns tasks in any unfinished milestone (`PLANNED`,
`FUNDED`, `ACTIVE`, `CHANGES_REQUESTED`); a task leaves TODO only while its milestone is `ACTIVE`
or `CHANGES_REQUESTED`. The assignee is an `ACTIVE` member of the project or nobody; only the lead
moves an unassigned task. Moves follow §8's chain one step at a time (TODO ↔ IN_PROGRESS ↔ REVIEW ↔
DONE); the board shows a refused drop target with the reason. DONE only if every dependency is
DONE (409 naming them); a task can't leave DONE while a task that depends on it is DONE (409
naming them); leaving DONE records `task.reopened`. `progress_pct` derives from the status weight
(0, 50, 85, 100; §9.10), never typed in. Dependencies: same milestone, acyclic (409 with the cycle
in order), ≤ 20 per task. Delete: the lead, only when not DONE; its dependency rows go with it; the
deletion is recorded. A member who leaves or is removed has their unfinished tasks unassigned and
the lead is notified. Tasks carry `version` (`If-Match`); a stale move is 409 and the board rolls
back. `PATCH /tasks/{id}` is the lead's (title, description, assignee, deadline, estimate,
difficulty, milestone); a task changes milestone only to another unfinished milestone, only while
TODO and only with no dependencies either way (dependencies never cross milestones), else 409
naming which to remove. The assignee moves the task and adds evidence and comments. Bounds: title
1–160; description ≤ 5000; estimate > 0 and ≤ 999.9 h, one decimal (`Decimal`, `numeric(5,1)`);
difficulty `EASY|MEDIUM|HARD`; deadline optional, not before the project's start date; named caps
(D63): 1000 tasks per project, 20 dependencies and 20 evidence items per task. `last_activity_at`
is updated by every move, evidence and comment (STALLED_TASK reads it). Task is a §8 state machine,
so every status move, creation, reassignment and deletion writes an audit entry (`write_audit`)
besides the activity event; reordering within a column is not a transition. `task.done` and
`task.moved` record the task's milestone, its assignee at that moment and its estimate (§9.13
credits completed hours to whoever finished them; §9.1.1's t comes from the member's milestones).

**D144 · Card order: fractional positions.** `position` is a text key generated by the server
from the neighbours the client names (`after_id` / `before_id` in the same column); every list
orders by `(position, id)`, so it never ties (the D140 lesson). The key generator is a small pure
module with property tests (between any two keys there is another; keys stay short under repeated
inserts); no new dependency. Moves into a column take a per-milestone advisory lock
(`app/db/locks.py`) so two simultaneous drops between the same neighbours can't produce the same
key; if the neighbours' keys are equal or a key grows past a set length, the server re-keys that
column inside the same lock. Neighbours must be in the target column and milestone, or the move is
422.

**D145 · Check-ins.** A check-in belongs to the week (Monday–Sunday, Asia/Dhaka) it is posted
in: one per member per week (`UNIQUE(member, week_start)`), immutable once posted (reputation
evidence; corrections go in a comment). Fields: `done` and `next` required, 1–2000 characters;
`blockers` optional ≤ 2000; `confidence` integer 1–5; `week_start` and `on_time` set by the
server. On time = posted by Tuesday 23:59 Asia/Dhaka of that week (the Monday 10:00 reminder gives
a day and a half). Expected weeks run from the first Monday on or after the member became `ACTIVE`
in an `IN_PROGRESS` project until they leave or the project leaves `IN_PROGRESS`.
`checkin.reminders` (Monday 10:00, §11) reminds every member who hasn't posted this week (in-app +
email, §12) and records `checkin.missed` for every finished expected week with neither a check-in
nor a `checkin.missed` yet, so a run skipped while the scheduler was down is caught up; idempotent
per member-week. A check-in with non-empty `blockers` notifies the lead (`blocker.reported`);
anyone in the project may reply (a `CHECKIN` comment, D146), the client too; the first reply by
**another member** records `blocker.answered` with who answered (§9.1.5 counts teammates helping,
so replies from the client or the author don't count).

**D146 · Comments and discussion.** Comment targets are `TASK`, `MILESTONE` and `CHECKIN` (an
addition to §7.5's enum, for blocker replies). A comment may name a `reply_to` on the same target;
when the replied-to comment's author had mentioned the replier, the reply records
`comment.replied` with the response time in seconds (§9.1.4 reply score). Mentions: the client
sends user ids explicitly (picked from a member list); the server keeps only participants of that
project and drops anyone else silently (§17 "mention of non-member ignored"); at most 10 per
comment or post. Bodies are plain text ≤ 4000, rendered as text (the injection corpus comes back
inert); §13.7's linkifier turns only `https://` URLs into links with `rel="noopener noreferrer
nofollow"` (`javascript:`, `data:`, `http:` never become links; unit-tested). Authors may edit for
15 minutes ("edited" label; previous versions in `comment_revisions` / post revisions) and
soft-delete their own (`deleted_at`, shown as "Comment deleted"). Discussion: threads per project
(title 3–120), posts ≤ 4000 with optional `reply_to`, the same mention and edit rules, polled every
15 s while the tab is visible. A post records `comment.posted` (and `comment.replied` under the
reply rule) with `entity_type` `DISCUSSION_POST`, so §9.1.4 sees both places people talk.
Participants never see a deleted comment's or post's earlier text or revisions; rows are kept for
Phase 12's dispute evidence (admin only). Comments and posts share one 60/hour bucket per user
(§14.8).

**D147 · Project files.** `files` gains `project_id NULL` and the kind `PROJECT_FILE` (CHECK:
project files have a project, others don't). Allowed types are exactly §14.9's (images
re-encoded, PDF ≤ 10 MB, plain text/markdown ≤ 1 MB; ZIP and everything else refused by
signature), through the existing pipeline. Participants upload; the uploader or the lead deletes
(soft). `file_access()` and the `files` RLS policies are extended so project participants can read
project files and nobody else can; downloads keep the signed-URL path (5 min, `attachment`,
`nosniff`, `sandbox`). Limits: 20 uploads/hour (`ratelimit.upload`, existing) and 500 MB/day per
user; the byte budget gets a new settings key (e.g. `ratelimit.upload_bytes_per_day`) in
`alembic/seed/platform_settings_v6.json`, inserted as a new settings version by 0016 exactly as
0011 added v5; every settings test that checks the seed files against the schema defaults passes
with v6. `files.project_id` joins the columns `files_identity_immutable()` protects. Deleted
project files are hidden and never served, but their bytes are kept (Phase 12 evidence), so the
24-hour orphan cleanup must not purge them. Evidence of kind `FILE` must reference a project file
of the same project. Screen 35's "linked task/milestone" comes from that evidence; no link columns
are added to `files` (Phase 10's submissions link milestones through `evidence_ids`).

**D148 · Task evidence.** Kinds `FILE`, `LINK`, `PR`, `SCREENSHOT`. URLs `https://` only, ≤ 2048
characters, **never fetched** (no previews, no unfurling); a `PR` must look like
`https://github.com/<owner>/<repo>/pull/<n>` (format check only; Phase 13 verifies). Note ≤ 500.
Added by the task's assignee or the lead (§2.2), recorded as `task.evidence_added`.

**D149 · Activity events (§9.1.6).** One Pydantic schema per event type in one module, covering
all 22 catalogue types (Phases 10–13 emit the later ones); every write is validated and the Phase 9
tests validate every schema. The table is append-only (`reject_mutation()` trigger, like the audit
log; UPDATE and DELETE fail at the DB level; tested). Events are written in the same transaction as
the change they record, through a `SECURITY DEFINER` function (`record_activity()`) that checks the
actor is the caller (`app_uid()`), the caller is a participant of the project and the type is in
the catalogue; direct INSERT stays SYSTEM-only (§14.15); the definer pins `search_path` and has its
own RLS tests. Paths that already run as SYSTEM (team services through `_system()`, jobs such as
`checkin.missed`, admin decisions such as removal approval) insert directly in their own
transaction — the definer would rightly refuse an admin, who isn't a participant. Event `data`
never holds money or another member's private data (no prices, days, or reasons for leaving):
every participant reads the feed and D130 keeps prices sealed among members; the schemas enforce
it and a test scans the feed as a member. Phase 8 paths start recording too: `member.left` (leave
and removal) and `member.replaced` (a replacement accepts). Every input §9.1.4–9.1.5 needs is
recoverable from events (on-time ratio, reply times, DONE-not-reopened, work start, blockers
answered); the plan says which event carries which input.

**D150 · Inactivity.** `member_inactive_days()` (D121) gets its real body: whole days since the
member's last `checkin.posted`, task event, comment or discussion post in that project; with none,
since they became `ACTIVE`. `INACTIVE_MEMBER` uses the same function. Removal for inactivity now
works at ≥ `alerts.repair_days`: D121's "no signal" 409 is replaced by the real check, and the
tests and `docs/BACKLOG.md` P8-7 are updated.

**D151 · The risk engine and monitoring.** A pure engine in `algorithms/risks.py` (§4): every
§9.11 rule, team health, overall risk, schedule progress, budget usage; one function per rule,
every threshold from settings; the project day is calendar days since `start_date` in
Asia/Dhaka. Saving settings rejects `alerts.inactive_days ≥ alerts.repair_days`. CAPACITY compares
a member's open task hours with their committed hours for this project (the reservation's
`hours_per_week`) × weeks until those tasks' deadlines (≥ 1 week; a task without a deadline uses
its milestone's forecast finish). SKILL_DEPENDENCY's "skill held by exactly one active member"
means the member's slot skill on this team. Severities: STALLED_TASK LOW at ≥
`alerts.stalled_days`, MEDIUM at ≥ 2 × it; INACTIVE_MEMBER MEDIUM at ≥ `alerts.inactive_days`,
CRITICAL at ≥ `alerts.repair_days`; for SKILL_DEPENDENCY "inactive ≥ 5 days" means ≥
`alerts.stalled_days` and "overloaded" means an open CAPACITY risk on that member.
CRITICAL_PATH_DELAY and SLACK_EATEN look at started (`ACTIVE`) milestones only; not-started
milestones pushed by a late predecessor aren't flagged again, the ripple shows once in
DEADLINE_IMPACT (otherwise the seeded Inventory project would show three CRITICAL risks and
"Critical" health, where §13.9 shows one CRITICAL and "At risk"). Milestone → forecast state:
`APPROVED`, `AUTO_APPROVED`, `PAID` → DONE; `ACTIVE`, `SUBMITTED`, `CHANGES_REQUESTED`, `DISPUTED`
→ ACTIVE; `PLANNED`, `FUNDED` → NOT_STARTED; p from tasks (§9.10 weights; no tasks → 0). BUDGET
and AUTO_APPROVAL_SOON are written and unit-tested now but fed zeros until Phase 10 (they can't
fire; the budget donut honestly shows released 0, committed 0). One computation,
`monitoring.evaluate(project, now)`: risks upserted by (project, type, entity), OPEN ones unique;
a severity change updates the row; a risk resolves when its rule stops firing; today's
`forecast_snapshots` row is upserted with every milestone's planned and forecast start and finish,
the project finish and impact, and which milestones caused the delay (Phase 11's post-mortem reads
the causes). A risk that opens as or is raised to CRITICAL notifies the client and the lead once
(in-app + email, §12, subject to preferences); re-evaluations don't repeat it. Triggers: the
scheduler every 15 min per `IN_PROGRESS` project; task and milestone events debounced 30 s per
project with a Redis key, designed so the last event of a burst is never lost (e.g. a dirty flag
re-checked at the end of the job; tested). `GET /projects/{id}/dashboard` reads the latest
evaluation plus live task counts and shows when it was evaluated; it is cached 30 s in Redis per
project and per response shape (client and member never share an entry); the triggering events
invalidate it; the cache goes through a new `core/cache.py` (§4, §15.1: cache-aside, versioned
keys, invalidation after commit, single-flight lock) with its own tests; p99 < 2 s. Dashboard and
risks are role-shaped: the budget part (released, committed, remaining) and the BUDGET and
AUTO_APPROVAL_SOON risks are for the client and admins only; members get progress, schedule,
forecast, health and the other risks; separate response models (`…ForClient` / `…ForMember`, the
D130 pattern) and a test scanning a member's responses for budget fields. INACTIVE_MEMBER at
CRITICAL suggests "Request removal / find a replacement" to the client — a suggestion only (§9.9)
linking to the Phase 8 removal request; it never starts a repair by itself.

**D152 · Forecast on the plan and the Timeline.** `GET /projects/{id}/plan` adds the forecast
when the project is `IN_PROGRESS`: per-milestone forecast start and finish, the forecast finish,
the impact in days and the critical paths, taken from the same latest evaluation so Overview,
Timeline and plan page never disagree. Screen 22 gets the baseline/forecast toggle; screen 31
shows baseline vs forecast with the critical path and a today line. The read-only Milestones tab
(D141) reads this response too: for an `IN_PROGRESS` project each node also carries its status,
task progress (0–100), revision count and actual dates, so no extra endpoint is needed.

**D153 · Notifications: stream and preferences.** `GET /notifications/stream` exactly as
D107/§10.3: session cookie, the Origin/`Sec-Fetch-Site` rule, the same `sse:concurrent:{user}`
counter (job streams and the notification stream together ≤ 3), heartbeat 20 s, close after 30
min, `Last-Event-ID` resume, no DB connection held while open. Events carry only the notification
id, type and the user's own title, through Redis pub/sub (§15.2; the demo stack runs two API
replicas, so no in-process state), published only after the notification's transaction commits.
Because pub/sub drops what nobody heard, on connect and on resume the stream first sends the
user's notifications newer than `Last-Event-ID` with one short query, releases the connection, then
follows the channel. Nginx gets its location (like `jobs/{id}/events`) and an edge test. The bell
and page update live; the 60 s refresh stays as the fallback. Preferences: the
`notification_preferences` table, `GET/PUT /notification-preferences` and a Settings section
(screen 19) linked from Notifications, covering every §12 row (including those Phases 5–8 already
send) except account and security emails (verification, password reset, new-device sign-in),
which can't be turned off. Enforced in one place — `notify`/`notify_users` and the email enqueue,
keyed by type — with a test that an existing Phase 8 notification respects a turned-off
preference. One catalogue (an enum) of notification types; every existing `notify(..., kind)`
string and email template is mapped to a §12 row in the plan, and `notify` refuses an unknown type
(a test greps every caller). Defaults follow §12's columns; mentions are in-app on and email off by
default (§12 has no mention email, §17 says "email outbox for … mentions": the email exists but is
opt-in); CRITICAL risks and check-in reminders are in-app and email on. Preferences may move to
Demo 3 only if the Demo 2 walkthrough itself is at risk (§17.0); then the stream stays, the move is
recorded and reported.

**D154 · The Inventory dashboard seed (§18.2 item 2).** Stage 2 gains "Inventory dashboard"
`IN_PROGRESS` on project day N (default 12; `make seed-demo STAGE=2 DAY=N`) with §18.2's numbers:
Requirements done 0→3; UI design done 3→8 with `revision_count = 1`; Inventory API active from
day 4 at p = 0.7; Dashboard frontend active from day 8 at p = 0.4; Integration and Testing not
started; planned 23, forecast 25 (+2); one member inactive 8 days. The team goes through the real
services (publish, bids, a formation run with `formation_runner`, confirm, accept, lead, start)
with the clock frozen at past days so the start date is today − N. The start (D118) activates only
Requirements; every later milestone change is done by one commented SYSTEM seed helper (approval
and activation after a predecessor are Phase 10's services): Requirements `APPROVED` finished day
3; UI design `ACTIVE` from day 3 then `APPROVED` finished day 8, `revision_count = 1`; Inventory
API `ACTIVE`, `actual_start` day 4; Dashboard frontend `ACTIVE`, `actual_start` day 8. No money
rows (ledger history and the disputed split on UI design come with Phases 10 and 12). The history
is fixed in project days and `DAY` only moves "today": every task move, check-in and comment has a
project day ≤ 12 and the seed writes only those ≤ `DAY` (`DAY=12` is §18.2 exactly; `DAY=14`
shows the inactive member at 10 days → CRITICAL and the forecast slipping; `DAY=10` is quieter;
the gate asserts `DAY=12` only). Tasks, moves, check-ins and comments go through the Phase 9
services under a `FrozenClock` per simulated day; append-only rows are never rewritten. Task
estimates and statuses give exactly p = 0.7 and 0.4. Only the documented risks: exactly one
CRITICAL_PATH_DELAY (Dashboard frontend, forecast finish 18 vs 16), SLACK_EATEN (Inventory API),
DEADLINE_IMPACT MEDIUM (2 ≤ 10 % of 23), INACTIVE_MEMBER MEDIUM (8 days); health "At risk",
overall CRITICAL. The inactive member is chosen so SKILL_DEPENDENCY and STALLED_TASK don't fire
and estimates fit everyone's hours so CAPACITY doesn't; the seed asserts its end state. If §18.2's
numbers can't produce exactly this set, the gate- and demo-visible result is kept (forecast 25, +2,
one CRITICAL on Dashboard frontend, "At risk") and only details §18.2 doesn't fix are adjusted,
recorded and asserted. Must not change: the ordering project's eligible bids and D116 team, the
golden reputations, the Clinic repair, the homepage figures; Inventory reservations must not
overlap the ordering project's period; `make demo-reset STAGE=2` stays under 30 s (measured).

**D155 · Test-only routes (D133 pattern, `DEVSYNC_ENV=test` only, `assert_no_test_routes`).**
Run `monitoring.evaluate` for a project now with an optional `as_of` date (the engine's `now`;
how E2E and API tests move time forward without rewriting append-only rows), and run
`checkin.reminders` now with an optional `as_of`. No route changes stored timestamps.

**D156 · Endpoints §10.2 doesn't list** (contract in the plan, `docs/API.md` and OpenAPI; §10.2's
names are kept for the routes it lists): `GET /projects/{id}/tasks?milestone_id=&assignee_id=&mine=&status=&cursor=&limit=`
(the board's "All milestones", "Only mine" and each column's "Show more" after 50 cards, D158);
`GET /tasks/{id}` (the drawer); the discussion post edit and delete (exact paths fixed in the
plan); `GET /me/projects` (developer My projects, active and completed); `GET
/projects/{id}/evidence` (the Evidence tab's per-member activity summary); the two test-only
routes of D155. The final list is recorded here when the plan is approved.

**D157 · The DAST step (gate step 17) and `make zap`.** Implemented in Phase 9 and must pass from
now on. Image: ZAP, pinned to an exact version tag and digest, at least 14 days old (recorded here
when chosen). The baseline (passive) scan runs against the running test stack through Nginx over
HTTPS with an authenticated context (a seeded test user's session from the test router, injected
as a header), excluding sign-out and every state-changing URL from the spider, with start URLs for
the main signed-in pages and the workspace. The report goes to `runs/zap/`; the gate note gives
the alert counts. Any High or Medium fails; a rules file may ignore an alert only with a DECISIONS
entry naming it and showing why it is a false positive; never relax a header or security default.
Findings on pages from Phases 1–8 are fixed at their cause (a trial run on day one). ZAP accepts
the test stack's self-signed certificate for this target only; TLS is never turned off.
`--offline` records a skip, like step 7; Taeen pre-pulls the image (Known issues line).

**D158 · Phones and long lists (§13.14).** Kanban on phones: one column per screen with
horizontal snap scrolling and column tabs, long-press drag (300 ms) with edge auto-scroll, a "Move
to…" menu on every card, "New task" as a floating action button for the lead. Timeline on phones
defaults to the CPM list (cards with dates, slack, critical badge) with "Show timeline" for the
scrollable Gantt (sticky name column, zoom buttons), built once in the shared components and used
on the plan page too. Comments and discussion on phones open as a full-screen thread with the input
fixed above the keyboard. Lists over 50 items are virtualized (activity feed, notifications,
discussion posts, files, check-ins feed); Kanban columns instead show 50 cards then "Show more"
(cursor). The one new frontend dependency is `@tanstack/react-virtual` (TanStack family, no
dependencies, positions rows through the CSSOM — no injected `<style>`, D23), pinned to an exact
version ≥ 14 days old, installed with `npx npm@10 install` (D15), version and reason recorded here,
proven by `csp.spec.ts` on a long list and the route-chunk budget. If it breaks CSP or the budget:
no hand-written virtualizer — cursor pages of 50 with "Show more", at most 200 rows mounted, the
dependency removed, and the change recorded.

**D159 · Order of work (Demo 2 first).** (1) migration and RLS; (2) tasks, Kanban and evidence;
(3) check-ins; (4) comments with mentions; (5) activity events; (6) monitoring (engine, job,
dashboard, risks, forecast) and the Overview, Timeline, Milestones and Risks tabs; (7) the
Inventory seed and `phase9_checks`; (8) files; (9) discussion; (10) the notification stream and
preferences; (11) Evidence tab, My projects, the dashboards' progress parts; (12) the DAST step.
The gate still needs everything; if behind, keep this order, report items at risk, never cut tests
or security. The only scope §17.0 lets move to Demo 3 is notification preferences (D153).

**D160 · The workspace tab bar follows §13.4 (all eleven tabs).** The Phase 8 shell lists nine
tabs, matching the §13.9 wireframe (no Discussion, no Evidence), while §13.4 lists Overview ·
Tasks · Timeline · Milestones · Team · Check-ins · Files · Discussion · Payments · Evidence · Risks,
and Phase 9 builds Discussion (36) and Evidence (38) under D141. §13.4 is the layout rule (the more
specific section for navigation); §13.9's wireframes say they fix structure but are illustrative in
detail. So the bar has §13.4's eleven tabs in §13.4's order; Payments stays "arrives in Phase 10"
(D141). *Rejected:* keeping nine tabs (Discussion and Evidence would be unreachable); appending the
two tabs at the end (breaks §13.4's order for no reason). The `workspace.test.tsx` placeholder
count and the `workspace-team` baselines change accordingly (reviewed by eye).

**D161 · The forecast's remaining time is computed exactly, not in binary floating point.** While
checking §18.2 against `algorithms/forecast.py` (Phase 4, pure, called by no service yet), the
Dashboard frontend (p = 0.4, elapsed 4 days) gives `remaining = max(8·0.6, 4·0.6/0.4)`; in float64
the second term is `5.999999999999999`, which `ceil` turns into 6 (forecast finish 18, as §18.2
says) only by luck — other progress values land a hair above an integer and `ceil` adds a whole
day (e.g. forecast 19, impact +3), so a monitored project could show a delay that doesn't exist.
§9.10's rule (ours, not [PCS]) is unchanged: `forecast finish = today + ceil(max(dur·(1−p),
e·(1−p)/p))`; only its arithmetic becomes exact: progress comes from `numeric(5,1)` estimates and
fixed weights, so it is a rational number, and the service passes it as a `Fraction` (from
`Decimal`) that the pure function uses for both terms before `ceil`. Unit tests pin the boundary
(remaining exactly 6 → 6, never 7) and a property test checks the exact and the old result agree
whenever the float error can't cross an integer. *Rejected:* rounding the float to n decimals
before `ceil` (an arbitrary tolerance that would also round genuine fractions); leaving it and
relying on the seed's assertion (the seed would pass while real projects could show a phantom
day). This changes `forecast.py`'s input type for `progress` (float → `Fraction | float`, floats
still accepted for existing tests) and adds tests; `milestone_progress` gains an exact variant.

**D162 · One notification catalogue; preferences per §12 row.** `app/core/notification_types.py`
defines `NotificationType` (StrEnum): every kind Phases 5–8 send plus Phase 9's (TASK_ASSIGNED,
TASKS_UNASSIGNED, MENTIONED, BLOCKER_REPORTED, CHECKIN_REMINDER, RISK_CRITICAL). Each type belongs
to exactly one `Category`, which is a §12 row (`bids_received`, `bidding_outcome`, `formation`,
`selected`, `bid_updates`, `invitation_responses`, `team`, `task_assigned`, `mentions`,
`blockers`, `checkin_reminder`, `critical_risk`, `verification`; the mapping table is in
`docs/plans/phase-09.md`). `notification_preferences.type` stores the category key, so one switch
in Settings covers one §12 row. Defaults follow §12's columns; email can only be switched on where
§12 has an email, except mentions (email exists, off by default, D153). `notify()` refuses
anything that isn't a `NotificationType`; a test checks every caller. *Rejected:* a preference per
type (about 30 switches nobody understands); keeping free strings (nothing stops a typo or an
unmapped kind).

**D163 · Preferences are enforced in the two writers.** `notify` becomes `async` and skips the
in-app row when the recipient switched its category off. `outbox.enqueue` gains `user_id` and
`notification_type`; the six account templates (`verify_email`, `reset_password`,
`account_exists`, `account_locked`, `new_device`, `password_changed`) form `ACCOUNT_TEMPLATES`,
are always sent and take no type; every other template must name a type and is skipped when the
category's email is off. A test lists every template and asserts it is an account template or
mapped. *Rejected:* a database trigger that silently drops rows (invisible in review, can't cover
email).

**D164 · Live notifications are published only after commit.** `notify` appends
`(user_id, id, type, title)` to `session.info["notif_pending"]`; a SQLAlchemy `after_commit`
listener publishes them to Redis channel `notif:{user_id}` and `after_rollback` discards them. A
rolled-back change never reaches a browser and no caller has to remember to publish. *Rejected:*
Postgres `LISTEN/NOTIFY` (§15.2 names Redis pub/sub, and it holds a database connection per
listener); publishing inside the service before commit (leaks rolled-back events).

**D165 · Debounced evaluation that never loses the last event.** After commit, task and milestone
changes do `ZADD NX mon:dirty <now> <project_id>`. A scheduler job `monitoring.flush` every 30 s
enqueues `monitoring.evaluate` for each project whose score is ≥ 30 s old and removes exactly that
member with that score (a Lua compare-and-remove), so an event arriving during the evaluation
re-adds the project and the next flush evaluates again. Worst case ≈ 60 s after the last event; the
15-minute sweep stays as the backstop. *Rejected:* `enqueue_in` (no RQ scheduler runs); sleeping
30 s inside a worker (ties up a worker per project).

**D166 · Workspace rows carry `project_id`.** `tasks`, `task_dependencies`, `task_evidence`,
`comments`, `checkins`, `discussion_threads` and `discussion_posts` store `project_id NOT NULL`;
a guard trigger checks it matches the parent (milestone, task, target, thread or team member) and
keeps it immutable. RLS policies are then one helper call per row (`is_participant(project_id)`)
and the §7.9 queries stay index-only. *Rejected:* joins inside every policy (slower and easy to
get subtly wrong).

**D167 · `activity_events.subject_id`.** A nullable column for the member an event is about when
that differs from the actor or there is no actor (`checkin.missed` and `member.left` written by
SYSTEM). The Evidence tab and Phase 11 aggregate on it; `data` holds no user ids except mentions
and reply targets. *Rejected:* the subject inside `data` (can't be indexed or constrained).

**D168 · Evidence kinds and immutability.** `FILE` references any live project file of the same
project; `SCREENSHOT` references an image project file; `LINK` and `PR` carry an `https://` URL
(D148). Evidence rows are immutable (no edit or delete; reputation evidence, like check-ins), and
the 20-per-task cap counts them. *Rejected:* a URL for screenshots (would mean trusting or fetching
remote images); deletable evidence (a member could erase evidence after a dispute starts).

**D169 · Comment and post revisions are captured by a trigger and readable only by admins.** A
`BEFORE UPDATE` trigger on `comments` and `discussion_posts` (definer, pinned `search_path`) copies
the old body into the revisions table. Participants see only the "edited" label, which keeps
earlier and deleted text private (D146) without per-row rules; the rows stay for Phase 12's
disputes. *Rejected:* showing edit history (not in §13.5, and it leaks text the author replaced).

**D170 · `make seed-demo DAY=N` without `STAGE` means stage 2.** §17 writes the command without a
stage, and only stage 2 has the Inventory project. `DAY` with `STAGE=1` is refused; `DAY` must be
3–20 so the fixed history fits. *Rejected:* requiring `STAGE=2` (breaks §17's literal command);
silently ignoring `DAY` on stage 1 (hides a mistake).

**D171 · The two new Phase 9 dependencies, pinned** (completes D157 and D158).
`@tanstack/react-virtual` **3.14.26** (published 2026-11-03, 24 days before pinning); its only
dependency is `@tanstack/virtual-core` (same family, no dependencies of its own), recorded here
because D158 said "no dependencies". ZAP: `zaproxy/zap-stable:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af`
(published 2026-11-03). *Rejected:* newer react-virtual 3.14.27/28 (5 days old, under the 14-day
rule); ZAP's `weekly` image (not a fixed release).

**D172 · Task writes require `If-Match`.** `PATCH /tasks/{id}`, `POST /tasks/{id}/move` and
`DELETE /tasks/{id}` refuse a missing `If-Match` with 422 (`fields.If-Match`), unlike bids where
it is optional: a board drag without a version could silently overwrite a teammate's concurrent
drop, and §13.7's rollback relies on the 409. *Rejected:* optional as for bids (lost updates on a
shared board).

**D173 · Evidence keeps its task, and project files follow the project, not the uploader.** Two
consequences of append-only evidence (D148, D168) and participant-only files (D142, D147), found
while writing migration 0016:
- A task that has evidence can't be deleted (409 `INVALID_STATE`, "This task has evidence
  attached, so it stays on the board"); `task_evidence.task_id` has no cascade, so the database
  refuses it too. D143 lets the lead delete any task that isn't DONE; evidence already attached is
  reputation evidence and can't vanish with it. *Rejected:* cascading the evidence away (breaks
  append-only); soft-deleting tasks (a hidden-row rule on every board query for a rare case).
- `file_access()` admits a project file to the project's participants and SYSTEM only — not its
  uploader after they leave the project, and not admins until Phase 12's disputes (D142 "files
  for admins come with Phase 12"). *Rejected:* keeping 0004's owner and admin access for project
  files (a former member could keep downloading the team's files; admins would get files before
  the dispute context exists).
- Smaller points fixed in the same pass: card positions sort with `COLLATE "C"` (byte order, so
  base-62 keys compare as numbers in any database locale); keys are appended with "the next digit
  up" rather than a midpoint, so 1,000 appends stay about 33 characters (a midpoint toward the
  end grows a digit every ~5 appends); `GET /projects/{id}/plan` moves to the `workspace.read`
  account gate so members pass it and the service decides (client, admin, or a participant).

**D174 · The Inventory dashboard seed's free details** (the parts §18.2 leaves open, D154).
- **Team:** Arif (React, the lead), Farhan (FastAPI), Nusrat (UI/UX) and Imran (Testing), one bid
  per place, so the formation run's team is forced. Each commits **10 hours a week** and has 30 or
  more on their profile. The ordering project starts in 3 days and overlaps this one, so its
  20-hour bids stay feasible: its 10 eligible bids and the D116 team can't move.
- **The inactive member is Nusrat:** UI design is done, so no unfinished critical milestone needs
  her skill (no SKILL_DEPENDENCY), and she has no task in progress (no STALLED_TASK). Her last
  activity is day 3 at about 22:30 Dhaka, so on day 12 she has been inactive 8 whole days at any
  hour of the day.
- **Exact progress:**
  - Inventory API: ten 2-hour tasks for Farhan, 7 done, so p = 0.7.
  - Dashboard frontend: ten 1.5-hour tasks for Arif, 4 done, so p = 0.4.
  - No task is left in progress.
  - Open hours (6 and 9) fit inside 10 hours a week, so CAPACITY doesn't fire.
- **Milestone skills:** Integration needs React and FastAPI; Testing needs Testing. Each is held by
  one active, recently active member, so SKILL_DEPENDENCY doesn't fire.
- **Rows not written through a service:** only the milestone transitions that Phase 10 will own
  (approvals and activating a successor), set by one commented SYSTEM helper.
- **History:** the bidding, the run, confirm, accept and the lead choice happen on day −1, and the
  start on day 0. A member never checks in twice in one week; Imran's day-9 blocker is answered
  by Farhan on day 10 (`blocker.answered`).
- **Result:** at day 12 the engine gives exactly forecast 25 (+2) and the documented four risks;
  the seed asserts it.

*Rejected:* using developers with fewer hours (Rafi, Zahid), because the overlap would make
their ordering bids infeasible; leaving a task in progress, because it would add a STALLED_TASK.

**D175 · Project files: the daily byte budget and Markdown names.** Decided by Claude Code
during the Phase 9 build (item 8), by the brief's order (spec intent, then secure).
- **The budget counter:** one Redis counter per user and Dhaka calendar day,
  `rl:upload_bytes:<hashed user>:<date>`. It sits under `rl:` with the other limits, so the
  test-only limit reset also clears it.
- **Reserve, then settle:** before the body is read, the request's `Content-Length`
  (capped at `MAX_UPLOAD_MB`) is reserved in one atomic script; without a usable
  `Content-Length`, the whole `MAX_UPLOAD_MB` is reserved. After the upload is stored, the
  counter is corrected to the stored size; a failed upload gives back everything it reserved.
  Two parallel uploads therefore can't both slip under the budget, as a check-then-charge would
  allow.
- **Over budget:** 429 `RATE_LIMITED` with `Retry-After` until midnight in Dhaka.
- **Redis down:** the budget fails closed with 503. The plan said the `upload` scope already
  fails closed, but it fails open (`FAIL_CLOSED_SCOPES` doesn't list it). It stays as it is
  (changing it isn't part of this phase). The budget is new and fails closed, because an
  unmetered disk is the thing it exists to prevent.
- **Markdown:** a file detected as plain text keeps a `.md` name when it was uploaded as `.md` or
  `.markdown`. It is still stored and served as `text/plain`, as an attachment, so it can't be
  rendered. Every other type gets the extension of its detected type, as before.

*Rejected:* a check-only budget (races between parallel uploads); naming every text file
`.txt` (it breaks the §14.9 "markdown" promise for no security gain).
- **The lead's delete and RLS:** PostgreSQL also checks an UPDATE's new row against the SELECT
  policies, and a soft-deleted project file was visible only to its owner. So a lead couldn't
  delete a member's file (500 in the API test). In 0016, `project_file_select` now also lets
  the project's lead see deleted rows of that project. Everyone else still can't, and the
  list and downloads hide deleted files for everyone (the service filters them, and
  `file_access()` checks `deleted_at`). *Rejected:* a SECURITY DEFINER delete function
  (it would repeat the uploader-or-lead rule in SQL); dropping the `deleted_at` condition for
  every participant (wider than needed).

**D176 · Notification delivery details (item 10).** Decided by Claude Code during the Phase 9
build, within D153 and D162–D164.
- **One path for every notice:**
  - Every in-app notification goes through `notify` / `notify_once` / `notify_users`. That
    includes the hourly new-bids notice, which used to insert rows itself and skipped both the
    switch and the live push. It now keeps its watermark through `notify(..., at=cutoff)`.
  - The recipient's switches are read in a short SYSTEM session (`notification_prefs.switches`),
    because the writer usually acts for someone else and RLS keeps preference rows to their
    owner.
  - `outbox.enqueue` reads the same switch for every non-account template.
- **The three new §12 emails:** `mentioned` (opt-in), `checkin_reminder` and `risk_critical`.
  They go with their notifications through `EmailSpec` and never quote message text.
- **Publishing:**
  - The `after_commit` listener publishes `{id, type, title}` with a small synchronous Redis
    client, because listeners can't await. A publish that fails is logged and skipped: the row
    is stored, and the browser catches up through `Last-Event-ID` or the 60 s refresh.
  - `after_rollback` drops the pending entries.
- **The stream:**
  - It subscribes first, then replays the notifications newer than `Last-Event-ID` (a
    notification id; at most 50; an unknown, malformed or foreign id replays nothing). Live
    messages already replayed are dropped.
  - The stream's length is the setting `SSE_MAX_SECONDS` (30 min). The test stack sets it to
    2 s so tests get complete responses; the production default is unchanged.
- **Known limit:** with someone's in-app switch off there is no row to de-duplicate against.
  So a job re-run for the same occasion (the Monday reminder, for example) can email twice.
  The jobs that de-duplicate this way run once per occasion.

*Rejected:* publishing from an asyncio task created in the listener (an RQ job's event loop
ends before it runs); polling the database from the stream (holds connections, D107).

**D177 · How the DAST step runs (item 12, completes D157).** Decided by Claude Code during the
Phase 9 build.
- **An Automation Framework plan, not `zap-baseline.py`:** `backend/scripts/zap_scan.py` writes
  ZAP's own plan, which gives exact control over:
  - the context and its exclusions: the test-only router, sign-out, both SSE streams and signed
    blob URLs;
  - the session, added to every request by the `replacer` job;
  - explicit start requests: the main signed-in pages, a workspace and the API reads behind
    them;
  - both spiders, two minutes each.

  Only passive rules run: nothing is attacked or changed.
- **Target:** ZAP runs in Nginx's network namespace against `https://localhost:8443`. That is
  the test stack's `PUBLIC_ORIGIN`; the day-one trial aimed at port 443, where nothing listens.
  ZAP's own proxy listens on 8099, because 8080 is Nginx's.
- **The session:**
  - `backend/scripts/zap_session.py` seeds a throwaway verified developer through the
    test-only router and signs in through Nginx, as a browser would.
  - The cookie travels on stdout to the scan script and into the plan file. The plan file is
    deleted when ZAP ends. No log, report or summary contains the cookie; failures print only
    the error code.
- **TLS:** ZAP accepts any upstream certificate, and the test stack's is self-signed. ZAP has no
  per-target switch, so the limit is the target itself: the scan only ever talks to the test
  stack inside its own network. TLS stays on.
- **Pass rule:**
  - any High or Medium alert fails;
  - `infra/zap/ignore.json` may list an alert only with a DECISIONS entry that exists, and the
    script checks that it does;
  - the list starts empty.

  Reports go to `runs/zap/<timestamp>/` (JSON, HTML, a one-line summary and ZAP's output).
- **`--offline`:** records N/A, as step 7 does.

*Rejected:* `zap-baseline.py` with `-z` replacer flags (the cookie would show in the process
list, and there's no way to exclude paths from the spider); an API key instead of a session
(the app has none, and adding one for a scanner would widen the attack surface).
