/**
 * Convergence chart (spec §13.3, §9.3): the best team score the swarm has found after each
 * iteration, rising to a plateau. Custom SVG drawn at the container's width (like TrendChart);
 * the axis fits the values. Live while a run streams progress, final afterwards. "View as table"
 * shows the same numbers (every 10th point, plus the last). No motion.
 */
import { useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useElementWidth } from "@/lib/useElementWidth";

const DEFAULT_WIDTH = 480;
const MIN_WIDTH = 280;
const HEIGHT = 180;
const PAD = { left: 44, right: 12, top: 12, bottom: 24 };

export function ConvergenceChart({
  values,
  iterations,
  live = false,
}: {
  /** Best fitness per point; null before any feasible team was found. */
  values: readonly (number | null)[];
  /** How many iterations the points span (for the axis and the table). */
  iterations: number;
  live?: boolean;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [boxRef, measured] = useElementWidth<HTMLDivElement>();
  const width = measured > 0 ? Math.max(MIN_WIDTH, measured) : DEFAULT_WIDTH;
  const known = values.filter((v): v is number => v !== null);
  const n = values.length;
  const lo = known.length ? Math.min(...known) : 0;
  const hi = known.length ? Math.max(...known) : 1;
  const span = hi - lo || Math.max(Math.abs(hi), 0.1) * 0.1;
  const min = lo - span * 0.1;
  const max = hi + span * 0.1;
  const innerW = width - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (n <= 1 ? innerW : (innerW * i) / (n - 1));
  const y = (v: number) => PAD.top + innerH * (1 - (v - min) / (max - min));
  const iterOf = (i: number) => (n <= 1 ? iterations : Math.round(((i + 1) * iterations) / n));
  const path = values
    .map((v, i) => (v === null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`))
    .filter(Boolean)
    .join(" L");
  const last = known.at(-1);
  const summary =
    last === undefined
      ? "No team found yet."
      : `Best team score ${last.toFixed(4)} after ${String(iterations)} ${iterations === 1 ? "iteration" : "iterations"}${live ? " so far" : ""}.`;
  const rows = values.map((v, i) => ({ i, v })).filter(({ i }) => i % 10 === 0 || i === n - 1);

  return (
    <div ref={boxRef}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-body-sm text-text-muted" aria-live={live ? "polite" : undefined}>
          {summary}
        </p>
        <SegmentedControl
          size="sm"
          label="Convergence: chart or table"
          value={view}
          onChange={setView}
          segments={[
            { value: "chart", label: "Chart" },
            { value: "table", label: "View as table" },
          ]}
        />
      </div>
      {view === "chart" ? (
        <svg
          viewBox={`0 0 ${String(width)} ${String(HEIGHT)}`}
          className="mt-3 block w-full"
          role="img"
          aria-label={`Convergence. ${summary}`}
        >
          <g className="stroke-border" strokeWidth="1">
            {[0, 0.5, 1].map((f) => (
              <line
                key={f}
                x1={PAD.left}
                x2={width - PAD.right}
                y1={PAD.top + innerH * f}
                y2={PAD.top + innerH * f}
              />
            ))}
          </g>
          <g className="fill-text-muted text-caption tabular">
            {[0, 0.5, 1].map((f) => (
              <text
                key={f}
                x={PAD.left - 6}
                y={PAD.top + innerH * f}
                textAnchor="end"
                dominantBaseline="middle"
              >
                {(max - (max - min) * f).toFixed(2)}
              </text>
            ))}
            <text x={PAD.left} y={HEIGHT - 6}>
              1
            </text>
            <text x={width - PAD.right} y={HEIGHT - 6} textAnchor="end">
              {iterations}
            </text>
          </g>
          {path ? (
            <path
              d={`M${path}`}
              className="fill-none stroke-chart-1"
              strokeWidth="2"
              strokeLinejoin="round"
            />
          ) : null}
          {last !== undefined ? (
            <circle cx={x(n - 1)} cy={y(last)} r="4" className="fill-chart-1" />
          ) : null}
        </svg>
      ) : (
        <div className="mt-3 max-h-64 overflow-auto">
          <table className="w-full text-body-sm">
            <caption className="sr-only">Best team score by iteration</caption>
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th scope="col" className="py-2 pr-4 font-medium">
                  Iteration
                </th>
                <th scope="col" className="py-2 pl-4 text-right font-medium">
                  Best score
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ i, v }) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <th scope="row" className="py-1.5 pr-4 text-left font-normal tabular text-text">
                    {iterOf(i)}
                  </th>
                  <td className="py-1.5 pl-4 text-right tabular text-text">
                    {v === null ? "No team yet" : v.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** The swarm indicator: a few particles drifting while a formation job runs (the only looping
 * animation in DevSync, §13.2; still under reduced motion). */
export function SwarmIndicator({ label }: { label: string }) {
  const dots = [
    [14, 20],
    [30, 10],
    [44, 24],
    [24, 32],
    [52, 12],
    [8, 8],
  ] as const;
  return (
    <span className="inline-flex items-center gap-3" role="status">
      <svg viewBox="0 0 60 40" className="h-8 w-12" aria-hidden="true">
        {dots.map(([cx, cy], i) => (
          <circle
            key={`${String(cx)}-${String(cy)}`}
            cx={cx}
            cy={cy}
            r="3"
            className={`swarm-particle ${i === 0 ? "fill-primary" : "fill-chart-1"}`}
          />
        ))}
      </svg>
      <span className="text-body-sm text-text">{label}</span>
    </span>
  );
}
