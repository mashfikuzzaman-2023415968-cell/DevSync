---
name: devsync-ui
description: DevSync's own design system (spec §13): tokens, typography, spacing, page-header and card patterns, the component library in frontend/src/components, the motion catalogue in design/motion.ts, responsive rules, microcopy, the 3D hero rules and the consistency system. Use it for EVERY DevSync frontend task — any new or changed screen, component, form, dashboard, chart, empty or error state, copy on a button, animation, or anything in frontend/src — even small tweaks, and load it together with frontend-design (devsync-ui wins where they disagree). Also use it when reviewing a screen against the visual quality bar or preparing a demo gallery.
---

# DevSync UI

DevSync should look like one calm, modern SaaS product (Linear, Stripe Dashboard, Vercel):
generous white space, clear hierarchy, restrained colour, crisp type, purposeful motion. Every
screen is built from the same parts, so the app feels like one thing and later phases are fast.
This skill is the short, practical version of spec §13; the spec stays authoritative.

Before writing UI, skim the files you will use: `frontend/src/components/ui/*`,
`frontend/src/components/shell/*`, `frontend/src/design/{tokens.ts,motion.ts,preferences.tsx}`,
`frontend/src/lib/format.ts`. Reuse them; don't create one-off buttons, inputs or modals.
For the full component and screen tables read `references/components.md`.

## Tokens (never hard-code colours)

Colours are CSS variables from `design/tokens.css` (mirrored in `tokens.ts`, contrast-tested in
`contrast.test.ts`), exposed as Tailwind utilities: `bg-bg`, `bg-surface`, `bg-surface-2`,
`border-border`, `text-text`, `text-text-muted`, `text-text-subtle`, `bg-primary`,
`text-on-primary`, `bg-primary-soft`, `text-accent`, `bg-newcomer-bg text-newcomer`, and
`success|warning|danger|info` each with a `-bg` partner, plus `--chart-1..6`.

- Teal `primary` = brand, primary buttons, active nav, links, focus. Indigo `accent` = data
  visualisation. Amber `newcomer` = newcomer badges and the fairness dial. Rose `danger` =
  critical path, critical risks, destructive actions.
- `text-subtle` is AA only on `surface` (D10); on `bg` use `text-muted`.
- Never more than three accent colours on one screen. Status is never colour alone: always
  icon + text (`Badge`, `RiskChip`, `Alert` already do this).
- Dark theme comes from the same tokens (`data-theme` / OS); never write `dark:` colour
  overrides for token colours. New tokens go in both themes and in the contrast test.

## Type, spacing, radius, elevation

- Inter (400/500/600/700); JetBrains Mono only for code and ids. Scale utilities:
  `text-caption` 12, `text-body-sm` 14, `text-body` 16, `text-lead` 18, `text-h4` 20,
  `text-h3` 24, `text-h2`/`text-h1`/`text-hero` (fluid clamp). One `h1` per page.
- Numbers in tables, stats and money: `tabular`. Money: `formatMoney(paisa)` → `৳12,500`
  (paisa integers only). Dates `formatDate` → "12 Oct 2026" (Asia/Dhaka); relative times
  `formatRelative` with the full date in a `title`/tooltip. Scores stored 0–1 are shown
  0–100 with `formatScore`; percentages one decimal max; big counts `formatCount` (12.4k).
- 4 px grid (4, 8, 12, 16, 20, 24, 32, 40, 48, 64). Radius: `rounded-md` inputs/buttons,
  `rounded-lg` cards, `rounded-xl` dialogs and hero cards, `rounded-full` badges/avatars.
- Elevation `shadow-xs|sm|md|lg` (theme-aware; dark uses borders more than shadows).
- Focus: the global 2 px primary ring with 2 px offset on `:focus-visible`; never remove it.

## Page pattern (spec §13.8)

Every signed-in page renders inside the role shell (`RoleShell` → `AppShell`) and starts with
`PageHeader`: breadcrumb (when nested) → `h1` (24/32, 600) → one-line description → one
primary action on the right (full-width under the title on phones). 24 px gap to content.

