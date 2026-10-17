# DevSync components and screens (reference)

Read the section you need. Source of truth: spec §13.3–13.5, §13.9.

## Contents
1. Generic components and where they live
2. Domain composites (built in later phases)
3. Shell and navigation
4. Screen list by role
5. Wireframes for demo screens

## 1. Generic components (`frontend/src/components/ui`)

| Need | Use | Notes |
|---|---|---|
| Any action | `Button` | `variant`, `size`, `loading`, `icon`, `asChild` for links |
| Icon-only action | `IconButton` | 44 px, aria-label required |
| Labelled input | `Field` (input) or `FormField` + any control | hint, error (shakes once), required marker |
| Long text | `Textarea counter maxLength` | |
| Choose one of few | `RadioGroup` / `RadioGroup cards` / `SegmentedControl` | cards for role/answer choices |
| Choose one of many | `Select`; searchable: `Combobox` | |
| On/off | `Switch`; agreement: `Checkbox` | |
| Number in range | `Slider` with `format` | thumbs 28 px on touch |
| Container | `Card`, `CardHeader` | `interactive` for clickable cards |
| KPI | `StatCard` | count-up on first view |
| Status | `Badge tone`, `RiskChip severity`, `NewcomerBadge` | icon + text |
| Person | `Avatar name newcomer` | |
| Sections | `Tabs`, `Accordion` | |
| Confirmation | `ConfirmDialog` (`confirmText` for type-to-confirm) | |
| Side panel / phone sheet | `Sheet side="right"|"bottom"|"left"` | |
| Hints | `Tooltip`, `Popover` | |
| Row actions | `DropdownMenu` | "⋯" trigger |
| Feedback | `toast()`, `Alert` | |
| States | `Skeleton`, `EmptyState`, `ErrorState` | |
| Progress | `Progress`, `RingProgress`, `Stepper` | |
| Codes | `OtpInput` | paste + auto-advance |

Still to build when a phase needs them (from spec §13.3): data table (sticky header, sortable
whitelisted columns, card collapse on phones), MultiSelect (skills), date picker, pagination /
infinite list, timeline, rating stars (radio group), file dropzone, CodeMirror editor, countdown
timer, charts (line, bar, radar, donut with "View as table").

## 2. Domain composites (`frontend/src/components`)

Gantt (SVG; baseline vs forecast; critical path in danger; today line; zoom; keyboard-focusable
bars; table toggle) · DependencyGraph (layered DAG; critical edges emphasised) · KanbanBoard
(@dnd-kit, keyboard sensor, "Move to…" menu, long-press on phones) · ReputationPanel (six
meters + C/P + radar + evidence) · TeamCard · TeamComparison · FairnessDial (segmented 0..k +
cost of fairness chip after a run) · PrioritySliders (always total 100 %) · ConvergenceChart ·
RiskList · BudgetDonut · EscrowTimeline (Not funded → Funded → In review → Paid/Frozen) ·
SplitEditor (must total 100 %) · EvidenceList · WhyNotSelectedCard · CPMTable.

## 3. Shell and navigation

- `AppShell nav={…}`: top bar (logo → role home, Ctrl/⌘K palette, bell, account menu),
  sidebar (collapsible, remembered per user), bottom tab bar + More sheet on phones,
  page transition, skip link.
- Navigation config: `app/navigation.ts` (client, developer); admin in
  `features/admin/nav.ts` (admin chunk only). Pages not built yet have `phase` and show
  `ComingSoonPage` — add the real route in the phase that builds it and drop `phase`.
- Titles: route `handle: { title }`.

## 4. Screens (spec §13.5)

Public: homepage, login, admin TOTP, register, verify, forgot/reset, public projects
`/projects` + `/p/:id`, public developer `/d/:id`, 403/404/500/maintenance.
Developer: dashboard `/dev`, find `/dev/find`, project details + bid sheet, my bids + why not
selected, my projects, skill challenges + timed test + coding challenge, profile & portfolio,
reputation, earnings, notifications, settings.
Client: dashboard `/client`, create-project wizard, plan, bids, team formation, team, payments,
disputes, analytics.
Workspace `/w/:projectId/…`: overview, tasks (Kanban), timeline, milestones, team, check-ins,
files, discussion, payments, evidence, risks, reviews, post-mortem, disputes.
Admin: dashboard, users, projects, formation runs, integrity flags, alerts, disputes,
reputation, payments, fairness analytics, content, settings, audit log.

## 5. Demo wireframes

See spec §13.9 for the landing page, client dashboard, create-project milestones step, CPM
plan, bids table, team formation (Demo 2 centrepiece), workspace overview, Kanban, milestone
review and reputation page. Follow those structures; adjust spacing with tokens.
