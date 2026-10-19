/**
 * Gantt chart for a CPM schedule (spec §9.10, §13.3 domain composites).
 *
 * Custom SVG (no chart library, per the build spec): one bar per milestone from its earliest
 * start to its earliest finish, with a lighter slack bar extending to the latest finish. The
 * critical path is drawn in danger (rose); slack is shown in accent. A dotted "today" line and
 * a dashed deadline line give context. Bars are keyboard-focusable with a text label for
 * screen readers; a table alternative lives in `CpmTable` and is offered by the parent.
 */
import { useId } from "react";
import type { CpmNode } from "@/api/types";
import { cn } from "@/lib/cn";
import { formatDays } from "@/lib/format";

export interface GanttProps {
  nodes: CpmNode[];
  /** Pixels per day (zoom). */
  dayWidth?: number;
  /** Day offset of "today" from project start; omit to hide the line. */
  today?: number | null;
  /** Deadline in days from start; drawn as a dashed line when the plan fits or overruns. */
  deadlineDays?: number | null;
  className?: string | undefined;
}

const ROW_H = 30;
const BAR_H = 16;
const LABEL_W = 150;
const PAD_Y = 12;
const AXIS_H = 22;

export function Gantt({
  nodes,
  dayWidth = 26,
  today = null,
  deadlineDays = null,
  className,
}: GanttProps) {
  const titleId = useId();
  const duration = Math.max(1, ...nodes.map((n) => n.lf), deadlineDays ?? 0);
  const chartW = duration * dayWidth;
  const width = LABEL_W + chartW + 16;
  const height = AXIS_H + nodes.length * ROW_H + PAD_Y;
  const x = (day: number) => LABEL_W + day * dayWidth;

  // Week gridlines keep long plans readable without crowding day ticks.
  const step = dayWidth < 14 ? 7 : dayWidth < 22 ? 2 : 1;
  const ticks: number[] = [];
  for (let d = 0; d <= duration; d += step) ticks.push(d);

  const criticalCount = nodes.filter((n) => n.critical).length;

  return (
    <div className={cn("overflow-x-auto", className)}>
      <svg
        role="img"
        aria-labelledby={titleId}
        width={width}
        height={height}
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        className="min-w-full"
      >
        <title id={titleId}>
          Gantt chart: {nodes.length} milestones over {formatDays(duration)}, {criticalCount} on the
          critical path.
        </title>

        {/* Day/week grid */}
        <g className="stroke-border" strokeWidth="1">
          {ticks.map((d) => (
            <line key={`g${String(d)}`} x1={x(d)} y1={AXIS_H} x2={x(d)} y2={height - PAD_Y} />
          ))}
        </g>
        <g className="fill-text-subtle text-caption tabular" aria-hidden="true">
          {ticks.map((d) => (
            <text key={`t${String(d)}`} x={x(d)} y={14} textAnchor="middle">
              {d === 0 ? "Start" : `d${String(d)}`}
            </text>
          ))}
        </g>

        {/* Deadline line */}
        {deadlineDays != null && (
          <line
            x1={x(deadlineDays)}
            y1={AXIS_H}
            x2={x(deadlineDays)}
            y2={height - PAD_Y}
            className="stroke-warning"
            strokeWidth="1.5"
            strokeDasharray="2 3"
          />
        )}

        {/* Today line */}
        {today != null && today >= 0 && today <= duration && (
          <line
            x1={x(today)}
            y1={AXIS_H}
            x2={x(today)}
            y2={height - PAD_Y}
            className="stroke-primary"
            strokeWidth="1.5"
            strokeDasharray="1 3"
          />
        )}

        {/* Bars */}
        {nodes.map((n, i) => {
          const rowY = AXIS_H + i * ROW_H;
          const barY = rowY + (ROW_H - BAR_H) / 2;
          const barW = Math.max(2, (n.ef - n.es) * dayWidth);
          const slackW = n.slack * dayWidth;
          const label = n.critical
            ? `${n.name}: days ${String(n.es)}–${String(n.ef)}, on the critical path`
            : `${n.name}: days ${String(n.es)}–${String(n.ef)}, slack ${formatDays(n.slack)}`;
          return (
            <g
              key={n.key}
              tabIndex={0}
              role="group"
              aria-label={label}
              className="group outline-none"
            >
              <title>{label}</title>
              <text x={0} y={rowY + ROW_H / 2 + 4} className="fill-text text-body-sm">
                {truncate(n.name)}
              </text>
              {/* slack behind the bar */}
              {slackW > 0 && (
                <rect
                  x={x(n.ef)}
                  y={barY + 3}
                  width={slackW}
                  height={BAR_H - 6}
                  rx="2"
                  className="fill-accent/25"
                />
              )}
              <rect
                x={x(n.es)}
                y={barY}
                width={barW}
                height={BAR_H}
                rx="3"
                className={n.critical ? "fill-danger" : "fill-accent"}
              />
              <rect
                x={x(n.es) - 2}
                y={barY - 2}
                width={barW + 4}
                height={BAR_H + 4}
                rx="4"
                fill="none"
                strokeWidth="2"
                className="stroke-primary opacity-0 group-focus-visible:opacity-100"
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function truncate(s: string, max = 20): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}
