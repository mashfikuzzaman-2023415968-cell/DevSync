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
newer than 14 days only to fix a published vulnerability, recorded here with the CVE source.

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
That alone was not enough: the app scrolls smoothly (`scroll-behavior: smooth`, kept for the
homepage anchors), so in Firefox the scroll Playwright starts to bring an element into view was
still animating when it clicked (~1 in 10 runs). `clickSettled()` (e2e/test.ts) scrolls the
element into view, waits until the page stops scrolling, then clicks; used for below-the-fold
clicks in the profile and Settings tests (44/44 repeated runs on three engines). (7) Search input: schemathesis
sent `q=\x00…` to `GET /public/projects` and got a 500 (PostgreSQL rejects NUL in text).
`services/marketplace.search` now cleans `q` and each skill name like profile one-line fields
(control characters removed, NFC, trimmed, empties dropped) and allows at most 20 skill filters
(422 `skills: too_many`). (6) gitleaks scans the working tree
(`--no-git`), so after any failed E2E run the next gate failed step 5 on Playwright traces in
`frontend/test-results/` (115 `generic-api-key` hits, all session cookies of the throwaway test
stack). That folder and `frontend/playwright-report/` are gitignored generated output, so they
join the allowlist next to `frontend/dist/`, `frontend/coverage/` and `runs/`; tracked files are
scanned exactly as before.
