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
