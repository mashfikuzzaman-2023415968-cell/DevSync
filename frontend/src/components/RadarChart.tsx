/**
 * Radar chart (spec §13.3 "charts (line, bar, radar …) with View as table", §13.8 #6).
 *
 * Custom SVG like `Gantt.tsx` (no chart library, so nothing injects styles under the strict
 * CSP). One polygon over N axes on a 0–100 scale, light grid rings at 25/50/75/100, the series
 * in `--chart-2`, labels in muted text. The chart is an image with a text summary; "View as
 * table" switches to the same numbers as a table. No motion.
 */
import { useId, useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useElementWidth } from "@/lib/useElementWidth";

export interface RadarAxis {
  label: string;
  /** 0–1 */
  value: number;
}

// Drawn at the container's real width (1 unit = 1 px), so labels stay 12 px at every size. The
// radius leaves about 92 px on each side for the longest side label ("Client diversity").
const RINGS = [0.25, 0.5, 0.75, 1];
const DEFAULT_WIDTH = 400;
const LABEL_ROOM = 92;
const MIN_RADIUS = 48;
const MAX_RADIUS = 110;

interface Geometry {
  width: number;
  height: number;
  cx: number;
  cy: number;
  radius: number;
}

function geometry(measured: number): Geometry {
  const width = measured > 0 ? measured : DEFAULT_WIDTH;
  const radius = Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, width / 2 - LABEL_ROOM));
  const height = Math.round(radius * 2 + 56);
  return { width, height, cx: width / 2, cy: height / 2, radius };
}

function point(g: Geometry, i: number, n: number, fraction: number): [number, number] {
  const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
  return [
    g.cx + g.radius * fraction * Math.cos(angle),
    g.cy + g.radius * fraction * Math.sin(angle),
  ];
}

function clamp(v: number): number {
  return Math.min(1, Math.max(0, v));
}

export function RadarChart({ title, axes }: { title: string; axes: readonly RadarAxis[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const captionId = useId();
  const [boxRef, measured] = useElementWidth<HTMLDivElement>();
  const g = geometry(measured);
  const n = axes.length;
  const summary = axes.map((a) => `${a.label} ${Math.round(clamp(a.value) * 100)}`).join(", ");
  const polygon = axes
    .map((a, i) =>
      point(g, i, n, clamp(a.value))
        .map((v) => v.toFixed(1))
        .join(","),
    )
    .join(" ");

  return (
    <div ref={boxRef}>
      <div className="flex justify-end">
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
        <figure className="mt-2" aria-labelledby={captionId}>
          <svg
            viewBox={`0 0 ${String(g.width)} ${String(g.height)}`}
            className="block w-full"
            role="img"
            aria-label={`${title}: ${summary}`}
          >
            <g className="fill-none stroke-border" strokeWidth="1">
              {RINGS.map((r) => (
                <polygon
                  key={r}
                  points={axes
                    .map((_a, i) =>
                      point(g, i, n, r)
                        .map((v) => v.toFixed(1))
                        .join(","),
                    )
                    .join(" ")}
                />
              ))}
              {axes.map((a, i) => {
                const [x, y] = point(g, i, n, 1);
                return <line key={a.label} x1={g.cx} y1={g.cy} x2={x} y2={y} />;
              })}
            </g>
            <polygon
              points={polygon}
              className="fill-chart-2/20 stroke-chart-2"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            {axes.map((a, i) => {
              const [x, y] = point(g, i, n, clamp(a.value));
              return <circle key={a.label} cx={x} cy={y} r="3" className="fill-chart-2" />;
            })}
            <g className="fill-text-muted text-caption" aria-hidden="true">
              {axes.map((a, i) => {
                const [x, y] = point(g, i, n, 1.16);
                const anchor = Math.abs(x - g.cx) < 4 ? "middle" : x < g.cx ? "end" : "start";
                return (
                  <text key={a.label} x={x} y={y} textAnchor={anchor} dominantBaseline="middle">
                    {a.label}
                  </text>
                );
              })}
            </g>
          </svg>
          <figcaption id={captionId} className="sr-only">
            {title}
          </figcaption>
        </figure>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-body-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th scope="col" className="py-2 font-medium">
                  Parameter
                </th>
                <th scope="col" className="py-2 text-right font-medium">
                  Score (0–100)
                </th>
              </tr>
            </thead>
            <tbody>
              {axes.map((a) => (
                <tr key={a.label} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 text-left font-normal text-text">
                    {a.label}
                  </th>
                  <td className="py-2 text-right tabular text-text">
                    {Math.round(clamp(a.value) * 100)}
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
