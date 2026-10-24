# UI guide

Generated from spec §13 and describes the design system **as built through Phase 5**. The spec
stays authoritative; the working version for Claude Code is the project skill
[`.claude/skills/devsync-ui/SKILL.md`](../.claude/skills/devsync-ui/SKILL.md) (with
`references/components.md`), which every frontend task loads together with `frontend-design`.

Source files:

| What | Where |
|---|---|
| Colour tokens (light + dark) | `frontend/src/design/tokens.css`, mirrored in `tokens.ts`, checked by `contrast.test.ts` |
| Type scale, radii, easings, duration utilities, keyframes | `frontend/src/index.css` (Tailwind 4 `@theme`) |
| Motion catalogue | `frontend/src/design/motion.ts`, `useMotion.ts` |
| Theme and reduced-motion preferences | `frontend/src/design/preferences.tsx` (`ds-theme`, `ds-motion`) |
| Primitives | `frontend/src/components/ui/*` |
| Shell | `frontend/src/components/shell/*`, `frontend/src/app/RoleShell.tsx` |
| Domain composites | `frontend/src/components/{Gantt,DependencyGraph,CpmTable}.tsx` |
| Brand, stills, 3D | `frontend/src/components/brand/*`, `frontend/src/components/three/*` |
| Formatting | `frontend/src/lib/format.ts` |
| UI kit (dev only) | `/dev/ui-kit` when built with `DEV_TOOLS` (`features/devtools/UiKitPage.tsx`) |

## 1. Look and feel

One calm, modern SaaS product: generous white space, clear hierarchy, restrained colour, crisp
type, purposeful motion. Every screen is built from the same parts.

## 2. Colour tokens

