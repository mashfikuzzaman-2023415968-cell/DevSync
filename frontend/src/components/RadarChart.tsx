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

export interface RadarAxis {
  label: string;
  /** 0–1 */
  value: number;
}

// Wide enough that end-anchored side labels ("Client diversity") never clip at the edge.
const WIDTH = 400;
const HEIGHT = 290;
const CX = WIDTH / 2;
const CY = HEIGHT / 2;
const RADIUS = 96;
const RINGS = [0.25, 0.5, 0.75, 1];

function point(i: number, n: number, fraction: number): [number, number] {
  const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
  return [CX + RADIUS * fraction * Math.cos(angle), CY + RADIUS * fraction * Math.sin(angle)];
}

function clamp(v: number): number {
  return Math.min(1, Math.max(0, v));
}

export function RadarChart({ title, axes }: { title: string; axes: readonly RadarAxis[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const captionId = useId();
  const n = axes.length;
  const summary = axes.map((a) => `${a.label} ${Math.round(clamp(a.value) * 100)}`).join(", ");
  const polygon = axes
    .map((a, i) =>
      point(i, n, clamp(a.value))
        .map((v) => v.toFixed(1))
        .join(","),
    )
    .join(" ");

  return (
    <div>
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
            viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
            className="mx-auto block w-full max-w-[26rem]"
            role="img"
            aria-label={`${title}: ${summary}`}
          >
            <g className="fill-none stroke-border" strokeWidth="1">
              {RINGS.map((r) => (
                <polygon
                  key={r}
                  points={axes
                    .map((_a, i) =>
                      point(i, n, r)
                        .map((v) => v.toFixed(1))
                        .join(","),
                    )
                    .join(" ")}
                />
              ))}
              {axes.map((a, i) => {
                const [x, y] = point(i, n, 1);
                return <line key={a.label} x1={CX} y1={CY} x2={x} y2={y} />;
              })}
            </g>
            <polygon
              points={polygon}
              className="fill-chart-2/20 stroke-chart-2"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            {axes.map((a, i) => {
              const [x, y] = point(i, n, clamp(a.value));
              return <circle key={a.label} cx={x} cy={y} r="3" className="fill-chart-2" />;
            })}
            <g className="fill-text-muted text-caption" aria-hidden="true">
              {axes.map((a, i) => {
                const [x, y] = point(i, n, 1.16);
                const anchor = Math.abs(x - CX) < 4 ? "middle" : x < CX ? "end" : "start";
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