Content sits in `Card` (surface, radius 12, 1 px border, shadow-xs) on the `bg` background,
24 px gutters, max two columns on dashboards at ≥ 1280 px (8/4:
`xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]`), one column below 1024 px.

One primary button per view; secondary actions `outline` or `ghost`; destructive actions use
`variant="destructive"` and always go through `ConfirmDialog` (type-to-confirm for serious
ones, explaining the consequence).

Every data view has four states — build all of them:
- loading: `Skeleton` blocks shaped like the final layout (no spinner longer than 300 ms);
- empty: `EmptyState` (icon or `NodeArt`/`Still`, one-sentence explanation, primary action);
- error: `ErrorState` (what happened, Try again, request id from `ApiError.requestId`);
- success: a `toast({ tone: "success", title })` or inline confirmation.

Data fetching only through TanStack Query hooks in `features/*/api.ts`; forms with React Hook
Form + Zod schemas mirroring the backend; map server field errors with `applyFieldErrors`.
Mutations that show their own errors set `meta: { inlineErrors: true }`; otherwise 403/429
toasts come from `app/queryClient.ts`.

## Components (use these)

`Button` (primary, secondary, outline, ghost, destructive, link; sm/md/lg; `loading`; `asChild`
to style a router `Link`), `IconButton` (aria-label required), `Field`/`FormField`/`Input`/
`Textarea` (counter), `Select`, `Combobox`, `Checkbox`, `RadioGroup` (`cards` for big choices),
`Switch`, `Slider` (value label), `SegmentedControl`, `Card`/`CardHeader`, `StatCard`
(count-up), `Badge`, `NewcomerBadge`, `RiskChip`, `Avatar` (initials, newcomer ring), `Tabs`,
`Accordion`, `Breadcrumbs`, `Dialog`, `ConfirmDialog`, `Sheet` (right; `side="bottom"` on
phones), `Popover`, `Tooltip` (also opens on tap/focus), `DropdownMenu`, `toast`, `Skeleton`,
`EmptyState`, `ErrorState`, `Alert`, `Stepper`, `Progress`, `RingProgress`, `OtpInput`,
`PasswordMeter`. Icons: lucide, 16 px inline / 20 px in buttons and nav, always with text
except well-known icon buttons (close, more, search) which need `aria-label`.

Domain composites (Gantt, DependencyGraph, KanbanBoard, ReputationPanel, TeamCard,
FairnessDial, PrioritySliders, ConvergenceChart, RiskList, EscrowTimeline, SplitEditor …) are
built in their phases under `components/` from these primitives; see `references/components.md`.

## Motion (spec §13.2, §13.13)

