/**
 * The node-and-line motif in 2D (spec §13.13): a loose constellation with a small linked
 * team, one amber newcomer. Used for empty states, error pages and onboarding. Decorative.
 */
import { cn } from "@/lib/cn";

const NODES: [number, number, number][] = [
  [18, 30, 2.5],
  [44, 14, 2],
  [70, 34, 2.5],
  [96, 18, 2],
  [122, 40, 2.5],
  [150, 22, 2],
  [30, 70, 2],
  [58, 88, 2.5],
  [140, 78, 2],
  [168, 60, 2.5],
  [112, 96, 2],
];
const TEAM: [number, number][] = [
  [78, 62],
  [104, 56],
  [92, 80],
  [66, 82],
];

export function NodeArt({ className }: { className?: string | undefined }) {
  return (
    <svg
      viewBox="0 0 186 110"
      className={cn("h-24 w-auto", className)}
      aria-hidden="true"
      focusable="false"
    >
      <g className="stroke-text-subtle/40" strokeWidth="0.8">
        {NODES.slice(0, -1).map(([x, y], i) => {
          const next = NODES[i + 1];
          return next ? (
            <line key={`l${String(i)}`} x1={x} y1={y} x2={next[0]} y2={next[1]} />
          ) : null;
        })}
      </g>
      {NODES.map(([x, y, r], i) => (
        <circle
          key={`n${String(i)}`}
          cx={x}
          cy={y}
          r={r}
          className={i % 3 === 0 ? "fill-accent/50" : "fill-primary/45"}
        />
      ))}
      <g className="stroke-primary" strokeWidth="1.6" fill="none">
        <path d="M78 62 104 56 92 80 66 82Z" strokeLinejoin="round" />
        <line x1="78" y1="62" x2="92" y2="80" />
      </g>
      {TEAM.map(([x, y], i) => (
        <circle
          key={`t${String(i)}`}
          cx={x}
          cy={y}
          r="5"
          className={i === 3 ? "fill-newcomer" : "fill-primary"}
        />
      ))}
      <circle cx="66" cy="82" r="9" className="fill-newcomer/20" />
    </svg>
  );
}