Colours are CSS variables exposed as Tailwind utilities (`bg-surface`, `text-text-muted`,
`bg-primary`, …). Never hard-code a colour; never write `dark:` overrides for token colours —
the dark theme comes from the same tokens (`data-theme` on `<html>`, or the OS).

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` / `surface` / `surface-2` | #f7f8fa / #ffffff / #f1f5f9 | #0b1220 / #111827 / #1e293b | page / cards / wells |
| `border` | #e2e8f0 | #273449 | 1 px borders |
| `text` / `text-muted` / `text-subtle` | #0f172a / #475569 / #64748b | #e5e7eb / #a1a1aa / #94a3b8 | body / secondary / tertiary (subtle only on `surface`, D10) |
| `primary` (+ `-hover`, `-soft`, `on-primary`) | #0f766e | #2dd4bf | brand teal: primary buttons, active nav, links, focus |
| `accent` | #4f46e5 | #818cf8 | indigo: data visualisation |
| `newcomer` (+ `-bg`) | #b45309 | #fcd34d | amber: newcomer badges, fairness dial |
| `success` / `warning` / `danger` / `info` (+ `-bg`) | #047857 / #b45309 / #be123c / #0369a1 | #34d399 / #fbbf24 / #fb7185 / #38bdf8 | status; danger also critical path and destructive actions |
| `chart-1`…`chart-6` | teal, indigo, amber, rose, sky, slate | lighter variants | chart series |
| `elev-xs`…`elev-lg` | soft shadows | almost none (borders instead) | `shadow-xs`…`shadow-lg` |

Rules: at most three accent colours per screen; status is never colour alone (icon + text, as
`Badge`, `RiskChip` and `Alert` do); new tokens go in both themes and the contrast test.

## 3. Typography

Inter 400/500/600/700 and JetBrains Mono 400 (code and ids), both self-hosted through
`@fontsource`. Scale (px / line height):

| Utility | Size | Utility | Size |
|---|---|---|---|
| `text-caption` | 12 / 16 | `text-h4` | 20 / 28 |
| `text-body-sm` | 14 / 20 | `text-h3` | 24 / 32 |
| `text-body` | 16 / 24 | `text-h2` | fluid 24 → 30 |
| `text-lead` | 18 / 28 | `text-h1` | fluid 28 → 36 |
| | | `text-hero` | fluid 36 → 48 |

One `h1` per page. Numbers in tables, stats and money use `tabular`. Formatting helpers:
`formatMoney(paisa)` → "৳12,500" (integers only, never floats), `formatDate` → "12 Oct 2026"
(Asia/Dhaka), `formatRelative` (full date in the tooltip), `formatScore` (0–1 shown as 0–100),
`formatCount` (12.4k).

## 4. Spacing, radius, elevation, focus

4 px grid (4, 8, 12, 16, 20, 24, 32, 40, 48, 64). Radii: `rounded-md` 8 px inputs and buttons,
`rounded-lg` 12 px cards, `rounded-xl` 16 px dialogs and hero cards, `rounded-full` badges and
avatars. Focus: a global 2 px primary ring with a 2 px offset on `:focus-visible`; never removed.
Content width is capped at 1280 px (`--container-content`).

## 5. Components

**Primitives** (`components/ui`, Radix-based where interactive): `Button` (primary, secondary,
outline, ghost, destructive, link; sm/md/lg; `loading`; `asChild`), `IconButton` (aria-label
required), `Field`/`FormField`/`Input`/`Textarea` (counter), `Select`, `Combobox` (cmdk),
`Checkbox`, `RadioGroup` (`cards`), `Switch`, `Slider`, `SegmentedControl`, `Card`/`CardHeader`,
`StatCard` (count-up), `Badge`, `NewcomerBadge`, `RiskChip`, `Avatar`, `Tabs`, `Accordion`,
`Breadcrumbs`, `Dialog`, `ConfirmDialog` (type-to-confirm), `Sheet` (right/left/bottom),
`Popover`, `Tooltip` (tap and focus too), `DropdownMenu`, `toast`/`Toaster` (Radix Toast),
`Skeleton`, `EmptyState`, `ErrorState`, `Alert`, `Stepper`, `Progress`, `RingProgress`,
`OtpInput`, `PasswordMeter`, `Spinner`, `FileDropzone`, `SortableList` (@dnd-kit, keyboard),
`CountdownTimer`, `PageHeader`.

**Shell**: `AppShell` (top bar, collapsible sidebar, bottom tab bar + More sheet, skip link),
`CommandPalette` (Ctrl/⌘K), `OfflineBanner`, `PageSkeleton`; `AuthLayout` for sign-in screens.

**Domain composites built so far**: `Gantt` (SVG; real dates or days-from-start, Days/Weeks
zoom, finish-to-start arrows, critical path in `danger`, slack, legend, today line once work
is under way, keyboard-focusable bars, details line), `DependencyGraph` (layered DAG, critical
edges emphasised, names wrap, nodes are focus stops), `CpmTable` (the accessible table
alternative). **Brand**: `Logo`/`Wordmark`/`Mark`, `NodeArt` (2D motif), `Still` (pre-rendered
3D stills). Later phases add KanbanBoard, ReputationPanel, FairnessDial, PrioritySliders,
ConvergenceChart, RiskList, EscrowTimeline, SplitEditor and more from these primitives.

## 6. Page pattern

Every signed-in page renders inside the role shell and starts with `PageHeader`: breadcrumbs
(when nested) → `h1` → one-line description → one primary action (full width under the title
on phones); 24 px to content. Content sits in `Card`s on `bg`, 24 px gutters, at most two
columns on dashboards at ≥ 1280 px (8/4), one column below 1024 px. One primary button per
view; destructive actions go through `ConfirmDialog` and explain the consequence.

Every data view has all four states: **loading** (`Skeleton` shaped like the result), **empty**
(`EmptyState`: icon or art, one sentence, primary action), **error** (`ErrorState`: what
happened, Try again, request id) and **success** (toast or inline confirmation). Data comes
only from TanStack Query hooks in `features/*/api.ts`; forms use React Hook Form + Zod and map
server field errors back onto the fields.

## 7. Motion catalogue

All motion comes from `design/motion.ts` through `useMotion()`, which returns variants already
reduced for the user's setting.

| Token | Value |
|---|---|
| Durations | fast 120 ms, base 180 ms, slow 280 ms, page 220 ms, press 80 ms, cross-fade 400 ms |
| Easing | standard `(0.2,0,0,1)`, emphasized `(0.3,0,0,1)`, exit `(0.4,0,1,1)` |
| Stagger | lists 30 ms (max 8 items), words 40 ms, reveals 60 ms |
| One-offs | count-up 0.6 s, meter 0.4 s, reveal 0.35 s, highlight fade 1.2 s, toast 5 s, drag hold 150 ms |

Variants: `page`, `card`, `list`/`listItem`, `reveal`, `words`/`word` (homepage headline),
`overlay`, `dialog`, `sheetRight`, `sheetBottom`, `shake` (form errors), `swap` (cross-fade),
plus `meterTransition` and `indicatorTransition`. Radix overlays use the CSS utilities
`anim-overlay`, `anim-pop`, `anim-sheet-*`, `anim-toast`; Tailwind durations are
`duration-fast|base|slow|page|crossfade|press`.

Rules: an ESLint rule rejects numeric durations/delays and `duration-300`-style classes outside
`motion.ts`. Hover lifts and press scales use the `motion-ok:` variant. Under reduced motion (OS
or in-app setting) there are no transforms, shimmer, count-ups or drawing — only ≤ 120 ms
fades, and content shows its final state. Nothing loops except progress indicators; motion
never blocks input or delays content by more than 300 ms.

## 8. Responsive rules (§13.14)

Mobile first; breakpoints sm 640, md 768, lg 1024, xl 1280, 2xl 1536. ≥ 1024: top bar + sidebar
(248 px, collapsible to a 72 px rail); 768–1023: rail; < 768: compact top bar and bottom tab bar
(4 destinations + More). Tables become card lists, dialogs become bottom sheets, wizards show
"Step 3 of 6" with a sticky Back/Continue bar, charts go full width with a table toggle. Inputs
are 16 px (no iOS zoom) with `inputMode`/`autoComplete`; `100dvh` and safe-area insets; no
hover-only features. The gate's viewport matrix (375×667, 390×844, 768×1024, 1366×768,
1440×900, light and dark; `frontend/e2e/responsive.spec.ts`) checks for horizontal overflow,
overlapping controls, clipped text and ≥ 44 × 44 px touch targets.

## 9. Accessibility (WCAG 2.1 AA)

Keyboard access everywhere with visible focus; every control labelled (`FormField` wires
`aria-describedby`/`aria-invalid`); `aria-live="polite"` for toasts, progress and form errors;
skip link; document titles `<Page> · DevSync` from route `handle.title`; charts have table
alternatives (`CpmTable`); 200 % zoom without horizontal scrolling; contrast tested for every
token pair. axe runs on every registered screen in the gate (`frontend/e2e/a11y.spec.ts`,
screens listed in `e2e/screens.ts`).

## 10. Microcopy (§13.10)

Plain, friendly, specific, second person, sentence case. Buttons are verbs naming the result
("Publish for bidding", "Place sealed bid"), never "Submit" or "OK", and keep their name through the flow
(the toast says "Published"). Numbers beat vague words ("2 days late"). Every algorithmic result
gets one sentence of "why" (for example the bid verdicts in "How the filter decided"). Errors
say what happened and what to do next without apologising. Paper notation only in explanation
drawers. Curly apostrophes (’) in UI copy; no ALL-CAPS labels.

## 11. 3D hero and stills (§13.12)

The only WebGL is the homepage hero (`components/three/TalentConstellation.tsx`, React Three
Fiber, slim `three` entry, ≤ 220 KB gzip chunk, colours from `tokens.ts`). A 2D poster is drawn
first so the headline stays the LCP element; the live scene cross-fades in and falls back to
the poster for reduced motion, no WebGL, software WebGL (D54), data saver, < 4 cores or a lost
context; it pauses off screen. No remote models or HDRs. Elsewhere the identity appears through
`Still` images and `NodeArt`; `make stills` re-renders them (the gate checks the manifest hash).
Until Phase 7 the homepage shows no algorithm percentages (D21).

## 12. Security rules that touch the UI

Strict CSP: no inline scripts or styles, no `dangerouslySetInnerHTML`, no `eval`, no external
URLs, no CSS-in-JS. Radix's runtime `<style>` uses the per-response nonce (D23,
`lib/nonce.ts`). User text always renders as text. Dev-only pages never ship.

## 13. Definition of done for a screen

Page pattern and four data states; light + dark, five viewports, reduced motion; keyboard pass,
axe clean, touch targets; copy checked; component tests and, on demo paths, a Playwright flow
with visual baselines (`make visual-update`, review the diff).