All motion comes from `design/motion.ts` via `useMotion()` (variants already reduced for the
user's setting): `page`, `card`, `list`/`listItem` (30 ms stagger, max 8), `reveal`, `dialog`,
`overlay`, `sheetRight`/`sheetBottom`, `shake` (form errors), `swap` (cross-fades),
`meterTransition` (400 ms), `indicatorTransition` (180 ms); durations 120/180/280/220 ms; easing
`ease.standard|emphasized|exit`; Tailwind `duration-fast|base|slow|page|crossfade` and
`ease-standard|emphasized|exit`. Radix overlays animate with `anim-overlay`, `anim-pop`,
`anim-sheet-*`, `anim-toast`.

- An ESLint rule rejects numeric `duration`/`delay` values and `duration-300`-style classes
  outside `motion.ts`; add a named token there instead of a number.
- Transform effects (hover lifts, press scale) use the `motion-ok:` variant so they disappear
  under reduced motion. Reduced motion (OS or in-app) means: no transforms, shimmer,
  count-ups, drawing or parallax; ≤ 120 ms opacity fades; content shows its final state.
- Nothing bounces or loops except the PSO swarm indicator while a job runs. Motion never
  blocks interaction or delays content more than 300 ms. Avoid Framer `popLayout` (it injects
  a `<style>` tag).

## Responsive (spec §13.14 — a screen that only works on a laptop is unfinished)

Mobile-first. Breakpoints sm 640, md 768, lg 1024, xl 1280, 2xl 1536. Check every screen at
375×667, 390×844, 768×1024, 1366×768, 1440×900 in light and dark (the gate's viewport matrix
asserts: no horizontal overflow, no overlapping interactive elements, ≥ 44 × 44 px touch targets
on touch sizes — labels count towards a control's target; inline links inside a sentence are
exempt — and no clipped text).

- ≥ 1024: top bar + sidebar (248 → 72 px rail); 768–1023: rail; < 768: compact top bar and
  bottom tab bar (4 destinations + More sheet). Workspace tabs scroll horizontally.
- Tables become card lists; dialogs become bottom sheets; wizards show "Step 3 of 6" with a
  sticky Back/Continue bar; dashboards stack, stat cards 2×2; charts full width with a
  "View as table" toggle.
- Body text ≥ 16 px on phones, inputs 16 px (no iOS zoom), correct `inputMode`,
  `autoComplete`, `enterKeyHint`; `100dvh`, `env(safe-area-inset-*)`; no hover-only features.

## Accessibility (WCAG 2.1 AA, spec §13.6)

Keyboard access everywhere, visible focus, a label for every control (`FormField` wires
`aria-describedby`/`aria-invalid`), `aria-live="polite"` for toasts, progress and form errors,
skip link, document titles `<Page> · DevSync` via the route `handle.title`, charts with table
alternatives, 200 % zoom without horizontal scrolling. axe runs on every screen in the gate.

## Microcopy (spec §13.10)

Plain, friendly, specific, second person, sentence case. Buttons are verbs that say what
happens ("Form team", "Approve and release payment"), never "Submit"/"OK", and keep the same
name through the flow ("Publish" → toast "Published"). Numbers instead of vague words
("2 days late"). Every algorithmic result gets one sentence of "why". Errors say what happened
and what to do next, without apologising. Paper terms (C3, Eq. 11) only in admin/explanation
drawers. Use curly apostrophes (’) in UI copy. No ALL-CAPS labels or "A · B · C" meta strings.

## 3D and stills (spec §13.12–13.13)

The only WebGL in the app is the homepage hero (`components/three/TalentConstellation.tsx`,
React Three Fiber, colours from `design/tokens.ts`, lazy chunk ≤ 220 KB gzip through the slim
`three` entry, D25). Poster first (drawn on a 2D canvas so the headline stays the LCP element),
live canvas cross-fades in; fallbacks to the poster for reduced motion, no WebGL, data saver,
< 4 cores or a lost context; paused off screen. No remote models/HDRs, no other 3D libraries.

Everywhere else reuse the identity through stills (`Still` with `hero-poster`/`team`) and the
2D `NodeArt` motif. After changing the scene or tokens run `make stills` (the gate compares the
manifest hash). Homepage numbers must come from real data or a real algorithm run (rule 0.2.6;
until Phase 7 the hero chip and fairness dial show no percentages, D21).

## Security rules that touch UI (spec §13.7, §14.3)

Strict CSP: no inline scripts or styles in HTML, no `dangerouslySetInnerHTML`, no `eval`, no
external URLs, no CSS-in-JS or libraries that inject `<style>` (Radix scroll lock uses the
per-response nonce, D23). User text renders as text. Dev-only pages (`/dev/ui-kit`,
`/__stills`) are behind `DEV_TOOLS` and never ship.

## Before calling a screen done

1. Page header pattern, cards, one primary action, all four data states.
2. Light + dark, five viewport sizes, reduced motion.
3. Keyboard-only pass; axe clean; touch targets.
4. Copy checked against the microcopy rules.
5. Unit/component tests (states, keyboard, aria) and, for demo paths, a Playwright flow and
   visual baselines (`make visual-update`, review the diff).
