# Security review — Phase 2 (Design system, app shell, landing page)

- **Date:** 2026-10-17
- **Reviewer:** Claude Code (`/security-review` method on `main...phase-2`, ~190 files), with
  Mashfikuzzaman Taeen. Done in the main session (full context of the code).
- **Scope:** CSP nonce path (Nginx + `lib/nonce.ts`), new endpoints `/public/stats` and
  `/client-errors`, migration 0003 (`public_stats()` SECURITY DEFINER), test-only rate-limit
  reset and its environment-gated exemption, frontend error reporting, fetch wrapper feedback,
  route/role shells and the admin chunk, dev-only routes, 3D hero and the slim `three` entry,
  stills, robots/Open Graph.
- **Tester's human check (spec §14.22):** _pending (Sara Binte Shafayet)_

Unresolved high findings: 0

## Result of the review

No high-confidence (≥ 8/10) vulnerabilities were found.

| Area | Conclusion |
|---|---|
| CSP | `script-src 'self'` unchanged (no nonce, no `unsafe-*`). `style-src` gains a per-response nonce from `$request_id` (128 random bits, new per response, `index.html` is `no-store`); the client accepts only a 32-hex value. Exact header and nonce/page match are tested at the edge; every screen (with dialogs, menus, palette open) is checked for violations in E2E. |
| XSS / DOM sinks | No `dangerouslySetInnerHTML`, `innerHTML` or `eval` in app code; user text rendered as text; the drei `Html` chip renders a fixed string through React. Zod runs `jitless` (no `new Function`). |
| `/public/stats` | Aggregate count only via a SECURITY DEFINER function with a pinned `search_path`, EXECUTE granted to app/worker only; RLS on `users` unchanged; cached JSON contains only the count (tested). |
| `/client-errors` | Anonymous allowed but CSRF + Origin required, body ≤ 8 KB (requires Content-Length), `extra="forbid"` with length/pattern limits, rate-limited per IP; control characters, query strings, fragments and secret-like strings removed before logging; nothing stored or echoed. |
| Test-only router | Still mounted only when `DEVSYNC_ENV=test` (tested). The global-limit exemption for `/api/v1/__test__` is passed only in the test environment and asserted absent in development/production; production limits are unchanged. |
| Authorization | Role shells only decide what to show; the server still enforces every route (authz matrix includes the two new public operations). Admin navigation lives in the admin chunk, loaded only after `/admin/session` succeeds. |
| Supply chain | New packages pinned exactly, ≥ 14 days old, `npm audit` clean; the slim `three` entry re-exports genuine three.js classes and a test proves coverage of every member the libraries use. No remote models, environments or fonts (no off-origin requests, tested). |
| Information exposure | Dev-only UI kit and stills renderer are compiled out (gate greps `dist/`); `dist/.vite/manifest.json` removed from the image; `robots.txt` lists only path prefixes already public in the SPA. |

## Findings fixed during the phase (found by tests and this review)

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | Zod 4's `new Function` probe caused `script-src` CSP violations on every form page (blocked, but noisy and a sign of eval use). | **Fixed:** `z.config({ jitless: true })`; test asserts it. |
| 2 | Low | Radix scroll lock injected `<style>` elements that the strict CSP blocked (dialogs and sheets lost scroll lock). | **Fixed:** per-response style nonce (D23). |
| 3 | Low | A global-limit exemption for the test router would have been unsafe if enabled in every environment (unlimited requests to a non-existent path). | **Fixed by design:** exemption is configured only in the test environment; tested. |
| 4 | Low | The Nginx image was built from the repository root without a `.dockerignore`, so `.env` (secrets), `.git` and `node_modules` were sent to the Docker daemon as build context (not copied into the image, which takes only `frontend/` and `infra/nginx/`). | **Fixed:** root `.dockerignore` allowlist. |
| 5 | Info | Client error reports could include query strings (reset tokens) or secret-like strings in messages. | **Fixed:** browser sends only the path; server strips queries, fragments and long opaque strings again. |

## Accepted / carried forward

- The style nonce equals Nginx's request id, which also appears in internal access logs; it only
  authorizes styles for that one response, and log access is outside the threat model.
- Phase 0–1 accepted items unchanged (lockout DoS by email knowledge; Redis password on the
  command line and dev TLS key mode in development).
