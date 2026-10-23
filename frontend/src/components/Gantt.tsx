/**
 * Gantt chart for a CPM schedule (spec §9.10, §13.3 domain composites).
 *
 * Custom SVG (no chart library, per the build spec). Milestone names sit in an HTML column on
 * the left (full names, wrapped to two lines) and the timeline scrolls beside them. One bar per
 * milestone runs from its earliest start to its earliest finish, with a lighter slack bar to the
 * latest finish; the critical path is rose, slack milestones indigo. Finish-to-start
 * dependencies are drawn as elbow arrows from a predecessor's end to its successor's start.
 *
 * With a start date the axis shows real dates (months over days, or week starts when zoomed
 * out); without one it counts days from the start, matching the CPM table. A dashed deadline
 * line and, once work has started, a "today" line give context. Hovering, focusing or tapping a
 * bar shows its dates, slack and dependencies in a live region under the chart.
 * Bars are keyboard-focusable with a text label; `CpmTable` is the table alternative.
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { CpmNode } from "@/api/types";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { cn } from "@/lib/cn";
import { formatDate, formatDays } from "@/lib/format";

export type GanttEdge = readonly [from: string, to: string];
export type GanttZoom = "days" | "weeks";

export interface GanttProps {
  nodes: CpmNode[];
  /** Finish-to-start dependencies as [predecessor key, successor key]. */
  edges?: readonly GanttEdge[];
  /** Project start date (ISO); day 0 of the plan. Without it the axis counts days. */
  startDate?: string | null;
  /** Day offset of "today" from project start; omit to hide the line. */
  today?: number | null;
  /** Deadline in days from start; drawn as a dashed line. */
  deadlineDays?: number | null;
  /** Initial zoom; by default days for plans up to 45 days, weeks beyond. */
  zoom?: GanttZoom;
  className?: string | undefined;
}

const ROW_H = 44;
const BAR_H = 18;
const HEADER_H = 40;
const PAD_END = 24;
const DAY_W: Record<GanttZoom, number> = { days: 28, weeks: 10 };
const MAX_DAY_W = 64;
const AUTO_WEEKS_AFTER = 45;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The calendar date `day` days after an ISO start date (UTC, like the stored offsets). */
export function dayToDate(startIso: string, day: number): Date {
  const d = new Date(startIso);
  d.setUTCDate(d.getUTCDate() + day);
  return d;
}

/** "6 Nov 2026 – 14 Nov 2026" for a bar covering offsets [es, ef). */
function dateRange(startIso: string, es: number, ef: number): string {
  return `${formatDate(dayToDate(startIso, es))} – ${formatDate(dayToDate(startIso, Math.max(es, ef - 1)))}`;
}

export function ganttLabel(n: CpmNode, startDate: string | null): string {
  const base = n.critical
    ? `${n.name}: days ${String(n.es)}–${String(n.ef)}, on the critical path`
    : `${n.name}: days ${String(n.es)}–${String(n.ef)}, slack ${formatDays(n.slack)}`;
  return startDate ? `${base}, ${dateRange(startDate, n.es, n.ef)}` : base;
}

interface Tick {
  x: number;
  label: string;
  anchor: "start" | "middle";
}

/** Axis labels: a top row (months or "Days from start") and a bottom row (days or weeks). */
function axis(duration: number, zoom: GanttZoom, startDate: string | null) {
  const top: Tick[] = [];
  const bottom: Tick[] = [];
  const lines: number[] = [];
  if (startDate) {
    for (let d = 0; d <= duration; d += 1) {
      const date = dayToDate(startDate, d);
      if (d === 0 || date.getUTCDate() === 1) {
        top.push({
          x: d,
          label: `${MONTHS[date.getUTCMonth()] ?? ""} ${String(date.getUTCFullYear())}`,
          anchor: "start",
        });
      }
      if (zoom === "days") {
        lines.push(d);
        if (d < duration) {
          bottom.push({ x: d + 0.5, label: String(date.getUTCDate()), anchor: "middle" });
        }
      } else if (d % 7 === 0) {
        lines.push(d);
        bottom.push({
          x: d,
          label: `${String(date.getUTCDate())} ${MONTHS[date.getUTCMonth()] ?? ""}`,
          anchor: "start",
        });
      }
    }
  } else {
    top.push({ x: 0, label: zoom === "days" ? "Days from start" : "Weeks", anchor: "start" });
    const step = zoom === "days" ? 1 : 7;
    for (let d = 0; d <= duration; d += step) {
      lines.push(d);
      if (zoom === "days") {
        if (d % 5 === 0)
          bottom.push({ x: d, label: String(d), anchor: d === 0 ? "start" : "middle" });
      } else if (d < duration) {
        bottom.push({ x: d, label: `Week ${String(d / 7 + 1)}`, anchor: "start" });
      }
    }
  }
  return { top, bottom, lines };
}

