# Security review — Phase 3 (Profiles, portfolio, files, skill tests)

- **Date:** 2026-10-18
- **Reviewer:** Claude Code (`/security-review` method on `main...phase-3`, ~110 files; a
  sub-agent did the vulnerability pass, findings filtered at confidence ≥ 8/10), with
  Mashfikuzzaman Taeen.
- **Scope:** migration 0004 (tables, RLS policies, SECURITY DEFINER functions, guard triggers),
  the upload pipeline (`app/uploads/*`), signed downloads and the Nginx `internal` location,
  profile/portfolio/evidence/file/skill-test endpoints and services, authorization policies,
  the upload body limit, jobs, and the new frontend screens and upload client.
- **Tester's human check (spec §14.22):** _pending_

Unresolved high findings: 0

## Result of the review

No high-confidence (≥ 8/10) vulnerabilities were found.

| Area | Conclusion |
|---|---|
| Signed downloads | HMAC-SHA256 (key derived from `SECRET_KEY`) over storage key, type, name and expiry; constant-time compare; expiry capped at 2 × TTL. Type allowlisted at signing and serving; name sanitized and percent-encoded; always `attachment`. The key is a typed UUID, so the `X-Accel-Redirect` path can't escape `/_protected_files/`, which is `internal`, GET/HEAD only, `nosniff`, sandbox CSP, CORP same-origin. |
| `file_access` | Owner, admin or worker; portfolio images only when attached and the profile is visible to the caller; deleted files excluded. Certificates and review evidence are never public. Files can only be attached through a fresh upload by their owner. |
| RLS and definers | Every definer pins `search_path`; EXECUTE revoked from PUBLIC. `question_bank` admin/SYSTEM only; `attempt_questions` never returns answers. Attempts and evidence are written only by definers filtered to `app_uid()`; `caller_is_system()` checks `session_user`, so the web role cannot claim SYSTEM (D36, tested). Triggers block self-verification and changes to a stored file's identity (D35). Taxonomy tables are read-only for runtime roles. |
| Timed tests | Server clock only; deadline checked under `FOR UPDATE`; answers limited to the attempt's questions and choices 0–3; late submit scores only answers stored in time; one open attempt (advisory lock) and one scored attempt per 30 days. Responses carry no answer fields (schema assertion). |
| Uploads | Type by libmagic with per-kind allowlists (no SVG/HTML/ZIP); polyglot, markup and PDF-action checks (escaped names, compressed streams, inflate budget); Pillow re-encode under a pixel budget strips EXIF/GPS (checked end to end through Nginx); random keys, `O_EXCL`, 0640, no user input in paths. |
| Mass assignment / IDOR | Strict request schemas (unknown fields → 422); only sent fields applied; every lookup scoped to the caller and enforced again by RLS; other users' objects → 404 (tested per endpoint, plus the authz matrix). |
| Frontend | No unsafe DOM sinks; link URLs are `https://` only (server schema + DB CHECK); GitHub links use a fixed host with an encoded, validated username; uploads send CSRF token and credentials. |
| Body limit | Larger limit only for POSTs to the three upload paths (anchored match); all other requests keep 256 KB (tested). |

## Findings fixed during the phase (found by tests and this review)

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | `is_system()` checks `current_user`, which inside a SECURITY DEFINER function is the owner — the worker could not score expired attempts, and a naive fix (trusting `app.role` alone) would have let the web role act as SYSTEM. | **Fixed:** `caller_is_system()` (D36); tests prove the web role is refused and the worker succeeds. |
| 2 | Medium | Owners had an UPDATE policy on certificates/external reviews and files: with a future code path they could have set `status = VERIFIED` or swapped a file's storage key. | **Fixed:** `guard_verification` and `files_identity_immutable` triggers (D35); tested directly as the web role. |
| 3 | Low | Unverified (PENDING) client accounts would have been treated as clients by `profile_visible`, exposing clients-only developer profiles to unverified sign-ups. | **Fixed:** the caller must be ACTIVE; tested. |
| 4 | Low | PDFs could hide actions with hex-escaped names or inside compressed object streams. | **Fixed:** names decoded and Flate streams inflated (bounded) before checking; tested. |
| 5 | Low | Two parallel starts of the same test could both pass the "one open attempt" check. | **Fixed:** transaction-level advisory lock in `start_test_attempt`. |
| 6 | Info | The uploads volume was root-owned and world-readable (0755). | **Fixed:** owned by the API user, 0750 directory, 0640 files; Nginx reads through group 10001. |

## Accepted / carried forward

- A signed link works for anyone who holds it during its 5-minute life (it is issued only after
  authorization and bound to one file). By design (D32).
- Images are scanned for foreign signatures over their whole body; a random byte sequence in
  compressed image data can very rarely cause a false rejection (the person can re-save the
  image). Safety wins over convenience here.
- The ClamAV hook is not enabled (`scan_status = SKIPPED`); images are re-encoded and PDFs are
  never rendered on the server, and every download is an attachment with a sandbox CSP.
- Phase 0–2 accepted items unchanged.
