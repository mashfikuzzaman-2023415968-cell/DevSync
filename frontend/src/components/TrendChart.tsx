/**
 * Trend line chart (spec §13.3 charts, §13.5 #16 "trend chart over projects", §13.8 #6).
 *
 * Custom SVG like `Gantt.tsx`: one point per project (oldest left), a 0–100 axis with light
 * grid lines, up to six series in `--chart-1..6` order with a legend (colour plus name, never
 * colour alone). Every point is a keyboard focus stop; hovering, focusing or tapping one shows
 * its project and values in a live region under the chart. "View as table" shows the same
 * numbers. No motion.
 */
import { useId, useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { cn } from "@/lib/cn";

export interface TrendSeries {
  name: string;
  /** 0–1 per point; null where the value is unknown. */
  values: readonly (number | null)[];
}

export interface TrendPoint {
  label: string;
  /** Shown in the details line and the table, e.g. "8 Feb 2025". */
  detail?: string;
}

const STROKE = ["stroke-chart-1", "stroke-chart-2", "stroke-chart-3", "stroke-chart-4",
  "stroke-chart-5", "stroke-chart-6"] as const; // prettier-ignore
const FILL = ["fill-chart-1", "fill-chart-2", "fill-chart-3", "fill-chart-4", "fill-chart-5",
  "fill-chart-6"] as const; // prettier-ignore
const BG = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5",
  "bg-chart-6"] as const; // prettier-ignore

const WIDTH = 640;
const HEIGHT = 220;
const PAD = { left: 36, right: 16, top: 12, bottom: 24 };
const GRID = [0, 25, 50, 75, 100];

function score(v: number): number {
  return Math.round(Math.min(1, Math.max(0, v)) * 100);
}

export function TrendChart({
  title,
  points,
  series,
}: {
  title: string;
  points: readonly TrendPoint[];
  series: readonly TrendSeries[];
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [active, setActive] = useState<number | null>(null);
  const liveId = useId();
  const n = points.length;
  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (n <= 1 ? innerW / 2 : (innerW * i) / (n - 1));
  const y = (v: number) => PAD.top + innerH * (1 - Math.min(1, Math.max(0, v)));
  const describe = (i: number) => {
    const p = points[i];
    if (!p) return "";
    const values = series
      .map((s) => {
        const v = s.values[i];
        return v === null || v === undefined ? null : `${s.name} ${String(score(v))}`;
      })
      .filter(Boolean)
      .join(", ");
    return `${p.label}${p.detail ? ` (${p.detail})` : ""}: ${values}`;
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-body-sm text-text-muted">
          {series.map((s, i) => (
            <li key={s.name} className="flex items-center gap-2">
              <span
                className={cn("inline-block h-0.5 w-4 rounded-full", BG[i % 6])}
                aria-hidden="true"
              />
              {s.name}
            </li>
          ))}
        </ul>
        <SegmentedControl
          size="sm"
          label={`${title}: chart or table`}
          value={view}
          onChange={setView}
          segments={[
            { value: "chart", label: "Chart" },
            { value: "table", label: "View as table" },
          ]}
        />
      </div>
      {view === "chart" ? (
        <>
          <div className="mt-3 overflow-x-auto">
            <svg
              viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
              className="block w-full min-w-[20rem]"
              role="group"
              aria-label={title}
            >
              <g className="stroke-border" strokeWidth="1" aria-hidden="true">
                {GRID.map((g) => (
                  <line
                    key={g}
                    x1={PAD.left}
                    x2={WIDTH - PAD.right}
                    y1={y(g / 100)}
                    y2={y(g / 100)}
                  />
                ))}
              </g>
              <g className="fill-text-muted text-caption tabular" aria-hidden="true">
                {GRID.map((g) => (
                  <text
                    key={g}
                    x={PAD.left - 8}
                    y={y(g / 100)}
                    textAnchor="end"
                    dominantBaseline="middle"
                  >
                    {g}
                  </text>
                ))}
              </g>
              {series.map((s, si) => {
                const path = s.values
                  .map((v, i) => (v === null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`))
                  .filter(Boolean)
                  .join(" L");
                return path ? (
                  <path
                    key={s.name}
                    d={`M${path}`}
                    className={cn("fill-none", STROKE[si % 6])}
                    strokeWidth="2"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  />
                ) : null;
              })}
              {points.map((p, i) => (
                <g
                  key={`${p.label}-${String(i)}`}
                  tabIndex={0}
                  role="img"
                  aria-label={describe(i)}
                  className="group cursor-default outline-none"
                  onMouseEnter={() => {
                    setActive(i);
                  }}
                  onFocus={() => {
                    setActive(i);
                  }}
                  onClick={() => {
                    setActive(i);
                  }}
                >
                  <rect
                    x={x(i) - 10}
                    y={PAD.top}
                    width="20"
                    height={innerH}
                    className={active === i ? "fill-primary-soft" : "fill-transparent"}
                  />
                  {series.map((s, si) => {
                    const v = s.values[i];
                    return v === null || v === undefined ? null : (
                      <circle key={s.name} cx={x(i)} cy={y(v)} r="4" className={FILL[si % 6]} />
                    );
                  })}
                  <rect
                    x={x(i) - 12}
                    y={PAD.top - 2}
                    width="24"
                    height={innerH + 4}
                    rx="4"
                    className="fill-none stroke-primary opacity-0 group-focus-visible:opacity-100"
                    strokeWidth="2"
                  />
                </g>
              ))}
            </svg>
          </div>
          <p id={liveId} className="mt-2 min-h-5 text-body-sm text-text-muted" aria-live="polite">
            {active !== null
              ? describe(active)
              : "Point at, tap or tab to a project to see its values."}
          </p>
        </>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-body-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th scope="col" className="py-2 pr-4 font-medium">
                  Project
                </th>
                {series.map((s) => (
                  <th key={s.name} scope="col" className="py-2 pl-4 text-right font-medium">
                    {s.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {points.map((p, i) => (
                <tr
                  key={`${p.label}-${String(i)}`}
                  className="border-b border-border last:border-0"
                >
                  <th scope="row" className="py-2 pr-4 text-left font-normal text-text">
                    {p.label}
                    {p.detail ? (
                      <span className="block text-caption text-text-muted">{p.detail}</span>
                    ) : null}
                  </th>
                  {series.map((s) => {
                    const v = s.values[i];
                    return (
                      <td key={s.name} className="py-2 pl-4 text-right tabular text-text">
                        {v === null || v === undefined ? "—" : score(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