/** Drop labels that would start within `gap` px of the previous one (e.g. a month that
 * begins two days after the project starts). */
function spaced(ticks: Tick[], x: (d: number) => number, gap: number): Tick[] {
  const out: Tick[] = [];
  for (const t of ticks) {
    const prev = out[out.length - 1];
    if (prev && x(t.x) - x(prev.x) < gap) out[out.length - 1] = t;
    else out.push(t);
  }
  return out;
}

/** Elbow path from a predecessor's finish to a successor's start (finish-to-start link). */
function linkPath(x1: number, y1: number, x2: number, y2: number): string {
  const out = 6;
  if (x2 - x1 >= out * 2) {
    return `M${String(x1)},${String(y1)} H${String(x1 + out)} V${String(y2)} H${String(x2)}`;
  }
  // The successor starts at (or before) the predecessor's end: drop between the rows first.
  const between = y2 + (y2 > y1 ? -ROW_H / 2 : ROW_H / 2);
  return `M${String(x1)},${String(y1)} H${String(x1 + out)} V${String(between)} H${String(x2 - out)} V${String(y2)} H${String(x2)}`;
}

/** Width of the element, tracked with a ResizeObserver where available. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      setWidth(Math.floor(entry?.contentRect.width ?? 0));
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);
  return [ref, width] as const;
}

export function Gantt({
  nodes,
  edges = [],
  startDate = null,
  today = null,
  deadlineDays = null,
  zoom: initialZoom,
  className,
}: GanttProps) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const titleId = `gantt-title-${uid}`;
  const detailsId = `gantt-details-${uid}`;
  const duration = Math.max(1, ...nodes.map((n) => n.lf), deadlineDays ?? 0);
  const [chosenZoom, setZoom] = useState<GanttZoom | null>(initialZoom ?? null);
  const [active, setActive] = useState<string | null>(null);
  const [scrollRef, available] = useWidth<HTMLDivElement>();
  // Until the viewer picks one: weeks for long plans, or when days would need more than two
  // screens of scrolling (phones).
  const zoom: GanttZoom =
    chosenZoom ??
    (duration > AUTO_WEEKS_AFTER || (available > 0 && duration * DAY_W.days > available * 2)
      ? "weeks"
      : "days");

  // Stretch short plans to the available width; never squeeze below the zoom's day width.
  const dayWidth = Math.min(
    MAX_DAY_W,
    Math.max(DAY_W[zoom], Math.floor((available - PAD_END) / duration) || 0),
  );
  const chartW = duration * dayWidth + PAD_END;
  const height = HEADER_H + nodes.length * ROW_H;
  const x = (day: number) => day * dayWidth;
  const rowMid = (i: number) => HEADER_H + i * ROW_H + ROW_H / 2;

  const { top, bottom, lines } = useMemo(
    () => axis(duration, zoom, startDate),
    [duration, zoom, startDate],
  );
  // Day numbers need ~18 px each; week labels ("16 Nov", "Week 3") about 44 px.
  const bottomGap = zoom === "days" ? 18 : 44;
  const index = useMemo(() => new Map(nodes.map((n, i) => [n.key, i])), [nodes]);
  const byKey = useMemo(() => new Map(nodes.map((n) => [n.key, n])), [nodes]);
  const links = edges.flatMap(([from, to]) => {
    const a = byKey.get(from);
    const b = byKey.get(to);
    const ia = index.get(from);
    const ib = index.get(to);
    if (!a || !b || ia === undefined || ib === undefined) return [];
    return [{ from, to, a, b, ia, ib, critical: a.critical && b.critical && a.ef === b.es }];
  });

  const criticalCount = nodes.filter((n) => n.critical).length;
  const showToday = today != null && today >= 0 && today <= duration;
  const activeNode = active ? byKey.get(active) : undefined;
  const hover = (key: string | null) => () => {
    setActive(key);
  };

  return (
    <figure className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Legend showToday={showToday} showDeadline={deadlineDays != null} />
        <SegmentedControl<GanttZoom>
          label="Timeline zoom"
          size="sm"
          value={zoom}
          onChange={setZoom}
          segments={[
            { value: "days", label: "Days" },
            { value: "weeks", label: "Weeks" },
          ]}
        />
      </div>

      <div className="flex overflow-hidden rounded-md border border-border">
        {/* Names: an HTML column so long names wrap instead of being cut off. */}
        <div
          className="w-32 shrink-0 border-r border-border bg-surface-2 sm:w-52"
          aria-hidden="true"
        >
          <div className="flex h-10 items-end px-3 pb-1.5 text-caption font-medium text-text-muted">
            Milestone
          </div>
          {nodes.map((n) => (
            <div
              key={n.key}
              title={n.name}
              className={cn(
                "flex h-11 items-center border-t border-border px-3 text-body-sm leading-tight",
                active === n.key ? "bg-primary-soft text-text" : "text-text",
              )}
            >
              <span className="line-clamp-2 break-words">{n.name}</span>
            </div>
          ))}
        </div>

        <div ref={scrollRef} className="min-w-0 flex-1 overflow-x-auto">
          <svg
            role="img"
            aria-labelledby={titleId}
            aria-describedby={detailsId}
            width={chartW}
            height={height}
            viewBox={`0 0 ${String(chartW)} ${String(height)}`}
            className="block"
          >
            <title id={titleId}>
              Gantt chart: {nodes.length} milestones over {formatDays(duration)}, {criticalCount} on
              the critical path.
            </title>
            <defs>
              <marker
                id={`arrow-${uid}`}
                viewBox="0 0 6 6"
                refX="6"
                refY="3"
                markerWidth="6"
                markerHeight="6"
                markerUnits="userSpaceOnUse"
                orient="auto"
              >
                <path d="M0,0 L6,3 L0,6 z" className="fill-text-subtle" />
              </marker>
              <marker
                id={`arrow-crit-${uid}`}
                viewBox="0 0 6 6"
                refX="6"
                refY="3"
                markerWidth="6"
                markerHeight="6"
                markerUnits="userSpaceOnUse"
                orient="auto"
              >
                <path d="M0,0 L6,3 L0,6 z" className="fill-danger" />
              </marker>
            </defs>

            {/* Row stripes and grid */}
            {nodes.map((n, i) => (
              <rect
                key={`row-${n.key}`}
                x={0}
                y={HEADER_H + i * ROW_H}
                width={chartW}
                height={ROW_H}
                className={active === n.key ? "fill-primary-soft" : "fill-transparent"}
              />
            ))}
            <g className="stroke-border" strokeWidth="1">
              <line x1={0} y1={HEADER_H} x2={chartW} y2={HEADER_H} />
              {nodes.map((n, i) => (
                <line
                  key={`rl-${n.key}`}
                  x1={0}
                  y1={HEADER_H + (i + 1) * ROW_H}
                  x2={chartW}
                  y2={HEADER_H + (i + 1) * ROW_H}
                  strokeOpacity="0.5"
                />
              ))}
              {lines.map((d) => (
                <line
                  key={`g${String(d)}`}
                  x1={x(d)}
                  y1={20}
                  x2={x(d)}
                  y2={height}
                  strokeOpacity="0.6"
                />
              ))}
            </g>

            {/* Axis */}
            <g className="fill-text-muted text-caption tabular" aria-hidden="true">
              {spaced(top, x, 72)
                .filter((t, i) => i === 0 || x(t.x) + 64 <= chartW)
                .map((t) => (
                  <text key={`top${String(t.x)}`} x={x(t.x) + 4} y={14} className="font-medium">
                    {t.label}
                  </text>
                ))}
              {spaced(bottom, x, bottomGap).map((t) => (
                <text
                  key={`b${String(t.x)}`}
                  x={x(t.x) + (t.anchor === "start" ? 4 : 0)}
                  y={34}
                  textAnchor={t.anchor}
                >
                  {t.label}
                </text>
              ))}
            </g>

            {/* Deadline and today */}
            {deadlineDays != null && (
              <g aria-hidden="true">
                <line
                  x1={x(deadlineDays)}
                  y1={HEADER_H}
                  x2={x(deadlineDays)}
                  y2={height}
                  className="stroke-warning"
                  strokeWidth="2"
                  strokeDasharray="4 3"
                />
              </g>
            )}
            {showToday && (
              <g aria-hidden="true">
                <line
                  x1={x(today)}
                  y1={HEADER_H - 4}
                  x2={x(today)}
                  y2={height}
                  className="stroke-primary"
                  strokeWidth="2"
                />
                <circle cx={x(today)} cy={HEADER_H - 4} r="3" className="fill-primary" />
              </g>
            )}

            {/* Dependency arrows (under the bars) */}
            <g fill="none" aria-hidden="true">
              {links.map((l) => {
                const related = active === l.from || active === l.to;
                return (
                  <path
                    key={`${l.from}->${l.to}`}
                    d={linkPath(x(l.a.ef), rowMid(l.ia), x(l.b.es), rowMid(l.ib))}
                    markerEnd={`url(#${l.critical ? "arrow-crit" : "arrow"}-${uid})`}
                    strokeWidth={related ? "2" : "1.25"}
                    className={cn(
                      l.critical ? "stroke-danger" : "stroke-text-subtle",
                      active && !related && "opacity-30",
                    )}
                  />
                );
              })}
            </g>

            {/* Bars */}
            {nodes.map((n, i) => {
              const barY = rowMid(i) - BAR_H / 2;
              const barW = Math.max(2, (n.ef - n.es) * dayWidth);
              const slackW = n.slack * dayWidth;
              const label = ganttLabel(n, startDate);
              return (
                <g
                  key={n.key}
                  tabIndex={0}
                  role="group"
                  aria-label={label}
                  onMouseEnter={hover(n.key)}
                  onMouseLeave={hover(null)}
                  onFocus={hover(n.key)}
                  onBlur={hover(null)}
                  onClick={hover(n.key)}
                  className="group cursor-default outline-none"
                >
                  <title>{label}</title>
                  {slackW > 0 && (
                    <rect
                      x={x(n.ef)}
                      y={barY + 4}
                      width={slackW}
                      height={BAR_H - 8}
                      rx="2"
                      className="fill-accent/25"
                    />
                  )}
                  <rect
                    x={x(n.es)}
                    y={barY}
                    width={barW}
                    height={BAR_H}
                    rx="4"
                    className={n.critical ? "fill-danger" : "fill-accent"}
                  />
                  <rect
                    x={x(n.es) - 3}
                    y={barY - 3}
                    width={barW + 6}
                    height={BAR_H + 6}
                    rx="6"
                    fill="none"
                    strokeWidth="2"
                    className={cn(
                      "stroke-primary group-focus-visible:opacity-100",
                      active === n.key ? "opacity-100" : "opacity-0",
                    )}
                  />
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      <figcaption
        id={detailsId}
        aria-live="polite"
        className="min-h-10 text-body-sm text-text-muted"
      >
        {activeNode ? (
          <Details node={activeNode} startDate={startDate} edges={edges} byKey={byKey} />
        ) : (
          "Hover, focus or tap a bar to see its dates, slack and dependencies."
        )}
      </figcaption>
    </figure>
  );
}

function Details({
  node,
  startDate,
  edges,
  byKey,
}: {
  node: CpmNode;
  startDate: string | null;
  edges: readonly GanttEdge[];
  byKey: Map<string, CpmNode>;
}) {
  const span = node.ef - node.es;
  const when = startDate
    ? dateRange(startDate, node.es, node.ef)
    : `Days ${String(node.es)}–${String(node.ef)}`;
  const after = edges
    .filter(([, to]) => to === node.key)
    .map(([from]) => byKey.get(from)?.name)
    .filter((n): n is string => Boolean(n));
  return (
    <span>
      <span className="font-medium text-text">{node.name}</span>
      {`: ${when} (${formatDays(span)}). `}
      {node.critical
        ? "On the critical path, so any delay moves the finish date."
        : `Can slip ${formatDays(node.slack)} without delaying the finish.`}
      {after.length > 0 && ` Starts after ${after.join(", ")}.`}
    </span>
  );
}

function Legend({ showToday, showDeadline }: { showToday: boolean; showDeadline: boolean }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-text-muted">
      <li className="flex items-center gap-1.5">
        <span className="h-2.5 w-4 rounded-sm bg-danger" aria-hidden="true" />
        Critical path
      </li>
      <li className="flex items-center gap-1.5">
        <span className="h-2.5 w-4 rounded-sm bg-accent" aria-hidden="true" />
        Has slack
      </li>
      <li className="flex items-center gap-1.5">
        <span className="h-1.5 w-4 rounded-sm bg-accent/25" aria-hidden="true" />
        Slack (can slip)
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="18" height="10" viewBox="0 0 18 10" aria-hidden="true">
          <path d="M0,5 H12" className="stroke-text-subtle" strokeWidth="1.25" fill="none" />
          <path d="M12,2 L18,5 L12,8 z" className="fill-text-subtle" />
        </svg>
        Depends on
      </li>
      {showDeadline && (
        <li className="flex items-center gap-1.5">
          <svg width="10" height="12" viewBox="0 0 10 12" aria-hidden="true">
            <line
              x1="5"
              y1="0"
              x2="5"
              y2="12"
              className="stroke-warning"
              strokeWidth="2"
              strokeDasharray="4 3"
            />
          </svg>
          Deadline
        </li>
      )}
      {showToday && (
        <li className="flex items-center gap-1.5">
          <span className="h-3 w-0.5 bg-primary" aria-hidden="true" />
          Today
        </li>
      )}
    </ul>
  );
}
