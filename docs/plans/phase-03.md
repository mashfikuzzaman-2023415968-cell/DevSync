# Phase 3 — Profiles, portfolio, files, skill tests (plan)

## Context
Phases 0–2 are done (gates PASS, tags `phase-0..2`, pushed). Phase 3 (spec §17 "Phase 3") gives developers and clients complete profiles, handles uploaded files safely, and lets newcomers earn verified skill evidence through timed tests — the evidence Phase 5's filtering and the newcomer rule rely on. The student will hand Phases 4–5 to a teammate afterwards, so Phase 3 ends with the first hand-off document (§0.5). Outcome: `make gate PHASE=3` → `PHASE 3 GATE: PASS`; commit `phase-3: …`, tag, push.

Read: §7.2 (+ `external_reviews` from §7.7, generic `files`), §10 Profiles/Skills/Tests/Files, §13.5 screens 7, 14–15, 19, §14.9, §14.13 row 3, §14.15 policies, §16.4 uploads/IDOR/mass-assignment/injection. Skills: `devsync-ui` + `frontend-design` for every screen.

## Dependencies (DECISIONS D29)
Backend (spec-named in §14.9): `python-magic` (+ `libmagic1` in the API image) for signature checks, `Pillow` for re-encoding. Frontend: `@dnd-kit/core` + `@dnd-kit/sortable` (spec-named for drag; used here for portfolio reordering, keyboard sensor included). Crop preview without a new library: the client shows exactly how the server will crop/fit the image (CSS `object-fit` frame), the server stores the re-encoded original — recorded in D29.

## Database — migration `0004_profiles_files_tests`
- Tables (§7.2, §7.7): `skills` (name, domain enum, active), `developer_profiles`, `developer_skills` (UNIQUE user+skill, level 1–5), `client_profiles`, `files` (owner_id, kind: PORTFOLIO_IMAGE/CERTIFICATE/EXTERNAL_REVIEW, storage_key uuid, original_name sanitized, mime, size, width/height, sha256, scan_status, attached_at, deleted_at), `portfolio_items` (≤ 20/user, position), `portfolio_images` (≤ 5/item), `certificates`, `external_reviews` (status PENDING/VERIFIED/REJECTED), `question_bank` (4 options, correct_index, difficulty, active), `skill_tests`, `test_attempts` (question_ids, answers jsonb, started_at, deadline_at, submitted_at, score numeric(4,3), scored), `skill_evidence` (source TEST/…, score). Coding challenges stay in Phase 13.
- RLS (ENABLE + FORCE) per §14.15: profiles own row / admin; evidence-type tables owner + admin; `question_bank` **admin + SYSTEM only** — web requests read questions only through a SECURITY DEFINER `test_questions(attempt_id)` that returns text + options for the caller's own open attempt (never `correct_index`); scoring through a definer `score_attempt(attempt_id)` so answers never leave the database. `skills`, `skill_tests` exempt (public taxonomy) in `rls_exempt.yml`. Public profile through a `public_profiles` view/definer returning only public fields and honouring `visibility`.
- Seed (data migration, frozen JSON in `alembic/seed/`): the 8 spec skills (React, Node.js, FastAPI, PostgreSQL, UI/UX, Testing, Flutter, DevOps with domains), one 10-question/600-second test per skill, and a question bank of **≥ 15 questions per skill (120+)** drafted by me — flagged in the hand-off for a team member to review for accuracy.
- Indexes: `test_attempts(user_id, test_id, started_at)`, `files(owner_id)`, `skill_evidence(user_id, skill_id)`.

## Backend
- `app/uploads/` (security-critical, ≥ 95% coverage): streaming receive to a temp file with a running size limit (never in memory), `python-magic` signature allowlist (PNG/JPEG/WebP; PDF ≤ 10 MB; plain text ≤ 1 MB; nothing else, no ZIP/SVG), Pillow: `MAX_IMAGE_PIXELS` bomb guard, verify + re-encode (drops EXIF/GPS/ICC metadata), longest side ≤ 4096 px; PDFs stored as-is, never rendered; random UUID storage key, 0600 permissions, name sanitized and kept as metadata only (no user-controlled paths). Signed download: `GET /files/{id}/download` → authorization → 302 to `/api/v1/files/blob?…&exp=…&sig=…` (HMAC-SHA256 key derived from SECRET_KEY, 5-minute expiry) → the API answers with `X-Accel-Redirect` into the existing Nginx `internal` `/_protected_files/` location (attachment, nosniff, CSP sandbox). Orphan cleanup job (unattached > 24 h). Optional scan hook records `scan_status=SKIPPED`.
- Services/endpoints (§10): `GET/PATCH /me/developer-profile`, `PUT /me/skills`, CRUD `/me/portfolio` (+ reorder) and `POST /me/portfolio/{id}/images`, CRUD `/me/certificates`, CRUD `/me/external-reviews` (status stays PENDING; admin verification arrives with the Phase 12 console), `GET/PATCH /me/client-profile`, `GET /skills`, `GET /developers/{id}` (session; role-aware), `GET /public/developers/{id}` (limited, visibility), `GET /skill-tests`, `POST /skill-tests/{id}/attempts`, `GET /attempts/{id}`, `POST /attempts/{id}/answer`, `POST /attempts/{id}/submit`, `GET /files/{id}/download`. All requests `extra="forbid"`; bounds from §7.2; rate limits `upload`, `test_start` (existing settings).
- Tests flow: attempt start picks 10 random active questions (seed stored), deadline = start + 600 s (server clock); answers rejected after the deadline (409 `INVALID_STATE`); submit scores via the definer, writes `skill_evidence`; one scored attempt per test per 30 days (409 with the next allowed date); expired unsubmitted attempts auto-scored by a job; no practice mode.
- Audit entries for profile changes, uploads, attempts. OpenAPI + `check_openapi` + authz matrix + schemathesis cover every new operation (uploads fuzzed with multipart).

## Frontend (devsync-ui patterns, mobile-first)
- **Profile & Portfolio** `/dev/profile` (screen 15): basics, skills with level selectors, availability, GitHub username, visibility; portfolio items with drag-to-reorder (@dnd-kit + keyboard + "Move up/down" menu) and image uploads (dropzone with progress, type/size hints, crop/fit preview); certificates and external reviews (upload → "Pending admin verification"); autosave with a "Saved" indicator.
- **Skill Challenges** `/dev/challenges` and **Timed test** `/dev/challenges/test/:attemptId` (screen 14): list with last score and next-attempt date; one question per screen, large radio cards, counter, countdown (amber < 60 s, danger < 15 s; server time is the source), progress bar, submit with confirm; score ring + "added to your profile".
- **Public developer** `/d/:id` (screen 7) and the client profile part of Settings (screen 19); developer dashboard checklist items become real (portfolio, skill test).
- New components: `FileDropzone`, `CountdownTimer`, `SortableList`; reuse `components/ui/*`, `PageHeader`, `EmptyState`, `RingProgress`, `toast`.

## Security (§14.13 row 3)
RLS for profile, file and test tables (+ cross-user tests per table); upload pipeline (signature, re-encode, size, bomb guard, signed URLs, no path control); profile field validation and injection corpus inert; test timer server-side; correct answers never in any API response (schema assertion); attempt limits; IDOR → 404; mass assignment (`user_id`, `status`, `score`, `scored`, `correct_index`) → 422; PII (phone) never on public profiles.

## Tests
- Unit: upload validators (each type, wrong signature, polyglot JPEG+ZIP/PDF+HTML, oversize, bomb, EXIF/GPS stripped, path-like names), signing (expiry, tamper), scoring, retake window, visibility rules, schemas.
- Integration/RLS: every new table cross-user; definer functions expose only intended columns; GUEST sees only public views.
- API/security: lifecycle (deadline passes mid-attempt, double submit, answer after deadline, retake within 30 days), answers absent from every test-related response, IDOR, mass assignment, injection corpus in profile fields and filenames, signed URL expiry/tamper, authz matrix, schemathesis.
- Jobs: orphan cleanup, auto-submit of expired attempts.
- Frontend: dropzone, countdown (fake timers, colour thresholds), sortable list (keyboard), forms, autosave.
- E2E (Chromium): developer completes profile with a portfolio image, takes a test, sees the score on the profile; client edits profile; public profile respects visibility; responsive matrix, axe and CSP on the new screens; visual baselines for the new screens.

## Gate (P3 additions)
`phase3_checks`: upload of a crafted polyglot rejected; a signed URL expires (and a tampered one is refused); test answers absent from API responses; plus Phase 1–2 checks. `uploads/*` added to the ≥ 95% security-critical coverage list. New screens join the responsive matrix, axe, CSP and visual steps.

## Housekeeping
Save as `docs/plans/phase-03.md`; DECISIONS D29 (deps, crop preview, question-bank review); API/SECURITY/TESTING docs; `/security-review` → `docs/security-reviews/phase-03.md`; PROGRESS.md; commit `phase-3: …`, tag `phase-3`, push. Then the **hand-off document** `docs/handoffs/handoff-01-taeen-to-<name>.md` (§0.5 template) and `docs/OWNERSHIP.md` update for the Phase 4–5 owner.

## Verification
`make gate PHASE=3` prints `PHASE 3 GATE: PASS`. Manual (§17): upload a photo with GPS EXIF, download it, confirm the metadata is gone; take a skill test and see the score on the profile.

## Risks
Upload pipeline correctness (polyglots, Nginx X-Accel path) — most tested part; question-bank accuracy (needs human review); `libmagic` in the slim image (Trivy must stay clean).
